"""Training sequences for Code-DKT (ФТ-40) and a synthetic data set for the report.

One sequence per student: the attempts in time order, each with the knowledge component,
correctness (as for BKT, ФТ-39) and the code features. Real data come from the database
after the pilot; until then `synthetic` makes students whose code reflects what they know,
so the training and evaluation scripts can be checked end to end.
"""

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.features import FEATURE_DIM, code_features
from app.models import Submission, Task, TaskKnowledgeComponent, User
from app.services.analytics import process_report, work_events
from app.services.bkt import _correct


@dataclass
class Step:
    kc: int  # index into the course's component list
    correct: bool
    features: list[float]


@dataclass
class Sequence:
    student: int
    steps: list[Step] = field(default_factory=list)


def from_database(
    db: Session, course_id: int, user_id: int | None = None
) -> tuple[list[int], list[Sequence]]:
    """Component ids of the course and one sequence per student who has graded attempts
    (only `user_id`'s when given). Students who withdrew consent are left out (14.3)."""
    links = db.execute(
        select(TaskKnowledgeComponent.task_id, TaskKnowledgeComponent.knowledge_component_id)
        .join(Task, Task.id == TaskKnowledgeComponent.task_id)
        .where(Task.course_id == course_id)
        .order_by(TaskKnowledgeComponent.knowledge_component_id)
    ).all()
    components = sorted({kc for _, kc in links})
    index = {kc: i for i, kc in enumerate(components)}
    by_task: dict[int, list[int]] = {}
    for task_id, kc in links:
        by_task.setdefault(task_id, []).append(index[kc])
    sequences: dict[int, Sequence] = {}
    query = (
        select(Submission)
        .join(User, User.id == Submission.user_id)
        .where(
            Submission.task_id.in_(list(by_task)),
            Submission.verdict.is_not(None),
            User.consent_withdrawn_at.is_(None),
            User.anonymized_at.is_(None),
        )
        .order_by(Submission.created_at, Submission.id)
    )
    if user_id is not None:
        query = query.where(Submission.user_id == user_id)
    for s in db.scalars(query):
        features = code_features(
            s.code,
            s.static_analysis,
            process_report(work_events(db, s.user_id, s.task_id, s.assessment_id)),
        )
        correct = _correct(db, s)
        sequence = sequences.setdefault(s.user_id, Sequence(s.user_id))
        for kc in by_task[s.task_id]:
            sequence.steps.append(Step(kc, correct, features))
    return components, list(sequences.values())


GOOD = "int main(){int n;cin>>n;vector<int>a(n);for(auto&x:a)cin>>x;cout<<a.size();}"
POOR = (
    "int main(){int n,i,j,k;cin>>n;for(i=0;i<n;i++)for(j=0;j<n;j++)for(k=0;k<n;k++)if(i)if(j)n++;}"
)


def synthetic(
    students: int = 300, components: int = 5, steps: int = 12, seed: int = 11
) -> list[Sequence]:
    """Students learn components BKT-style, several attempts on one topic in a row; a
    student who knows a component writes cleaner code with fewer compile errors, even when
    the attempt fails. That is the signal Code-DKT can use and BKT cannot."""
    rng = random.Random(seed)  # noqa: S311  # nosec B311 (simulated data, not security)
    out = []
    for student in range(students):
        known = [rng.random() < 0.15 for _ in range(components)]
        sequence = Sequence(student)
        kc = rng.randrange(components)
        for _ in range(steps):
            # A course works on one topic for several attempts before moving on.
            if rng.random() < 0.3:
                kc = rng.randrange(components)
            knows = known[kc]
            correct = rng.random() >= 0.1 if knows else rng.random() < 0.25
            code = GOOD if knows else POOR
            process = {
                "compile_errors": rng.choice([0, 0, 1]) if knows else rng.choice([1, 2, 3]),
                "fix_minutes": rng.uniform(0, 3) if knows else rng.uniform(4, 20),
                "attempts": rng.randint(1, 2) if knows else rng.randint(2, 6),
            }
            sequence.steps.append(Step(kc, correct, code_features(code, None, process)))
            if not knows and rng.random() < 0.25:
                known[kc] = True
        out.append(sequence)
    if any(len(s.features) != FEATURE_DIM for q in out for s in q.steps):
        raise ValueError("feature length changed")
    return out
