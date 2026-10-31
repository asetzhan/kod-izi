"""Task bank operations (ФТ-10, ФТ-18, ФТ-19, ФТ-22)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import LevelStatus, TaskLevel, TaskStatus
from app.models import KnowledgeComponent, Task, TaskKnowledgeComponent, TestCase, Topic
from app.services.levels import LevelRule
from app.services.task_import import ImportedTest, TaskDraftData


class TaskError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def topic_in_course(db: Session, course_id: int, topic_id: int | None) -> Topic | None:
    if topic_id is None:
        return None
    topic = db.get(Topic, topic_id)
    if topic is None or topic.course_id != course_id:
        raise TaskError("topic_not_in_course", "the topic does not belong to this course")
    return topic


def set_knowledge_components(db: Session, task: Task, kc_ids: list[int]) -> None:
    """ФТ-10: only components of the task's own course may be linked."""
    if kc_ids:
        rows = db.scalars(
            select(KnowledgeComponent)
            .join(Topic, Topic.id == KnowledgeComponent.topic_id)
            .where(KnowledgeComponent.id.in_(kc_ids), Topic.course_id == task.course_id)
        ).all()
        if len(rows) != len(set(kc_ids)):
            raise TaskError("kc_not_in_course", "a knowledge component is not in this course")
    task.kc_links = [
        TaskKnowledgeComponent(knowledge_component_id=i) for i in dict.fromkeys(kc_ids)
    ]


def set_tests(task: Task, tests: list[ImportedTest]) -> None:
    task.tests = [
        TestCase(
            position=i,
            input=t.input,
            expected_output=t.expected_output,
            is_hidden=t.is_hidden,
        )
        for i, t in enumerate(tests, start=1)
    ]


def apply_level(
    task: Task,
    rule: LevelRule,
    scores: dict[str, int] | None,
    status: LevelStatus,
    level: TaskLevel | None = None,
    rationale: str = "",
) -> None:
    """Store feature scores; the level comes from the rule unless given explicitly."""
    if scores is not None:
        task.set_features(scores)
        level = level or rule.level_for(scores)
    task.level = level.value if level else None
    task.level_status = status.value if level else LevelStatus.UNRATED.value
    if rationale:
        task.level_rationale = rationale


def find_kc_ids(db: Session, course_id: int, codes: list[str]) -> list[int]:
    if not codes:
        return []
    rows = db.execute(
        select(KnowledgeComponent.code, KnowledgeComponent.id)
        .join(Topic, Topic.id == KnowledgeComponent.topic_id)
        .where(Topic.course_id == course_id, KnowledgeComponent.code.in_(codes))
    ).all()
    found = dict(rows)
    missing = [c for c in codes if c not in found]
    if missing:
        raise TaskError("unknown_kc", f"unknown knowledge components: {', '.join(missing)}")
    return [found[c] for c in codes]


def create_from_draft(
    db: Session, course_id: int, draft: TaskDraftData, rule: LevelRule, author_id: int | None
) -> Task:
    """Imported tasks always start as drafts with a suggested level at most (Q-07)."""
    topic_id = None
    if draft.topic_code:
        topic = db.scalar(
            select(Topic).where(Topic.course_id == course_id, Topic.code == draft.topic_code)
        )
        if topic is None:
            raise TaskError("unknown_topic", f"unknown topic {draft.topic_code}")
        topic_id = topic.id
    task = Task(
        course_id=course_id,
        topic_id=topic_id,
        external_key=draft.external_key,
        title=draft.title,
        statement_md=draft.statement_md,
        input_format=draft.input_format,
        output_format=draft.output_format,
        time_limit_ms=draft.time_limit_ms,
        memory_limit_kb=draft.memory_limit_kb,
        reference_solution=draft.reference_solution,
        reference_language=draft.reference_language,
        source_url=draft.source_url,
        source_note=draft.source_note,
        status=TaskStatus.DRAFT.value,
        author_id=author_id,
    )
    set_tests(task, draft.tests)
    if draft.features is not None:
        derived = rule.level_for(draft.features)
        if draft.level is not None and draft.level != derived:
            raise TaskError(
                "level_mismatch",
                f"features give level {derived.value}, config says {draft.level.value}",
            )
    apply_level(
        task, rule, draft.features, LevelStatus.SUGGESTED, draft.level, draft.level_rationale
    )
    db.add(task)
    db.flush()
    set_knowledge_components(db, task, find_kc_ids(db, course_id, draft.knowledge_components))
    return task


def approve(task: Task) -> None:
    """A task is shown to students only when it is complete and its level confirmed."""
    problems = []
    if task.level_status != LevelStatus.CONFIRMED.value:
        problems.append("level_not_confirmed")
    if not task.tests:
        problems.append("no_tests")
    if not any(not t.is_hidden for t in task.tests):
        problems.append("no_public_test")
    if not task.reference_solution.strip():
        problems.append("no_reference_solution")
    if problems:
        raise TaskError("not_ready", ", ".join(problems))
    task.status = TaskStatus.APPROVED.value
