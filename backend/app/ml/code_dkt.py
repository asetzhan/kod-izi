"""Code-DKT (ФТ-40): Deep Knowledge Tracing with code features, in PyTorch (CPU, Q-19).

The input of step t is the component and correctness of attempt t together with the code
features of that attempt; an LSTM gives, after each step, the probability of a correct
next attempt for every component. Training minimises the cross-entropy of the predicted
next attempt. This module is imported only when torch is installed.
"""

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
from torch import nn

from app.ml.dataset import Sequence
from app.ml.features import FEATURE_DIM

MODEL_FILE = "code_dkt.pt"
META_FILE = "code_dkt.json"


@dataclass
class Meta:
    components: list[int]  # knowledge component ids, in the model's order
    hidden: int
    auc: float
    bkt_auc: float
    trained_on: int  # number of students
    synthetic: bool


class CodeDKT(nn.Module):
    def __init__(self, components: int, hidden: int = 64) -> None:
        super().__init__()
        self.components = components
        self.lstm = nn.LSTM(2 * components + FEATURE_DIM, hidden, batch_first=True)
        self.out = nn.Linear(hidden, components)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden, _ = self.lstm(x)
        return torch.sigmoid(self.out(hidden))


def _inputs(sequence: Sequence, components: int) -> torch.Tensor:
    rows = []
    for step in sequence.steps:
        one_hot = [0.0] * (2 * components)
        one_hot[step.kc + (components if step.correct else 0)] = 1.0
        rows.append(one_hot + step.features)
    return torch.tensor(rows, dtype=torch.float32)


def train(
    sequences: list[Sequence],
    components: int,
    epochs: int = 8,  # more overfits on pilot-sized data (docs/reports/code-dkt-vs-bkt.md)
    hidden: int = 64,
    seed: int = 3,
    lr: float = 0.01,
) -> CodeDKT:
    torch.manual_seed(seed)
    torch.set_num_threads(1)  # reproducible reports: same data, same AUC
    rng = random.Random(seed)  # noqa: S311  # nosec B311 (shuffling, not security)
    model = CodeDKT(components, hidden)
    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()
    data = [q for q in sequences if len(q.steps) >= 2]
    for _ in range(epochs):
        rng.shuffle(data)
        for sequence in data:
            x = _inputs(sequence, components).unsqueeze(0)
            predictions = model(x)[0, :-1]  # after step t, for step t+1
            targets = torch.tensor([float(s.correct) for s in sequence.steps[1:]])
            index = torch.tensor([s.kc for s in sequence.steps[1:]])
            chosen = predictions.gather(1, index.unsqueeze(1)).squeeze(1)
            loss = loss_fn(chosen, targets)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
    return model


@torch.no_grad()
def scores(model: CodeDKT, sequences: list[Sequence]) -> tuple[list[bool], list[float]]:
    """P(correct) predicted before each attempt from the second on, and what happened."""
    model.eval()
    labels, out = [], []
    for sequence in sequences:
        if len(sequence.steps) < 2:
            continue
        predictions = model(_inputs(sequence, model.components).unsqueeze(0))[0, :-1]
        for t, step in enumerate(sequence.steps[1:]):
            labels.append(step.correct)
            out.append(float(predictions[t, step.kc]))
    return labels, out


@torch.no_grad()
def mastery(model: CodeDKT, sequence: Sequence) -> list[float]:
    """P(correct next attempt) per component after the student's last attempt."""
    model.eval()
    if not sequence.steps:
        return [0.0] * model.components
    predictions = model(_inputs(sequence, model.components).unsqueeze(0))[0, -1]
    return [float(p) for p in predictions]


def save(model: CodeDKT, meta: Meta, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), directory / MODEL_FILE)
    (directory / META_FILE).write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")


def load(directory: Path) -> tuple[CodeDKT, Meta]:
    meta = Meta(**json.loads((directory / META_FILE).read_text(encoding="utf-8")))
    model = CodeDKT(len(meta.components), meta.hidden)
    # weights_only: the file holds tensors only, never pickled objects.
    model.load_state_dict(torch.load(directory / MODEL_FILE, weights_only=True))
    return model, meta
