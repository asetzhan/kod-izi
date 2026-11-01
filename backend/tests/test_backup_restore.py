"""Spec 13, 14.1, 16: an encrypted backup can really be restored.

Runs infra/backup/backup.sh against a scratch database filled by the migrations and the
seed, restores it with infra/backup/restore.sh into another scratch database and
compares them. Needs pg_dump, pg_restore, psql (same major version as the server) and
openssl in PATH.
"""

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.seed_content import seed_all
from tests.conftest import TEST_DATABASE_URL, alembic_config

TOOLS = ("pg_dump", "pg_restore", "psql", "openssl")
pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in TOOLS), reason="PostgreSQL client tools are missing"
)
SCRIPTS = Path(__file__).resolve().parents[2] / "infra" / "backup"
TABLES = [
    "courses",
    "topics",
    "external_lessons",
    "knowledge_components",
    "tasks",
    "test_cases",
    "users",
    "audit_log",
]


def _url(database: str) -> URL:
    return make_url(TEST_DATABASE_URL).set(database=database)


def _libpq_env(url: URL) -> dict[str, str]:
    host = url.host or str(url.query.get("host", ""))
    env = {"PGHOST": host, "PGUSER": url.username or "postgres", "PGDATABASE": url.database or ""}
    if url.port:
        env["PGPORT"] = str(url.port)
    if url.password:
        env["PGPASSWORD"] = url.password
    return env


@pytest.fixture
def scratch() -> Iterator[tuple[URL, URL]]:
    admin = create_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    names = ("kodizi_backup_src_test", "kodizi_backup_dst_test")
    with admin.connect() as conn:
        for name in names:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    yield _url(names[0]), _url(names[1])
    with admin.connect() as conn:
        for name in names:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _counts(url: URL) -> dict[str, int]:
    engine = create_engine(url)
    with engine.connect() as conn:
        counts = {
            t: int(conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()) for t in TABLES
        }
        counts["rls_tables"] = int(
            conn.execute(
                text("SELECT count(*) FROM pg_class WHERE relrowsecurity AND relkind = 'r'")
            ).scalar_one()
        )
        counts["app_grants"] = int(
            conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.role_table_grants "
                    "WHERE grantee = 'kodizi_app'"
                )
            ).scalar_one()
        )
    engine.dispose()
    return counts


def _run(script: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(SCRIPTS / script), *args],
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_sec14_encrypted_backup_restores_completely(
    scratch: tuple[URL, URL], tmp_path: Path
) -> None:
    source, target = scratch
    cfg = alembic_config()
    url = source.render_as_string(hide_password=False).replace("%", "%%")  # configparser
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(source)
    with Session(engine) as db:
        seed_all(db, get_settings().seed_dir)
        db.commit()
    engine.dispose()

    files = tmp_path / "materials"
    files.mkdir()
    (files / "book.bin").write_bytes(b"%PDF-1.4 sample")
    backups = tmp_path / "backups"
    secret = {"BACKUP_PASSPHRASE": "correct horse battery staple", "BACKUP_DIR": str(backups)}

    made = _run("backup.sh", {**_libpq_env(source), **secret, "MATERIAL_DIR": str(files)})
    assert made.returncode == 0, made.stderr
    db_file = next(backups.glob("kodizi-db-*.dump.enc"))
    files_file = next(backups.glob("kodizi-files-*.tar.enc"))
    assert b"stepik" not in db_file.read_bytes()  # encrypted, not a readable dump

    wrong = _run("restore.sh", {**_libpq_env(target), "BACKUP_PASSPHRASE": "wrong"}, str(db_file))
    assert wrong.returncode != 0

    restored_files = tmp_path / "restored"
    done = _run(
        "restore.sh",
        {**_libpq_env(target), **secret, "MATERIAL_DIR": str(restored_files)},
        str(db_file),
        str(files_file),
    )
    assert done.returncode == 0, done.stderr
    before, after = _counts(source), _counts(target)
    assert after == before
    assert before["tasks"] == 17 and before["rls_tables"] >= 12 and before["app_grants"] > 0
    assert (restored_files / "book.bin").read_bytes() == b"%PDF-1.4 sample"
