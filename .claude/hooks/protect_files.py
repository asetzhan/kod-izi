#!/usr/bin/env python3
"""PreToolUse hook (spec 15.4): block changes to .env, secret keys and production config.

Reads the tool call as JSON on stdin. Exit code 2 blocks the call and shows stderr to Claude.
"""

import itertools
import json
import re
import sys
from pathlib import PurePosixPath

ALLOWED_NAMES = {".env.example"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".crt")
SECRET_NAMES = {"id_rsa", "id_ed25519", "credentials.json"}
WRITE_COMMANDS = re.compile(
    r"(>|\btee\b|\bsed\s+(-\w*\s+)*-i|\bcp\b|\bmv\b|\brm\b|\btruncate\b|\bdd\b|\bchmod\b"
    r"|\bln\b|\binstall\b|\bperl\s+-\w*i)"
)
PATH_TOKEN = re.compile(r"[\w./~-]+")


def is_protected(path: str) -> bool:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if not parts:
        return False
    name = parts[-1]
    if name in ALLOWED_NAMES:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    if name.endswith(SECRET_SUFFIXES) or name in SECRET_NAMES:
        return True
    if "secrets" in parts[:-1]:
        return True
    if any(a == "infra" and b == "prod" for a, b in itertools.pairwise(parts)):
        return True
    return ".prod." in name


def check(payload: dict[str, object]) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    tool = payload.get("tool_name")
    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        if not WRITE_COMMANDS.search(command):
            return None
        hits = [t for t in PATH_TOKEN.findall(command) if is_protected(t)]
        return f"command writes to protected file(s): {', '.join(hits)}" if hits else None
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and is_protected(value):
            return f"{value} is protected"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    reason = check(payload)
    if reason is None:
        return 0
    print(
        f"Blocked by .claude/hooks/protect_files.py: {reason}. "
        "CLAUDE.md forbids changing .env, secret keys and production config; "
        "ask the customer to make this change.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
