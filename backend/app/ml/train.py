"""Train Code-DKT and compare it with BKT (ФТ-40). Run with `make train-dkt`.

The model is saved with its AUC and BKT's AUC on held-out students; the application uses
it only if it is better by `code_dkt_min_gain` and was trained on real data
(services/student_model.py). A Markdown report is written for the dissertation.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ml import code_dkt, evaluation
from app.ml.dataset import Sequence
from app.ml.features import FEATURE_DIM

SYNTHETIC_NOTE = "Симуляцияланған деректерде оқытылған модель жүйеде ешқашан қолданылмайды."


def run(
    components: list[int],
    sequences: list[Sequence],
    out_dir: Path,
    synthetic: bool,
    epochs: int = 8,
) -> dict[str, Any]:
    train, test = evaluation.split(sequences)
    params = evaluation.fit_bkt(train, len(components))
    bkt_auc = evaluation.auc(*evaluation.bkt_scores(test, params))
    model = code_dkt.train(train, len(components), epochs=epochs)
    dkt_auc = evaluation.auc(*code_dkt.scores(model, test))
    meta = code_dkt.Meta(
        components=components,
        hidden=model.lstm.hidden_size,
        auc=round(dkt_auc, 4),
        bkt_auc=round(bkt_auc, 4),
        trained_on=len(train),
        synthetic=synthetic,
    )
    code_dkt.save(model, meta, out_dir)
    return {
        "students": len(sequences),
        "train": len(train),
        "test": len(test),
        "attempts": sum(len(q.steps) for q in sequences),
        "components": len(components),
        "bkt_auc": meta.bkt_auc,
        "code_dkt_auc": meta.auc,
        "synthetic": synthetic,
        "epochs": epochs,
    }


def report_markdown(result: dict[str, Any]) -> str:
    source = (
        "симуляцияланған деректер (`app/ml/dataset.synthetic`): пилоттан бұрын скрипттерді "
        "тексеру үшін. Нақты нәтиже пилот деректерімен қайта есептеледі."
        if result["synthetic"]
        else "пилот деректері (дерекқордан)"
    )
    better = result["code_dkt_auc"] > result["bkt_auc"]
    return f"""# Code-DKT пен BKT-ны салыстыру (ФТ-40)

Күні: {datetime.now(UTC):%Y-%m-%d}. Дереккөз: {source}

Міндет: студенттің келесі әрекетінің дұрыс болатынын болжау. Өлшем: ROC AUC, тест
студенттерінде (оқытуға кірмеген {result["test"]} студент). Екі модель де әр студенттің
екінші әрекетінен бастап бағаланады.

| Көрсеткіш | Мәні |
| --- | --- |
| Студенттер (оқыту / тест) | {result["train"]} / {result["test"]} |
| Әрекеттер | {result["attempts"]} |
| Білім компоненттері | {result["components"]} |
| BKT, AUC | {result["bkt_auc"]} |
| Code-DKT, AUC | {result["code_dkt_auc"]} |
| Code-DKT дәуірлері (epochs) | {result["epochs"]} |

Қорытынды: Code-DKT {"BKT-дан жақсы" if better else "BKT-дан жақсы емес"}.
{SYNTHETIC_NOTE if result["synthetic"] else ""}
Жүйе Code-DKT-ны тек нақты деректерде оқытылған және AUC бойынша BKT-дан кемінде
`CODE_DKT_MIN_GAIN` (әдепкі 0,02) жоғары болғанда қолданады. Әйтпесе BKT қолданылады.

Модель: LSTM (жасырын қабат 64), кіріс — білім компоненті мен дұрыстықтың one-hot
векторы және кодтың {FEATURE_DIM} белгісі (12 метрика мен токендер жұптарының 32 себеттік
хэштелген гистограммасы, `app/ml/features.py`). Оқыту: Adam, келесі әрекеттің
бинарлық кросс-энтропиясы. Есептеу CPU-да (Q-19).
"""


def write_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_markdown(result), encoding="utf-8")
