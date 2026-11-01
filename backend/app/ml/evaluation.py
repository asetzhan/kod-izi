"""Comparing Code-DKT with BKT (ФТ-40): AUC of predicting the next attempt's correctness.

Plain Python, no torch: the comparison report and the fallback decision use it too.
"""

import random
from collections.abc import Sequence as Seq

from app.ml.dataset import Sequence
from app.services import bkt


def auc(labels: Seq[bool], scores: Seq[float]) -> float:
    """Area under the ROC curve (Mann–Whitney), ties counted half. 0,5 is chance."""
    positives = [s for label, s in zip(labels, scores, strict=True) if label]
    negatives = [s for label, s in zip(labels, scores, strict=True) if not label]
    if not positives or not negatives:
        return 0.5
    ranked = sorted((s, label) for s, label in zip(scores, labels, strict=True))
    rank_sum = 0.0
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        average = (i + j) / 2 + 1
        rank_sum += sum(average for k in range(i, j + 1) if ranked[k][1])
        i = j + 1
    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def split(
    sequences: list[Sequence], test_share: float = 0.3, seed: int = 5
) -> tuple[list[Sequence], list[Sequence]]:
    """By student, so a student's attempts are never on both sides."""
    shuffled = sequences[:]
    random.Random(seed).shuffle(shuffled)  # noqa: S311  # nosec B311 (data split, not security)
    cut = int(len(shuffled) * (1 - test_share))
    return shuffled[:cut], shuffled[cut:]


def fit_bkt(train: list[Sequence], components: int) -> list[bkt.BktParams]:
    """BKT parameters per component, fitted on the training students."""
    out = []
    for kc in range(components):
        observed = [[s.correct for s in q.steps if s.kc == kc] for q in train]
        observed = [o for o in observed if o]
        out.append(bkt.fit(observed) if observed else bkt.BktParams())
    return out


def bkt_scores(test: list[Sequence], params: list[bkt.BktParams]) -> tuple[list[bool], list[float]]:
    """P(correct) predicted by BKT before each attempt from the second on (the same
    attempts Code-DKT is scored on), and what happened."""
    labels, scores = [], []
    for sequence in test:
        learned = [p.p_init for p in params]
        for t, step in enumerate(sequence.steps):
            p = params[step.kc]
            if t > 0:
                scores.append(
                    learned[step.kc] * (1 - p.p_slip) + (1 - learned[step.kc]) * p.p_guess
                )
                labels.append(step.correct)
            learned[step.kc] = bkt.update(learned[step.kc], step.correct, p)
    return labels, scores
