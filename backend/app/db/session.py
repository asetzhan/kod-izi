from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import app.db.context  # noqa: F401  (registers the per-transaction actor listener)
from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    role = settings.db_app_role
    if role:
        # Work as the non-superuser role, so row-level security applies (spec 14.1).
        @event.listens_for(engine, "connect")
        def _set_role(dbapi_connection: Any, record: Any) -> None:
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{role}"')  # role name comes from settings only

    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session
