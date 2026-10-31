"""Who is asking, as seen by PostgreSQL row-level security (spec 14.1, "Рұқсаттар").

The application works as the non-superuser role `kodizi_app` (see migration 0006).
Policies on student-data tables let a row through only to its own student, to staff
or to background jobs. The values live in transaction-local settings, so they cannot
leak to the next request that reuses the pooled connection; they are applied again at
the start of every transaction from `session.info`.
"""

from typing import Any

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.roles import Role

INFO_KEY = "db_actor"
STAFF = (Role.TEACHER, Role.COACH, Role.ADMIN)


def _apply(session: Session, actor: dict[str, str]) -> None:
    session.execute(
        text(
            "SELECT set_config('app.user_id', :user_id, true), "
            "set_config('app.privileged', :privileged, true)"
        ),
        actor,
    )


def set_actor(session: Session, user: Any) -> None:
    """Requests: the authenticated user."""
    actor = {
        "user_id": str(user.id),
        "privileged": "on" if user.has_role(*STAFF) else "off",
    }
    session.info[INFO_KEY] = actor
    _apply(session, actor)


def set_system(session: Session) -> None:
    """Background jobs and management commands act for the system."""
    actor = {"user_id": "", "privileged": "on"}
    session.info[INFO_KEY] = actor
    _apply(session, actor)


@event.listens_for(Session, "after_begin")
def _reapply(session: Session, transaction: Any, connection: Any) -> None:
    actor = session.info.get(INFO_KEY)
    if actor is not None:
        connection.execute(
            text(
                "SELECT set_config('app.user_id', :user_id, true), "
                "set_config('app.privileged', :privileged, true)"
            ),
            actor,
        )
