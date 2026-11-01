"""Contest standings (ОТ-02): ICPC with penalty time, IOI with points for subtasks.

Pure functions over attempts, so the rules are tested without a database. An attempt's
time is counted from the participant's own start (a virtual participant has their own).
"""

from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass, field

from app.core.enums import Verdict


@dataclass(frozen=True)
class Attempt:
    user_id: int
    task_id: int
    elapsed_s: float  # from the participant's start
    verdict: str | None  # None while the submission is being judged
    score: float = 0.0  # IOI points of this submission (0–100)


@dataclass
class Cell:
    solved: bool = False
    wrong: int = 0  # rejected attempts before the accepted one (ICPC)
    minute: int | None = None  # minute of the accepted attempt (ICPC)
    score: float = 0.0  # best points (IOI)
    pending: int = 0  # attempts hidden by the freeze or still being judged
    tried: bool = False


@dataclass
class Row:
    user_id: int
    rank: int = 0
    solved: int = 0
    penalty: int = 0  # minutes (ICPC)
    score: float = 0.0  # points (IOI)
    cells: dict[int, Cell] = field(default_factory=dict)


def _hidden(attempt: Attempt, frozen_after_s: float | None, reveal: Set[int]) -> bool:
    if attempt.verdict is None:
        return True
    return (
        frozen_after_s is not None
        and attempt.elapsed_s >= frozen_after_s
        and attempt.user_id not in reveal
    )


def _visible(attempts: Iterable[Attempt], cutoff_s: float | None) -> list[Attempt]:
    """`cutoff_s`: a virtual participant sees the others as they were at the same moment."""
    return sorted(
        (a for a in attempts if cutoff_s is None or a.elapsed_s <= cutoff_s),
        key=lambda a: a.elapsed_s,
    )


def _rank(rows: list[Row], key: Mapping[int, tuple[float, ...]]) -> list[Row]:
    rows.sort(key=lambda r: (key[r.user_id], r.user_id))
    for i, row in enumerate(rows):
        if i > 0 and key[row.user_id] == key[rows[i - 1].user_id]:
            row.rank = rows[i - 1].rank  # a tie shares the place
        else:
            row.rank = i + 1
    return rows


def icpc(
    participants: Sequence[int],
    task_ids: Sequence[int],
    attempts: Iterable[Attempt],
    penalty_minutes: int = 20,
    frozen_after_s: float | None = None,
    cutoff_s: float | None = None,
    reveal: Set[int] = frozenset(),
) -> list[Row]:
    """More solved first, then less penalty: minutes of each accepted attempt plus
    `penalty_minutes` for every rejected attempt before it. A compilation error costs
    nothing; attempts after the acceptance are ignored."""
    rows = {u: Row(u, cells={t: Cell() for t in task_ids}) for u in participants}
    for attempt in _visible(attempts, cutoff_s):
        row = rows.get(attempt.user_id)
        cell = row.cells.get(attempt.task_id) if row else None
        if row is None or cell is None or cell.solved:
            continue
        cell.tried = True
        if _hidden(attempt, frozen_after_s, reveal):
            cell.pending += 1
        elif attempt.verdict == Verdict.OK.value:
            cell.solved = True
            cell.minute = int(attempt.elapsed_s // 60)
            row.solved += 1
            row.penalty += cell.minute + penalty_minutes * cell.wrong
        elif attempt.verdict != Verdict.CE.value:
            cell.wrong += 1
    key = {u: (-r.solved, r.penalty) for u, r in rows.items()}
    return _rank(list(rows.values()), key)


def ioi(
    participants: Sequence[int],
    task_ids: Sequence[int],
    attempts: Iterable[Attempt],
    frozen_after_s: float | None = None,
    cutoff_s: float | None = None,
    reveal: Set[int] = frozenset(),
) -> list[Row]:
    """The best submission of each problem counts; more points first."""
    rows = {u: Row(u, cells={t: Cell() for t in task_ids}) for u in participants}
    for attempt in _visible(attempts, cutoff_s):
        row = rows.get(attempt.user_id)
        cell = row.cells.get(attempt.task_id) if row else None
        if row is None or cell is None:
            continue
        cell.tried = True
        if _hidden(attempt, frozen_after_s, reveal):
            cell.pending += 1
        elif attempt.score > cell.score:
            cell.score = attempt.score
    for row in rows.values():
        row.score = round(sum(c.score for c in row.cells.values()), 2)
        row.solved = sum(1 for c in row.cells.values() if c.score >= 100 - 1e-9)
        for cell in row.cells.values():
            cell.solved = cell.score >= 100 - 1e-9
    key = {u: (-r.score,) for u, r in rows.items()}
    return _rank(list(rows.values()), key)


def submission_points(
    subtask_points: Mapping[str, int], results: Sequence[tuple[int, bool]]
) -> float:
    """IOI points of one submission from (subtask, passed) per test.

    With `subtask_points` a subtask gives its points only when all its tests pass;
    without them every test is worth the same share of 100."""
    if not results:
        return 0.0
    if not subtask_points:
        return round(100 * sum(1 for _, ok in results if ok) / len(results), 2)
    total = 0.0
    for subtask, points in subtask_points.items():
        tests = [ok for s, ok in results if str(s) == str(subtask)]
        if tests and all(tests):
            total += points
    return round(total, 2)
