"""Static analysis of submitted code (ФТ-32): clang-tidy, cppcheck, complexity metrics.

The analysers read the code but never run it. They still run the preprocessor, which
could pull a server file into a warning (`#include "/proc/self/environ"`), so code with
anything but plain `#include <header>` directives is not analysed, and the tools get an
empty environment and a time limit.
"""

import re
import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path
from typing import Any

import lizard

TIMEOUT_S = 20
MAX_WARNINGS = 100
CLANG_TIDY_CHECKS = (
    "-*,bugprone-*,readability-*,performance-*,misc-*,modernize-use-nullptr,"
    "-readability-magic-numbers,-readability-identifier-length,-misc-include-cleaner,"
    "-readability-braces-around-statements,-misc-use-anonymous-namespace,"
    "-misc-use-internal-linkage,-misc-const-correctness"
)
SAFE_INCLUDE = re.compile(
    r"^\s*#\s*include\s*<[A-Za-z0-9_+]+(?:/[A-Za-z0-9_+]+)*(?:\.h|\.hpp)?>\s*$"
)
DIRECTIVE = re.compile(r"^\s*#\s*(\w+)")
ALLOWED_DIRECTIVES = {"define", "undef", "if", "ifdef", "ifndef", "else", "elif", "endif", "pragma"}
CLANG_LINE = re.compile(r"^[^:]*:(\d+):(\d+): (warning|error|note): (.*?)(?: \[([\w.,-]+)\])?$")


def unsafe_reason(code: str) -> str | None:
    """Why the code must not go through the preprocessor of the analysers, if it must not."""
    joined = re.sub(r"\\\r?\n", "", code)
    if "%:" in joined or "??=" in joined:
        return "digraph_or_trigraph"
    if "__has_include" in joined:
        return "has_include"
    for line in joined.splitlines():
        match = DIRECTIVE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name == "include":
            if not SAFE_INCLUDE.match(line) or ".." in line:
                return "include_not_allowed"
        elif name not in ALLOWED_DIRECTIVES:
            return f"directive_{name}"
    return None


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(  # noqa: S603  # nosec B603
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
        check=False,
    )
    return result.stdout + result.stderr


def parse_clang_tidy(output: str) -> list[dict[str, Any]]:
    warnings = []
    for line in output.splitlines():
        match = CLANG_LINE.match(line)
        if match and match.group(3) != "note":
            warnings.append(
                {
                    "tool": "clang-tidy",
                    "line": int(match.group(1)),
                    "severity": match.group(3),
                    "check": match.group(5) or "clang-diagnostic",
                    "message": match.group(4)[:300],
                }
            )
    return warnings


def parse_cppcheck(output: str) -> list[dict[str, Any]]:
    warnings = []
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4 and parts[0].isdigit():
            warnings.append(
                {
                    "tool": "cppcheck",
                    "line": int(parts[0]),
                    "severity": parts[1],
                    "check": parts[2],
                    "message": parts[3][:300],
                }
            )
    return warnings


def metrics(code: str) -> dict[str, Any]:
    """Size and cyclomatic complexity per function (lizard parses, does not compile)."""
    info = lizard.analyze_file.analyze_source_code("main.cpp", code)
    functions = [
        {
            "name": f.name,
            "ccn": f.cyclomatic_complexity,
            "nloc": f.nloc,
            "params": len(f.parameters),
        }
        for f in info.function_list
    ]
    return {
        "nloc": info.nloc,
        "functions": functions,
        "max_ccn": max((f["ccn"] for f in functions), default=0),
    }


def analyse(code: str, language: str = "cpp17", *, run_tools: bool = True) -> dict[str, Any]:
    std = "-std=c++17" if language == "cpp17" else "-std=c++20"
    report: dict[str, Any] = {"metrics": metrics(code), "warnings": [], "tools": {}}
    if not run_tools:
        return report
    reason = unsafe_reason(code)
    if reason is not None:
        report["skipped"] = reason
        return report
    with tempfile.TemporaryDirectory(prefix="kod-izi-sa-") as tmp:
        folder = Path(tmp)
        (folder / "main.cpp").write_text(code, encoding="utf-8")
        warnings: list[dict[str, Any]] = []
        clang_tidy = shutil.which("clang-tidy")
        if clang_tidy:
            try:
                out = _run(
                    [clang_tidy, "main.cpp", f"--checks={CLANG_TIDY_CHECKS}", "--quiet", "--", std],
                    folder,
                )
                warnings += parse_clang_tidy(out)
                report["tools"]["clang-tidy"] = "ok"
            except subprocess.TimeoutExpired:
                report["tools"]["clang-tidy"] = "timeout"
        else:
            report["tools"]["clang-tidy"] = "missing"
        cppcheck = shutil.which("cppcheck")
        if cppcheck:
            try:
                out = _run(
                    [
                        cppcheck,
                        "--enable=warning,style,performance,portability",
                        "--template={line}|{severity}|{id}|{message}",
                        "--quiet",
                        f"--std={std.removeprefix('-std=')}",
                        "main.cpp",
                    ],
                    folder,
                )
                warnings += parse_cppcheck(out)
                report["tools"]["cppcheck"] = "ok"
            except subprocess.TimeoutExpired:
                report["tools"]["cppcheck"] = "timeout"
        else:
            report["tools"]["cppcheck"] = "missing"
    report["warnings"] = warnings[:MAX_WARNINGS]
    return report
