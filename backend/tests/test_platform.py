"""Stage-0 platform checks: health endpoint, migrations, LLM gateway (ФТ-46)."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.db.base import Base
from app.llm.base import LLMRequest
from app.llm.fake import FakeLLMProvider
from app.llm.registry import get_provider
from tests.conftest import alembic_config


def test_sec15_health_reports_db_and_redis(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_sec15_single_alembic_head() -> None:
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


def test_sec15_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_sec15_pgvector_extension_installed(engine: Engine) -> None:
    with engine.connect() as conn:
        found = conn.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
    assert found == 1


def test_ft46_fake_provider_is_deterministic() -> None:
    request = LLMRequest(
        system="Grade by rubric.",
        data_blocks={"student_code": "int main() {}"},
        prompt_version="v0",
    )
    first = FakeLLMProvider().complete(request)
    assert first == FakeLLMProvider().complete(request)
    assert first.prompt_version == "v0"
    other = FakeLLMProvider().complete(LLMRequest(system="Grade by rubric."))
    assert other.text != first.text


def test_ft46_registry_returns_configured_provider() -> None:
    assert get_provider().name == "fake"
    with pytest.raises(ValueError, match="unknown LLM provider"):
        get_provider("does-not-exist")
