#!/usr/bin/env python3
"""PostToolUse hook (spec 15.4): lint the file Claude just changed.

Python files go through ruff, TypeScript files through eslint. Remaining problems are
printed to stderr with exit code 2 so Claude sees them; a missing linter is skipped.
"""

import json
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603
    return result.returncode, (result.stdout + result.stderr).strip()


def lint(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return None
    if rel.parts[0] == "backend" and path.suffix == ".py":
        ruff = shutil.which("ruff")
        if ruff is None:
            return None
        cwd = ROOT / "backend"
        target = str(path.resolve())
        _run([ruff, "format", target], cwd)
        code, out = _run([ruff, "check", "--fix", target], cwd)
        return out if code else None
    if rel.parts[0] == "frontend" and path.suffix in {".ts", ".tsx"}:
        eslint = ROOT / "frontend" / "node_modules" / ".bin" / "eslint"
        if not eslint.exists():
            return None
        code, out = _run([str(eslint), "--fix", str(path.resolve())], ROOT / "frontend")
        return out if code else None
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not Path(file_path).exists():
        return 0
    problems = lint(Path(file_path))
    if problems:
        print(f"Lint problems in {file_path}:\n{problems}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
