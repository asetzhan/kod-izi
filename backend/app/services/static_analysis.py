"""Static analysis of submitted code (ФТ-32): clang-tidy, cppcheck, complexity metrics.

The analysers read the code but never run it. They still run the preprocessor, which
could pull a server file into a warning (`#include "/proc/self/environ"`), so code with
anything but plain `#include <header>` directives is not analysed (comments are removed
first, as the preprocessor does), only diagnostics about the submitted file are kept, and
the tools run with an empty environment and memory, CPU and time limits.
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
SAFE_PRAGMA = re.compile(
    r"^\s*#\s*pragma\s+(once|GCC\s+(optimize|target)\s*\([\w\s,\"+.=-]*\)|pack\s*\([\w\s,]*\)"
    r"|region\b.*|endregion\b.*)\s*$"
)
CLANG_LINE = re.compile(r"^(.*):(\d+):(\d+): (warning|error|note): (.*?)(?: \[([\w.,-]+)\])?$")
RAW_STRING = re.compile(r'R"([^ ()\\\t\n]{0,16})\(')


def mask_comments_and_literals(code: str) -> str:
    """Replace comments by a space and string/char literal contents by `S`.

    The preprocessor removes comments before it reads directives, so
    `/**/#include "/proc/1/environ"` is a real directive; only after this masking can
    directives be found reliably. Line breaks are kept.
    """
    out: list[str] = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if code.startswith("//", i):
            j = code.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2)
            block = code[i:] if j == -1 else code[i : j + 2]
            out.append(" " + "\n" * block.count("\n"))
            i = n if j == -1 else j + 2
        elif (raw := RAW_STRING.match(code, i)) and (i == 0 or not code[i - 1].isalnum()):
            closing = ")" + raw.group(1) + '"'
            j = code.find(closing, raw.end())
            body = code[i:] if j == -1 else code[i : j + len(closing)]
            out.append('"S"' + "\n" * body.count("\n"))
            i = n if j == -1 else j + len(closing)
        elif c in "\"'":
            j = i + 1
            while j < n and code[j] != c and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            out.append(f"{c}S{c}")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def unsafe_reason(code: str) -> str | None:
    """Why the code must not go through the preprocessor of the analysers, if it must not."""
    joined = re.sub(r"\\\r?\n", "", code)
    if "%:" in joined or "??=" in joined:
        return "digraph_or_trigraph"
    masked = mask_comments_and_literals(joined)
    if "__has_include" in masked or "_Pragma" in masked:
        return "has_include" if "__has_include" in masked else "pragma_operator"
    for line in masked.splitlines():
        if "#" not in line:
            continue
        match = DIRECTIVE.match(line)
        if not match:
            if line.lstrip().startswith("#"):
                continue  # a lone `#` (null directive) does nothing
            # `#` and `##` are valid only inside #define lines, handled above.
            return "stray_hash"
        name = match.group(1)
        if name == "include":
            if not SAFE_INCLUDE.match(line) or ".." in line:
                return "include_not_allowed"
        elif name == "pragma":
            if not SAFE_PRAGMA.match(line):
                return "pragma_not_allowed"
        elif name not in ALLOWED_DIRECTIVES:
            return f"directive_{name}"
    return None


def _limits() -> None:  # pragma: no cover - runs in the child process
    """Memory, CPU and output size limits for the analysers."""
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(  # noqa: S603  # nosec B603
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
        preexec_fn=_limits,  # nosec B602
        check=False,
    )
    return result.stdout + result.stderr


def parse_clang_tidy(output: str, analysed: str = "main.cpp") -> list[dict[str, Any]]:
    """Diagnostics of the analysed file only; anything about another file is dropped."""
    allowed = {analysed, "main.cpp", "./main.cpp"}
    warnings = []
    for line in output.splitlines():
        match = CLANG_LINE.match(line)
        if match and match.group(1) in allowed and match.group(4) != "note":
            warnings.append(
                {
                    "tool": "clang-tidy",
                    "line": int(match.group(2)),
                    "severity": match.group(4),
                    "check": match.group(6) or "clang-diagnostic",
                    "message": match.group(5)[:300],
                }
            )
    return warnings


def parse_cppcheck(output: str) -> list[dict[str, Any]]:
    warnings = []
    for line in output.splitlines():
        parts = line.split("|", 4)
        # Diagnostics of the analysed file only.
        if len(parts) == 5 and parts[0] in ("main.cpp", "./main.cpp") and parts[1].isdigit():
            warnings.append(
                {
                    "tool": "cppcheck",
                    "line": int(parts[1]),
                    "severity": parts[2],
                    "check": parts[3],
                    "message": parts[4][:300],
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
                warnings += parse_clang_tidy(out, str(folder / "main.cpp"))
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
                        "--template={file}|{line}|{severity}|{id}|{message}",
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
