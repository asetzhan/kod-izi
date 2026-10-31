"""Background jobs run by the RQ worker (`rq worker default`)."""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache

from redis import Redis
from rq import Callback, Queue
from rq.job import Job

from app.core.config import get_settings
from app.core.enums import MaterialStatus, SubmissionStatus
from app.db.context import set_system
from app.db.session import get_sessionmaker
from app.judge import get_judge
from app.judge.judge0 import MAX_WALL_TIME_S
from app.llm.registry import get_provider
from app.models import MaterialVersion, Submission
from app.services.antivirus import ClamdScanner
from app.services.materials import process_version
from app.services.pipeline import run_pipeline


def grade_job(submission_id: int) -> None:
    """Testing, static analysis and the preliminary AI grade of a queued submission."""
    with get_sessionmaker()() as db:
        set_system(db)
        submission = db.get(Submission, submission_id)
        if submission is None or submission.status != SubmissionStatus.QUEUED.value:
            return
        run_pipeline(db, get_judge(), get_provider(), submission)
        db.commit()


def material_job(version_id: int) -> None:
    """ФТ-06: antivirus, text extraction and embeddings. Runs in the `extractor` worker."""
    settings = get_settings()
    with get_sessionmaker()() as db:
        set_system(db)
        version = db.get(MaterialVersion, version_id)
        if version is None or version.status != MaterialStatus.PENDING.value:
            return
        process_version(
            db, version, ClamdScanner(settings.clamav_host, settings.clamav_port), get_provider()
        )
        db.commit()


@lru_cache
def _materials_queue() -> Queue:
    return Queue("materials", connection=Redis.from_url(get_settings().redis_url))


def enqueue_material(version_id: int) -> None:
    _materials_queue().enqueue(material_job, version_id, job_timeout=600)


def get_material_enqueue() -> Callable[[int], None]:
    """FastAPI dependency; tests replace it with inline processing."""
    return enqueue_material


@lru_cache
def _queue() -> Queue:
    return Queue("default", connection=Redis.from_url(get_settings().redis_url))


def mark_failed(submission_id: int) -> None:
    """A job that crashed or timed out must not leave the submission running forever."""
    with get_sessionmaker()() as db:
        set_system(db)
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
        set_system(db)
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
