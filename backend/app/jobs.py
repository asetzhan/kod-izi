"""Background jobs run by the RQ worker (`rq worker default`)."""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache

from redis import Redis
from rq import Callback, Queue
from rq.job import Job

from app.core.config import get_settings
from app.core.enums import SubmissionStatus
from app.db.session import get_sessionmaker
from app.judge import get_judge
from app.judge.judge0 import MAX_WALL_TIME_S
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


def mark_failed(submission_id: int) -> None:
    """A job that crashed or timed out must not leave the submission running forever."""
    with get_sessionmaker()() as db:
        submission = db.get(Submission, submission_id)
        if submission is not None and submission.status in (
            SubmissionStatus.QUEUED.value,
            SubmissionStatus.RUNNING.value,
        ):
            submission.status = SubmissionStatus.ERROR.value
            submission.error = "grading job failed"
            submission.finished_at = datetime.now(UTC)
            db.commit()


def _on_failure(job: Job, connection: object, *exc_info: object) -> None:
    mark_failed(int(job.args[0]))


def enqueue_grading(submission_id: int) -> None:
    with get_sessionmaker()() as db:
        submission = db.get(Submission, submission_id)
        tests = submission.tests_total if submission else 0
    # Each test may take up to Judge0's wall time limit plus queueing.
    _queue().enqueue(
        grade_job,
        submission_id,
        job_timeout=120 + tests * (MAX_WALL_TIME_S + 10),
        on_failure=Callback(_on_failure),
    )


def get_enqueue() -> Callable[[int], None]:
    """FastAPI dependency; tests replace it with inline grading."""
    return enqueue_grading
