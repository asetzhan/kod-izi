"""The single entry to the LLM (ФТ-46): quotas and usage log (spec 14.1, "LLM ресурсы")."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMRequest, LLMResponse
from app.models import LlmUsage

# Purposes started by a student count against the student's daily quota. Grading is
# started by the system and is not limited per student.
STUDENT_PURPOSES = {"assistant", "questions", "hint"}


class QuotaExceededError(Exception):
    pass


def used_today(db: Session, user_id: int, purposes: set[str]) -> int:
    since = datetime.now(UTC) - timedelta(days=1)
    return int(
        db.scalar(
            select(func.count())
            .select_from(LlmUsage)
            .where(
                LlmUsage.user_id == user_id,
                LlmUsage.purpose.in_(purposes),
                LlmUsage.created_at > since,
            )
        )
        or 0
    )


QUOTA_LOCK = 4_710_001  # namespace of the per-student advisory lock


def ensure_quota(db: Session, user_id: int) -> None:
    """Check the student's daily quota under a per-student lock.

    The lock lasts until the transaction ends, so a student's parallel requests are
    counted one after another and cannot all pass the check at once.
    """
    db.execute(select(func.pg_advisory_xact_lock(QUOTA_LOCK, user_id)))
    if used_today(db, user_id, STUDENT_PURPOSES) >= get_settings().llm_daily_quota:
        raise QuotaExceededError("daily quota")


def call(
    db: Session,
    provider: LLMProvider,
    request: LLMRequest,
    *,
    purpose: str,
    user_id: int | None,
) -> LLMResponse:
    usage = LlmUsage(
        user_id=user_id,
        purpose=purpose,
        model=request.model or "",
        prompt_version=request.prompt_version,
        input_tokens=0,
        output_tokens=0,
    )
    if user_id is not None and purpose in STUDENT_PURPOSES:
        ensure_quota(db, user_id)
        # Reserved before the call: a failed call still counts against the quota.
        db.add(usage)
        db.flush()
    response = provider.complete(request)
    usage.model = response.model
    usage.input_tokens = response.input_tokens
    usage.output_tokens = response.output_tokens
    db.add(usage)
    return response
