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
from app.models import AiGrade, Submission
from app.services import ai_grading
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
    try:
        return ai_grading.grade(db, provider, submission)
    except LLMUnavailableError:
        return None  # the teacher can start the AI grade again later
