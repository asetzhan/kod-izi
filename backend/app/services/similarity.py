"""Code similarity of an assessment's submissions (ФТ-30; spec 14.1, academic integrity).

JPlag (C++ front end) runs in the separate `analyzer` worker: no internet, its own
container, the code only parsed, never executed (CLAUDE.md). Where JPlag is not installed
(development, tests) a built-in token-winnowing comparison gives the same kind of score.
A high score is a hint for the teacher, not evidence (spec 14.1).
"""

import csv
import hashlib
import io
import re
import shutil
import subprocess  # nosec B404
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SimilarityReport, Submission

JPLAG_TIMEOUT_S = 600
MIN_TOKENS = 12
K_GRAM = 5
WINDOW = 4

# Built-in engine -----------------------------------------------------------------------------

TOKEN = re.compile(
    r"[A-Za-z_]\w*|\d+(?:\.\d+)?|==|!=|<=|>=|&&|\|\||<<|>>|\+\+|--|[{}()\[\];,<>=+\-*/%!&|^~?:.]"
)
COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
KEYWORDS = {
    "int",
    "long",
    "short",
    "char",
    "bool",
    "double",
    "float",
    "void",
    "auto",
    "const",
    "unsigned",
    "signed",
    "for",
    "while",
    "do",
    "if",
    "else",
    "switch",
    "case",
    "break",
    "continue",
    "return",
    "struct",
    "class",
    "using",
    "namespace",
    "include",
    "define",
    "vector",
    "string",
    "map",
    "set",
    "cin",
    "cout",
    "endl",
    "main",
    "std",
    "true",
    "false",
}


def normalize(code: str) -> list[str]:
    """Tokens with comments and literals removed and identifiers renamed: renaming
    variables or reformatting does not hide copying."""
    code = STRING.sub(" STR ", COMMENT.sub(" ", code))
    out = []
    for token in TOKEN.findall(code):
        if token[0].isalpha() or token[0] == "_":
            out.append(token if token in KEYWORDS else "ID")
        elif token[0].isdigit():
            out.append("NUM")
        else:
            out.append(token)
    return out


def fingerprints(tokens: list[str]) -> set[int]:
    """Winnowing (Schleimer et al.): the minimum hash of every window of k-grams."""
    grams = [
        int(
            hashlib.blake2b(" ".join(tokens[i : i + K_GRAM]).encode(), digest_size=8).hexdigest(),
            16,
        )
        for i in range(len(tokens) - K_GRAM + 1)
    ]
    if len(grams) <= WINDOW:
        return set(grams)
    return {min(grams[i : i + WINDOW]) for i in range(len(grams) - WINDOW + 1)}


def builtin_pairs(codes: Mapping[int, str]) -> list[dict[str, Any]]:
    prints = {u: fingerprints(normalize(c)) for u, c in codes.items()}
    users = sorted(u for u in prints if len(prints[u]) >= 2)
    out = []
    for i, a in enumerate(users):
        for b in users[i + 1 :]:
            common = len(prints[a] & prints[b])
            similarity = common / min(len(prints[a]), len(prints[b]))
            out.append({"a": a, "b": b, "similarity": round(similarity, 4)})
    return out


# JPlag ---------------------------------------------------------------------------------------


def _parse_csv(text: str) -> list[tuple[str, str, float]]:
    """JPlag's pairwise CSV: two submission names and similarity columns (0–1 or 0–100)."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [h.lower() for h in rows[0]]
    numeric = [i for i, h in enumerate(header) if "similarity" in h]
    column = next((i for i in numeric if "avg" in header[i] or "average" in header[i]), None)
    if column is None:
        column = numeric[0] if numeric else 2
    out = []
    for row in rows[1:]:
        if len(row) <= column:
            continue
        try:
            value = float(row[column])
        except ValueError:
            continue
        out.append((row[0], row[1], value / 100 if value > 1 else value))
    return out


def _find_csv(out_dir: Path) -> str:
    for path in out_dir.rglob("*.csv"):
        return path.read_text(encoding="utf-8", errors="replace")
    for archive in out_dir.rglob("*.jplag"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.filename.endswith(".csv") and info.file_size <= 10 * 1024**2:
                    return z.read(info).decode("utf-8", errors="replace")
    raise RuntimeError("JPlag wrote no CSV")


def jplag_pairs(codes: Mapping[int, str], jar: Path) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        submissions = root / "submissions"
        for user_id, code in codes.items():
            folder = submissions / f"u{user_id}"
            folder.mkdir(parents=True)
            (folder / "main.cpp").write_text(code, encoding="utf-8")
        out = root / "out"
        out.mkdir()
        java = shutil.which("java")
        if java is None:
            raise RuntimeError("java is not installed")
        subprocess.run(  # noqa: S603  # nosec B603
            [
                java,
                "-Xmx1g",
                "-jar",
                str(jar),
                "-l",
                "cpp",
                "-M",
                "RUN",
                "--csv-export",
                "-t",
                str(MIN_TOKENS),
                "-r",
                str(out / "result"),
                str(submissions),
            ],
            check=True,
            capture_output=True,
            timeout=JPLAG_TIMEOUT_S,
            cwd=out,
        )
        pairs = []
        for a, b, value in _parse_csv(_find_csv(out)):
            if a.startswith("u") and b.startswith("u"):
                ua, ub = sorted((int(a[1:]), int(b[1:])))
                pairs.append({"a": ua, "b": ub, "similarity": round(value, 4)})
        return pairs


Engine = Callable[[Mapping[int, str]], list[dict[str, Any]]]


def pick_engine() -> tuple[str, Engine]:
    jar = get_settings().jplag_jar
    if jar and Path(jar).is_file():
        return "jplag", lambda codes: jplag_pairs(codes, Path(jar))
    return "builtin", builtin_pairs


def latest_codes(db: Session, assessment_id: int, task_id: int) -> dict[int, str]:
    """Each student's last submission of the task in the assessment."""
    codes: dict[int, str] = {}
    for s in db.scalars(
        select(Submission)
        .where(Submission.assessment_id == assessment_id, Submission.task_id == task_id)
        .order_by(Submission.id)
    ):
        codes[s.user_id] = s.code
    return codes


def run_report(
    db: Session, report: SimilarityReport, engine: tuple[str, Engine] | None = None
) -> None:
    name, compare = engine or pick_engine()
    report.engine = name
    try:
        pairs = compare(latest_codes(db, report.assessment_id, report.task_id))
        report.pairs = sorted(pairs, key=lambda p: -p["similarity"])[:500]
        report.status = "done"
    except Exception as exc:  # a failed analysis must not stay pending
        report.status = "failed"
        report.error = f"{type(exc).__name__}: {exc}"[:1000]
    report.finished_at = datetime.now(UTC)
