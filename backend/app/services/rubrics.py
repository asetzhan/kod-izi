"""Rubric of a course (ФТ-13, ФТ-15), filled from seed/rubric_default.json."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Rubric, RubricCriterion

CRITERIA_CODES = (
    "understanding",
    "algorithm",
    "correctness",
    "code_quality",
    "debugging",
    "explanation",
)

# Q-10: the 0–100 scales used in the dissertation's experiment are not in the text.
# These descriptions are a draft the customer will replace; they can be edited per course.
DEFAULT_COMPONENT_SCALES = {
    "F": "Функционалдық дұрыстық, 0–100: жасырын тесттердің өту үлесі мен вердиктер "
    "(TLE, MLE, RE) бойынша.",
    "E": "Шешімді түсіндіру сапасы, 0–100: түсіндірме мен өз коды бойынша сұрақтарға "
    "жауаптар алгоритмнің логикасын, таңдау себебін және тиімділігін қаншалықты дәл "
    "ашады (жоба, Q-10).",
    "A": "GenAI құралдарын пайдалану деңгейі, 0–100: түсіну, жоспарлау, іске асыру, "
    "бақылау және қорғау кезеңдерінде GenAI-ді саналы қолдану (диссертация, 3-тарау, "
    "3-кесте). AI-көмекшіге тыйым салынса немесе студент қолданбаса, AI журналы бос "
    "екенін көрсет (жоба, Q-10).",
}


def default_rubric_data() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (get_settings().seed_dir / "rubric_default.json").read_text(encoding="utf-8")
    )
    return data


def get_or_create_rubric(db: Session, course_id: int) -> Rubric:
    rubric = db.scalar(select(Rubric).where(Rubric.course_id == course_id))
    if rubric is not None:
        return rubric
    data = default_rubric_data()
    weights = data["final_score"]["weights"]
    rubric = Rubric(
        course_id=course_id,
        weight_f=weights["F"],
        weight_e=weights["E"],
        weight_a=weights["A"],
        component_scales=dict(DEFAULT_COMPONENT_SCALES),
        criteria=[
            RubricCriterion(
                code=c["code"],
                position=i,
                name=c["name_kk"],
                indicators=c["indicators"],
                data_sources=c["data_sources"],
                descriptor_low=c["descriptors"]["low"],
                descriptor_mid=c["descriptors"]["mid"],
                descriptor_high=c["descriptors"]["high"],
            )
            for i, c in enumerate(data["criteria"], start=1)
        ],
    )
    db.add(rubric)
    db.flush()
    return rubric


def weights(rubric: Rubric) -> dict[str, float]:
    return {"F": rubric.weight_f, "E": rubric.weight_e, "A": rubric.weight_a}


def final_score(rubric: Rubric, components: dict[str, float]) -> float:
    """ФТ-15: S = wF·F + wE·E + wA·A (default 0,3626 / 0,3641 / 0,2733)."""
    w = weights(rubric)
    return round(sum(w[k] * components[k] for k in ("F", "E", "A")), 2)


def rubric_block(rubric: Rubric) -> str:
    return json.dumps(
        {
            "levels": ["low", "mid", "high"],
            "criteria": [
                {
                    "code": c.code,
                    "name": c.name,
                    "indicators": c.indicators,
                    "descriptors": {
                        "low": c.descriptor_low,
                        "mid": c.descriptor_mid,
                        "high": c.descriptor_high,
                    },
                }
                for c in rubric.criteria
            ],
            "component_scales": rubric.component_scales,
        },
        ensure_ascii=False,
    )
