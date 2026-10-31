"""Digital trace writer (ФТ-25) and academic integrity marks (ФТ-29)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import TraceKind
from app.models import AppSetting, TraceEvent, WorkSession

INTEGRITY_KEY = "integrity"
DEFAULT_INTEGRITY = {"large_paste_chars": 200}

# Events the browser may send. Compile, run, test, submit and verdict are written by
# the server itself, so a student cannot forge them.
CLIENT_KINDS = {TraceKind.SNAPSHOT, TraceKind.PASTE, TraceKind.FOCUS_LOST, TraceKind.FOCUS_BACK}


class IntegritySettings(BaseModel):
    large_paste_chars: int = Field(ge=1, le=100_000)


def get_integrity(db: Session) -> IntegritySettings:
    stored = db.get(AppSetting, INTEGRITY_KEY)
    return IntegritySettings.model_validate(stored.value if stored else DEFAULT_INTEGRITY)


def is_flagged(kind: TraceKind, payload: dict[str, Any], settings: IntegritySettings) -> bool:
    """Large pastes are marked for the teacher. A mark is a hint, not evidence (spec 14.1)."""
    if kind == TraceKind.PASTE:
        return int(payload.get("length", 0)) >= settings.large_paste_chars
    return False


def record_server_event(
    db: Session, session: WorkSession, kind: TraceKind, payload: dict[str, Any]
) -> None:
    db.add(
        TraceEvent(
            session_id=session.id,
            user_id=session.user_id,
            task_id=session.task_id,
            assessment_id=session.assessment_id,
            seq=None,
            kind=kind.value,
            payload=payload,
        )
    )


class ClientEvent(BaseModel):
    seq: int = Field(ge=0)
    kind: TraceKind
    client_ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


def ingest_client_events(db: Session, session: WorkSession, events: list[ClientEvent]) -> int:
    """Store browser events; a batch sent again after a network failure is not duplicated."""
    settings = get_integrity(db)
    rows = [
        {
            "session_id": session.id,
            "user_id": session.user_id,
            "task_id": session.task_id,
            "assessment_id": session.assessment_id,
            "seq": e.seq,
            "kind": e.kind.value,
            "client_ts": e.client_ts,
            "payload": e.payload,
            "flagged": is_flagged(e.kind, e.payload, settings),
        }
        for e in events
    ]
    if not rows:
        return 0
    statement = (
        insert(TraceEvent)
        .values(rows)
        .on_conflict_do_nothing(
            index_elements=["session_id", "seq"], index_where=TraceEvent.seq.is_not(None)
        )
        .returning(TraceEvent.id)
    )
    return len(db.execute(statement).all())


def session_events(db: Session, session_id: object) -> list[TraceEvent]:
    """Events in the order needed to replay the session.

    Browser events use their own time, so events sent late after a network outage still
    fall into place.
    """
    return list(
        db.scalars(
            select(TraceEvent)
            .where(TraceEvent.session_id == session_id)
            .order_by(
                func.coalesce(TraceEvent.client_ts, TraceEvent.server_ts),
                TraceEvent.seq.nulls_last(),
                TraceEvent.id,
            )
        )
    )
