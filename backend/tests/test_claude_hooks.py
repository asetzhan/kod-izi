"""Spec 15.4: the PreToolUse hook really blocks changes to .env and secrets."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[2]))
HOOK = REPO_ROOT / ".claude" / "hooks" / "protect_files.py"

pytestmark = pytest.mark.skipif(not HOOK.exists(), reason="repository .claude/ not mounted")


def _run_hook(tool_name: str, tool_input: dict[str, str]) -> int:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    result = subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, check=False
    )
    return result.returncode


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Write", {"file_path": "/repo/.env"}),
        ("Edit", {"file_path": "/repo/backend/.env.local"}),
        ("Write", {"file_path": "/repo/infra/prod/docker-compose.yml"}),
        ("Write", {"file_path": "/repo/infra/nginx/nginx.prod.conf"}),
        ("Write", {"file_path": "/repo/secrets/jwt.txt"}),
        ("Write", {"file_path": "/repo/infra/nginx/server.key"}),
        ("Bash", {"command": "echo JWT_SECRET=x > .env"}),
        ("Bash", {"command": "echo X >> /repo/.env"}),
        ("Bash", {"command": "sed -i 's/a/b/' .env"}),
        ("Bash", {"command": "cp .env.example .env"}),
        ("Bash", {"command": "rm -f .env"}),
        ("Bash", {"command": "cat .env"}),
        ("Bash", {"command": "echo x > '.en''v'"}),
        ("Bash", {"command": "python3 -c \"open('.env', 'w').write('x')\""}),
        ("Write", {"file_path": "/repo/.claude/settings.json"}),
        ("Write", {"file_path": "/repo/.claude/settings.local.json"}),
        ("Edit", {"file_path": "/repo/.claude/hooks/protect_files.py"}),
        ("Bash", {"command": "sed -i 's/2/0/' .claude/hooks/protect_files.py"}),
        ("Bash", {"command": "echo '{}' > .claude/settings.json"}),
    ],
)
def test_sec15_hook_blocks_protected_files(tool: str, tool_input: dict[str, str]) -> None:
    assert _run_hook(tool, tool_input) == 2


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Write", {"file_path": "/repo/.env.example"}),
        ("Edit", {"file_path": "/repo/backend/app/main.py"}),
        ("Write", {"file_path": "/repo/infra/docker-compose.yml"}),
        ("Bash", {"command": "cat .env.example"}),
        ("Bash", {"command": "make test > /tmp/out.txt"}),
        ("Bash", {"command": "git status"}),
        ("Bash", {"command": "python3 .claude/hooks/protect_files.py < payload.json"}),
        ("Edit", {"file_path": "/repo/.claude/agents/security-reviewer.md"}),
    ],
)
def test_sec15_hook_allows_ordinary_files(tool: str, tool_input: dict[str, str]) -> None:
    assert _run_hook(tool, tool_input) == 0


def test_sec15_hook_follows_symlinks_to_protected_files(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("JWT_SECRET=x\n")
    link = tmp_path / "notes.txt"
    link.symlink_to(secret)
    assert _run_hook("Write", {"file_path": str(link)}) == 2


def test_sec15_hook_blocks_unreadable_input() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
