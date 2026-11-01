"""ФТ-40: Code-DKT — features, evaluation, training, and the fallback to BKT."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.ml import evaluation
from app.ml.dataset import GOOD, POOR, synthetic
from app.ml.features import FEATURE_DIM, code_features
from app.services.student_model import code_dkt_usable, model_dir
from tests.workspace_helpers import SOLUTION, _open, _submit


def test_ft40_code_features_are_a_fixed_normalised_vector() -> None:
    good = code_features(GOOD, {"warnings": [], "metrics": {"max_ccn": 2}}, {"compile_errors": 0})
    poor = code_features(
        POOR, {"warnings": [1, 2, 3], "metrics": {"max_ccn": 9}}, {"compile_errors": 3}
    )
    assert len(good) == len(poor) == FEATURE_DIM
    assert all(0.0 <= v <= 1.0 for v in good + poor)
    assert good != poor and code_features("") == code_features("")


def test_ft40_auc_is_the_ranking_probability() -> None:
    assert evaluation.auc([True, False], [0.9, 0.1]) == 1.0
    assert evaluation.auc([True, False], [0.1, 0.9]) == 0.0
    assert evaluation.auc([True, False, True, False], [0.5, 0.5, 0.5, 0.5]) == 0.5
    assert evaluation.auc([True, True], [0.2, 0.3]) == 0.5  # one class only


def _meta(directory: Path, **values: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "components": [1],
        "hidden": 8,
        "auc": 0.8,
        "bkt_auc": 0.7,
        "trained_on": 50,
        "synthetic": False,
    }
    (directory / "code_dkt.json").write_text(json.dumps({**data, **values}), encoding="utf-8")


def test_ft40_falls_back_to_bkt_without_a_good_real_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "code_dkt_dir", tmp_path)
    assert not code_dkt_usable(1)  # no model
    _meta(model_dir(1), auc=0.71, bkt_auc=0.70)
    assert not code_dkt_usable(1)  # better by less than the minimum gain
    _meta(model_dir(1), synthetic=True)
    assert not code_dkt_usable(1)  # trained on simulated data
    (model_dir(1) / "code_dkt.json").write_text("{broken", encoding="utf-8")
    assert not code_dkt_usable(1)  # a broken file


def test_ft40_progress_uses_bkt_when_no_model_and_says_so(
    client: TestClient,
    ws: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "code_dkt_dir", tmp_path)
    _submit(client, ws, _open(client, ws), SOLUTION)
    data = client.get(
        f"/api/my/progress?course_id={ws['course']['id']}", headers=ws["student"]
    ).json()
    assert data["trajectory"]["engine"] == "bkt" and data["next"]["engine"] == "bkt"


def test_ft40_code_dkt_trains_and_beats_bkt_on_test_data(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from app.ml import code_dkt, train

    sequences = synthetic(students=200, steps=12)
    result = train.run(list(range(1, 6)), sequences, tmp_path, synthetic=True)
    assert result["code_dkt_auc"] > result["bkt_auc"] > 0.5
    model, meta = code_dkt.load(tmp_path)
    assert meta.synthetic and meta.components == [1, 2, 3, 4, 5]
    probabilities = code_dkt.mastery(model, sequences[0])
    assert len(probabilities) == 5 and all(0 <= p <= 1 for p in probabilities)
    report = train.report_markdown(result)
    assert "BKT, AUC" in report and "жүйеде ешқашан қолданылмайды" in report
