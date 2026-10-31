"""Background jobs run by the RQ worker (`rq worker default`)."""

from collections.abc import Callable
from functools import lru_cache

from redis import Redis
from rq import Queue

from app.core.config import get_settings
from app.core.enums import SubmissionStatus
from app.db.session import get_sessionmaker
from app.judge import get_judge
from app.models import Submission
from app.services.grading import grade_submission


def grade_job(submission_id: int) -> None:
    """ФТ-31: grade a queued submission through Judge0."""
    with get_sessionmaker()() as db:
        submission = db.get(Submission, submission_id)
        if submission is None or submission.status != SubmissionStatus.QUEUED.value:
            return
        grade_submission(db, get_judge(), submission)
        db.commit()


@lru_cache
def _queue() -> Queue:
    return Queue("default", connection=Redis.from_url(get_settings().redis_url))


def enqueue_grading(submission_id: int) -> None:
    _queue().enqueue(grade_job, submission_id, job_timeout=600)


def get_enqueue() -> Callable[[int], None]:
    """FastAPI dependency; tests replace it with inline grading."""
    return enqueue_grading
