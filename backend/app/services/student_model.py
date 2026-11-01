"""Which student model gives the mastery probabilities (ФТ-39, ФТ-40).

Code-DKT is used for a course only when torch is installed, a trained model for that
course exists, and its AUC beat BKT by at least `code_dkt_min_gain` on held-out students.
In every other case (no model, a broken file, a weaker model) the system falls back to BKT.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import bkt

log = logging.getLogger(__name__)


def model_dir(course_id: int) -> Path:
    return get_settings().code_dkt_dir / f"course-{course_id}"


def code_dkt_usable(course_id: int) -> bool:
    meta = model_dir(course_id) / "code_dkt.json"
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        gain = float(data["auc"]) - float(data["bkt_auc"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if data.get("synthetic") or gain < get_settings().code_dkt_min_gain:
        return False  # a model trained on simulated data never grades real students
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def _stamp(course_id: int) -> tuple[int, int, int, int]:
    """Both files' change time and size: a new model or new metadata reloads."""
    model = (model_dir(course_id) / "code_dkt.pt").stat()
    meta = (model_dir(course_id) / "code_dkt.json").stat()
    return (model.st_mtime_ns, model.st_size, meta.st_mtime_ns, meta.st_size)


@lru_cache(maxsize=16)
def _loaded(course_id: int, stamp: tuple[int, int, int, int]) -> Any:
    from app.ml import code_dkt

    return code_dkt.load(model_dir(course_id))


def student_model(db: Session, course_id: int, user_id: int) -> tuple[str, list[dict[str, Any]]]:
    """("bkt" | "code_dkt", the components with P(mastered)) for one student."""
    rows = bkt.student_model(db, course_id, user_id)
    if not code_dkt_usable(course_id):
        return "bkt", rows
    try:
        from app.ml import code_dkt, dataset

        model, meta = _loaded(course_id, _stamp(course_id))
        # A savepoint: a failed query here must not break the rest of the request.
        with db.begin_nested():
            components, sequences = dataset.from_database(db, course_id, user_id)
        if components != meta.components:
            return "bkt", rows  # the course changed since training: retrain first
        mine = sequences[0] if sequences else dataset.Sequence(user_id)
        probabilities = dict(zip(meta.components, code_dkt.mastery(model, mine), strict=True))
    except Exception:  # any problem with the model: BKT, never an error for the student
        log.warning("Code-DKT unavailable for course %s, using BKT", course_id, exc_info=True)
        return "bkt", rows
    threshold = bkt.get_params(db).threshold
    for row in rows:
        p = probabilities.get(row["kc_id"])
        if p is not None and row["attempts"]:
            row["p_learned"] = round(p, 4)
            row["mastered"] = p >= threshold
    return "code_dkt", rows
