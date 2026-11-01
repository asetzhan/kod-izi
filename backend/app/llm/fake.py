"""Deterministic provider for tests and development: no network access (ФТ-46).

Answers depend only on the request, never on chance. For the assessment prompt it builds
a valid grade from the test results alone, so instructions hidden in the student's code,
explanation or book fragments cannot change it.
"""

import hashlib
import json
import math
import re
from typing import Any

from app.llm.base import LLMRequest, LLMResponse
from app.models.analysis import EMBEDDING_DIM

WORD = re.compile(r"\w+", re.UNICODE)


def _sample(schema: dict[str, Any]) -> Any:
    """Smallest value that satisfies a simple JSON schema."""
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {name: _sample(sub) for name, sub in schema.get("properties", {}).items()}
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    return "fake"


def fake_grade(data_blocks: dict[str, str]) -> dict[str, Any]:
    """A plausible grade derived from the test results only."""
    try:
        tests = json.loads(data_blocks.get("test_results", "{}"))
    except ValueError:
        tests = {}
    passed, total = int(tests.get("tests_passed", 0)), max(int(tests.get("tests_total", 1)), 1)
    share = passed / total
    level = "high" if share == 1 else "mid" if share >= 0.5 else "low"
    fragments = json.loads(data_blocks.get("book_fragments", "[]") or "[]")
    book_ref = fragments[0]["ref"] if fragments else None
    criteria = []
    for code in (
        "understanding",
        "algorithm",
        "correctness",
        "code_quality",
        "debugging",
        "explanation",
    ):
        evidence = [{"type": "test", "ref": "tests", "quote": f"{passed}/{total}"}]
        if book_ref:
            evidence.append({"type": "book", "ref": book_ref, "quote": fragments[0]["text"][:80]})
        criteria.append({"code": code, "level": level, "evidence": evidence, "confidence": 0.5})
    return {
        "criteria": criteria,
        "components": {"F": round(share * 100), "E": 50, "A": 50},
        "interpretation": "fake interpretation",
        "feedback": "fake feedback",
        "next_step": "fake next step",
        "flags": [] if book_ref else ["no_book_fragment"],
    }


def fake_embedding(text: str) -> list[float]:
    """Hashed bag of words: texts sharing words get close vectors."""
    vector = [0.0] * EMBEDDING_DIM
    for word in WORD.findall(text.lower()):
        index = int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_DIM
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeLLMProvider:
    name = "fake"

    def complete(self, request: LLMRequest) -> LLMResponse:
        canonical = json.dumps(
            {"system": request.system, "data": request.data_blocks}, sort_keys=True
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        if request.prompt_version.startswith("assessment-"):
            text = json.dumps(fake_grade(request.data_blocks), ensure_ascii=False)
        elif request.prompt_version.startswith("olympiad-hint-"):
            text = "Жауап бойынша екілік іздеуді қарастырыңыз: тексеру функциясы монотонды."
        elif request.prompt_version.startswith("assistant-"):
            text = "Кітаптың тиісті бөлімін қараңыз және шекаралық жағдайларды тексеріңіз."
        elif request.response_schema is not None:
            text = json.dumps(_sample(request.response_schema), sort_keys=True)
        else:
            text = json.dumps({"fake": True, "input_sha256": digest}, sort_keys=True)
        return LLMResponse(
            text=text,
            model=request.model or "fake-model",
            prompt_version=request.prompt_version,
            input_tokens=len(canonical.split()),
            output_tokens=len(text.split()),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [fake_embedding(t) for t in texts]
