"""Agreement between AI and teacher grades (ФТ-49 core; spec 16: Pearson, Spearman, MAE, MD).

The dissertation's baseline for Claude: MAE = 7,34; r = 0,647 (spec 16).
"""

import hashlib
import hmac
import math
from collections.abc import Sequence


def pseudonym(user_id: int, secret: str) -> str:
    """Stable research pseudonym: the same student always gets the same code."""
    digest = hmac.new(secret.encode(), f"student:{user_id}".encode(), hashlib.sha256).hexdigest()
    return f"S-{digest[:10]}"


def _check(a: Sequence[float], b: Sequence[float]) -> None:
    if len(a) != len(b):
        raise ValueError("series must have the same length")


def mae(ai: Sequence[float], teacher: Sequence[float]) -> float | None:
    _check(ai, teacher)
    if not ai:
        return None
    return sum(abs(x - y) for x, y in zip(ai, teacher, strict=True)) / len(ai)


def mean_difference(ai: Sequence[float], teacher: Sequence[float]) -> float | None:
    """MD = mean(AI − teacher): positive when the AI grades higher."""
    _check(ai, teacher)
    if not ai:
        return None
    return sum(x - y for x, y in zip(ai, teacher, strict=True)) / len(ai)


def pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    _check(a, b)
    n = len(a)
    if n < 2:
        return None
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def _ranks(values: Sequence[float]) -> list[float]:
    """Average ranks for ties."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    _check(a, b)
    return pearson(_ranks(a), _ranks(b))


def agreement(ai: Sequence[float], teacher: Sequence[float]) -> dict[str, float | int | None]:
    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 4)

    return {
        "n": len(ai),
        "pearson": rounded(pearson(ai, teacher)),
        "spearman": rounded(spearman(ai, teacher)),
        "mae": rounded(mae(ai, teacher)),
        "md": rounded(mean_difference(ai, teacher)),
    }
