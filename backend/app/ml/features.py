"""Features of one attempt for Code-DKT (ФТ-40): code metrics and a code representation.

Code-DKT (Shi et al., 2022) adds an embedding of the submitted code to Deep Knowledge
Tracing. Here the code is represented by a hashed histogram of its normalized tokens
(identifiers and literals abstracted, as in the similarity check), plus metrics the system
already computes: size, cyclomatic complexity, analyser warnings, compile errors and the
time spent fixing them (ФТ-32, ФТ-33). No torch here: the features are plain floats.
"""

import hashlib
import math
from collections.abc import Mapping
from itertools import pairwise
from typing import Any

from app.services.similarity import normalize

TOKEN_BUCKETS = 32
METRICS = (
    "lines",
    "tokens",
    "max_ccn",
    "warnings",
    "compile_errors",
    "repeated_compile_errors",
    "fix_minutes",
    "attempts",
    "loops",
    "functions",
    "uses_stl",
    "recursion",
)
FEATURE_DIM = len(METRICS) + TOKEN_BUCKETS


def _bucket(token: str) -> int:
    return int(hashlib.blake2b(token.encode(), digest_size=4).hexdigest(), 16) % TOKEN_BUCKETS


def _squash(value: float, scale: float) -> float:
    """log-scaled into [0, 1) so that large values do not dominate."""
    return 1 - math.exp(-max(value, 0.0) / scale)


def code_features(
    code: str,
    static_analysis: Mapping[str, Any] | None = None,
    process: Mapping[str, Any] | None = None,
) -> list[float]:
    """A fixed-length vector of FEATURE_DIM floats in [0, 1]."""
    tokens = normalize(code)
    analysis = static_analysis or {}
    metrics = analysis.get("metrics", {}) if isinstance(analysis.get("metrics"), dict) else {}
    proc = process or {}
    lines = [line for line in code.splitlines() if line.strip()]
    names = set(tokens)
    raw = {
        "lines": _squash(len(lines), 40),
        "tokens": _squash(len(tokens), 300),
        "max_ccn": _squash(float(metrics.get("max_ccn") or 0), 10),
        "warnings": _squash(len(analysis.get("warnings", []) or []), 5),
        "compile_errors": _squash(float(proc.get("compile_errors") or 0), 3),
        "repeated_compile_errors": _squash(float(proc.get("repeated_compile_errors") or 0), 2),
        "fix_minutes": _squash(float(proc.get("fix_minutes") or 0), 15),
        "attempts": _squash(float(proc.get("attempts") or 0), 5),
        "loops": _squash(sum(1 for t in tokens if t in ("for", "while")), 3),
        "functions": _squash(code.count(") {") + code.count("){"), 4),
        "uses_stl": 1.0 if names & {"vector", "map", "set", "string"} else 0.0,
        "recursion": 0.0,
    }
    histogram = [0.0] * TOKEN_BUCKETS
    for a, b in pairwise(tokens):
        histogram[_bucket(f"{a} {b}")] += 1
    total = sum(histogram) or 1.0
    return [raw[name] for name in METRICS] + [h / total for h in histogram]
