"""What happens to a submission in the background (spec 8, steps 1–7).

Testing (ФТ-31), static analysis (ФТ-32), then the preliminary AI grade (ФТ-34, ФТ-35).
The teacher's decision (step 8) is stage 4.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import SubmissionStatus
from app.judge.client import JudgeClient
from app.llm.base import LLMProvider
from app.llm.ollama import LLMUnavailableError
from app.models import AiGrade, Assessment, Submission
from app.services import ai_grading
from app.services.assignments import assignment_for
from app.services.component_fill import fill_submission
from app.services.contests import is_contest
from app.services.grading import grade_submission
from app.services.static_analysis import analyse

Analyser = Callable[[str, str], dict[str, Any]]


def run_pipeline(
    db: Session,
    judge: JudgeClient,
    provider: LLMProvider,
    submission: Submission,
    analyser: Analyser = analyse,
) -> AiGrade | None:
    grade_submission(db, judge, submission)
    if submission.status != SubmissionStatus.DONE.value:
        return None
    submission.static_analysis = analyser(submission.code, submission.language)
    db.flush()
    assessment = db.get(Assessment, submission.assessment_id) if submission.assessment_id else None
    assigned = assessment is None and assignment_for(db, submission.user_id, submission.task_id)
    if (assessment is None and not assigned) or is_contest(assessment):
        # Olympiad practice and contests: the verdict is the result; the AI analysis
        # after a contest (ОТ-07) is a later stage. An individual task (ФТ-05) is graded.
        return None
    try:
        grade = ai_grading.grade(db, provider, submission)
        db.flush()
    except LLMUnavailableError:
        grade = None  # the teacher can start the AI grade again later
    fill_submission(db, submission, grade)  # components 4 and 5 (spec 6)
    return grade
