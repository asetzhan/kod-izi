"""The single entry to the LLM (ФТ-46): quotas and usage log (spec 14.1, "LLM ресурсы")."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMRequest, LLMResponse
from app.models import LlmUsage

# Purposes started by a student count against the student's daily quota. Grading is
# started by the system and is not limited per student.
STUDENT_PURPOSES = {"assistant", "questions"}


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


def call(
    db: Session,
    provider: LLMProvider,
    request: LLMRequest,
    *,
    purpose: str,
    user_id: int | None,
) -> LLMResponse:
    if (
        user_id is not None
        and purpose in STUDENT_PURPOSES
        and used_today(db, user_id, STUDENT_PURPOSES) >= get_settings().llm_daily_quota
    ):
        raise QuotaExceededError(purpose)
    response = provider.complete(request)
    db.add(
        LlmUsage(
            user_id=user_id,
            purpose=purpose,
            model=response.model,
            prompt_version=response.prompt_version,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
    )
    return response
