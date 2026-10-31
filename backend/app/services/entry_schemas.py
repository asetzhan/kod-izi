"""Shapes of component entry values a teacher may write (spec 6).

Values are JSON, but some are read later by code (results, LLM prompts), so the known
ones are checked; unknown keys must still be small JSON objects.
"""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

from app.services.rubrics import CRITERIA_CODES

Short = Annotated[str, Field(max_length=2000)]
MAX_JSON_CHARS = 50_000


class Lesson(BaseModel):
    title: Annotated[str, Field(max_length=300)]
    url: Annotated[str, Field(max_length=500, pattern=r"^https?://")]


class Goals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: Short
    learning_outcomes: list[Annotated[str, Field(max_length=500)]] = Field(max_length=20)
    knowledge_components: list[Annotated[str, Field(max_length=300)]] = Field(
        default_factory=list, max_length=50
    )
    lessons: list[Lesson] = Field(default_factory=list, max_length=50)


class LevelTexts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: Short
    mid: Short
    high: Short


class Descriptors(RootModel[dict[str, LevelTexts]]):
    pass


class CriterionLine(BaseModel):
    code: Literal[
        "understanding", "algorithm", "correctness", "code_quality", "debugging", "explanation"
    ]
    level: Literal["low", "mid", "high"]
    interpretation: Short = ""


class Interpretation(BaseModel):
    model_config = ConfigDict(extra="allow")

    criteria: list[CriterionLine] = Field(max_length=6)
    feedback: Annotated[str, Field(max_length=10_000)] = ""
    next_step: Short = ""


SCHEMAS: dict[tuple[int, str], type[BaseModel]] = {
    (1, "goals"): Goals,
    (2, "descriptors"): Descriptors,
    (5, "interpretation"): Interpretation,
}


def check_value(component: int, key: str, value: Any) -> Any:
    """Return the validated value or raise ValueError with a readable message."""
    if len(json.dumps(value, ensure_ascii=False)) > MAX_JSON_CHARS:
        raise ValueError("value is too large")
    schema = SCHEMAS.get((component, key))
    if schema is None:
        if not isinstance(value, dict):
            raise ValueError("value must be a JSON object")
        return value
    try:
        checked = schema.model_validate(value).model_dump()
    except ValidationError as exc:
        raise ValueError("; ".join(f"{e['loc']}: {e['msg']}" for e in exc.errors()[:5])) from None
    if schema is Descriptors and set(checked) != set(CRITERIA_CODES):
        raise ValueError(f"descriptors must cover exactly {list(CRITERIA_CODES)}")
    return checked
