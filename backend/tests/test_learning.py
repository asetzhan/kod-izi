"""Stage 6b part 2: ФТ-21, ФТ-23, ФТ-30, ФТ-37, ФТ-39, ФТ-44, ФТ-45."""

import io
import json
import random
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.db.context import set_system
from app.jobs import get_similarity_enqueue
from app.main import app
from app.models import (
    Chunk,
    GroupMember,
    KnowledgeComponent,
    Material,
    MaterialVersion,
    SimilarityReport,
    Task,
    TaskKnowledgeComponent,
    Topic,
)
from app.models.analysis import EMBEDDING_DIM
from app.services import bkt
from app.services.extract import extract_pdf
from app.services.similarity import _parse_csv, builtin_pairs, run_report
from tests.conftest import MakeUser, School, login
from tests.llm_helpers import ScriptedProvider
from tests.workspace_helpers import SOLUTION, _open, _submit

PARAMS = bkt.BktParams(p_init=0.2, p_transit=0.15, p_slip=0.1, p_guess=0.2)


# BKT (ФТ-39) --------------------------------------------------------------------------------


def test_ft39_bkt_update_follows_the_standard_formula() -> None:
    # correct: 0,2·0,9 / (0,2·0,9 + 0,8·0,2) = 0,5294; then + 0,4706·0,15 = 0,6
    assert bkt.update(0.2, True, PARAMS) == pytest.approx(0.6, abs=1e-4)
    # wrong: 0,2·0,1 / (0,02 + 0,8·0,8) = 0,0303; then + 0,9697·0,15 = 0,1758
    assert bkt.update(0.2, False, PARAMS) == pytest.approx(0.17576, abs=1e-4)
    history = bkt.trace([True] * 6, PARAMS)
    assert history == sorted(history) and history[-1] >= 0.95  # mastered after a run
    assert bkt.trace([True, True, False], PARAMS)[-1] < bkt.trace([True, True], PARAMS)[-1]


def test_ft39_bkt_fit_recovers_parameters_from_test_data() -> None:
    """Simulated students with known parameters: the fit must find them again."""
    truth = bkt.BktParams(p_init=0.1, p_transit=0.3, p_slip=0.1, p_guess=0.2)
    rng = random.Random(7)  # noqa: S311 (simulated data, not security)
    sequences = []
    for _ in range(300):
        learned = rng.random() < truth.p_init
        sequence = []
        for _ in range(8):
            if learned:
                sequence.append(rng.random() >= truth.p_slip)
            else:
                sequence.append(rng.random() < truth.p_guess)
            learned = learned or rng.random() < truth.p_transit
        sequences.append(sequence)
    fitted = bkt.fit(sequences)
    assert abs(fitted.p_transit - truth.p_transit) <= 0.1
    assert abs(fitted.p_slip - truth.p_slip) <= 0.1
    assert abs(fitted.p_guess - truth.p_guess) <= 0.1
    assert bkt.log_likelihood(sequences, fitted) >= bkt.log_likelihood(sequences, PARAMS)


# Student model, next task, trajectory through the API (ФТ-39, ФТ-44, ФТ-45) ---------------


@pytest.fixture
def modelled(client: TestClient, ws: dict[str, Any], db: Session) -> dict[str, Any]:
    """The workspace course with a topic, two knowledge components and a second task."""
    topic = Topic(course_id=ws["course"]["id"], code="1.4", title="Шарттар", position=1)
    db.add(topic)
    db.flush()
    parity = KnowledgeComponent(topic_id=topic.id, code="cond.parity", name="Жұптылық", position=1)
    loops = KnowledgeComponent(topic_id=topic.id, code="loop.for", name="for циклі", position=2)
    db.add_all([parity, loops])
    db.flush()
    db.add(TaskKnowledgeComponent(task_id=ws["task"]["id"], knowledge_component_id=parity.id))
    extra = client.post(
        "/api/tasks",
        headers=ws["teacher"],
        json={
            "course_id": ws["course"]["id"],
            "title": "Тағы бір тапсырма",
            "statement_md": "Print EVEN or ODD.",
            "reference_solution": SOLUTION,
            "tests": [{"input": "4\n", "expected_output": "EVEN\n", "is_hidden": False}],
        },
    ).json()
    features = {"knowledge_actions": 0, "algorithm_freedom": 0, "edge_cases": 1, "justification": 0}
    client.put(
        f"/api/tasks/{extra['id']}/level", headers=ws["teacher"], json={"features": features}
    )
    client.post(f"/api/tasks/{extra['id']}/approve", headers=ws["teacher"])
    db.add(TaskKnowledgeComponent(task_id=extra["id"], knowledge_component_id=parity.id))
    db.flush()
    return {**ws, "topic": topic, "parity": parity, "loops": loops, "extra": extra["id"]}


def test_ft39_ft44_ft45_model_next_task_and_trajectory(
    client: TestClient, modelled: dict[str, Any], school: School
) -> None:
    ws = modelled
    _submit(client, ws, _open(client, ws), "// fake:WA\n" + SOLUTION)
    mine = client.get(f"/api/my/progress?course_id={ws['course']['id']}", headers=ws["student"])
    assert mine.status_code == 200
    data = mine.json()
    parity = next(c for c in data["trajectory"]["components"] if c["code"] == "cond.parity")
    assert parity["attempts"] == 1 and parity["p_learned"] < PARAMS.p_init + 0.01
    assert data["next"]["weak_components"][0]["code"] == "cond.parity"
    assert data["next"]["tasks"] == []  # the teacher gives the task (ФТ-05)

    url = f"/api/courses/{ws['course']['id']}/students/{school['student_a'].id}/progress"
    teacher_view = client.get(url, headers=ws["teacher"]).json()
    assert [t["id"] for t in teacher_view["next"]["tasks"]] == [ws["extra"]]
    assert teacher_view["next"]["target_level"] == "I"
    other = login(client, school["teacher_b"].email)
    assert client.get(url, headers=other).status_code == 403


def test_ft39_admin_fits_and_saves_bkt_parameters(
    client: TestClient, modelled: dict[str, Any], school: School
) -> None:
    ws = modelled
    _submit(client, ws, _open(client, ws))
    admin = login(client, school["admin"].email)
    fitted = client.post(f"/api/courses/{ws['course']['id']}/bkt/fit", headers=admin).json()
    assert fitted["sequences"] == 1 and 0 <= fitted["params"]["p_slip"] <= 0.5
    saved = client.put(
        "/api/settings/bkt", headers=admin, json={**fitted["params"], "threshold": 0.9}
    )
    assert (
        saved.status_code == 200
        and client.get("/api/settings/bkt", headers=admin).json()["threshold"] == 0.9
    )
    assert (
        client.put("/api/settings/bkt", headers=ws["teacher"], json=fitted["params"]).status_code
        == 403
    )


# LLM drafts (ФТ-21) and extraction (ФТ-23) --------------------------------------------------


def _draft_answer(solution: str) -> str:
    return json.dumps(
        {
            "title": "Сандардың қосындысы",
            "statement": "Бір сан берілген, оны шығарыңыз.",
            "input_format": "Бір бүтін сан.",
            "output_format": "Сол сан.",
            "reference_solution": solution,
            "tests": ["1\n", "42\n", "-7\n"],
        },
        ensure_ascii=False,
    )


def test_ft21_llm_draft_gets_answers_from_the_reference_solution_in_the_judge(
    client: TestClient, modelled: dict[str, Any], db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = modelled
    provider = ScriptedProvider([_draft_answer("// fake:ECHO\nint main() {}")])
    monkeypatch.setattr("app.api.learning.get_provider", lambda: provider)
    created = client.post(
        f"/api/courses/{ws['course']['id']}/tasks/generate",
        headers=ws["teacher"],
        json={"topic_id": ws["topic"].id, "level": "II", "language": "kk"},
    )
    assert created.status_code == 201, created.text
    task = db.get(Task, created.json()["task"]["id"])
    assert task is not None and task.status == "draft" and task.topic_id == ws["topic"].id
    assert [(t.input, t.expected_output, t.is_hidden) for t in task.tests] == [
        ("1\n", "1\n", False),
        ("42\n", "42\n", True),
        ("-7\n", "-7\n", True),
    ]
    assert "ФТ-21" in task.source_note
    assert provider.requests[0].data_blocks["topic"] == "1.4 Шарттар"
    monkeypatch.setattr(
        "app.api.learning.get_provider",
        lambda: ScriptedProvider([_draft_answer("// fake:CE")]),
    )
    broken = client.post(
        f"/api/courses/{ws['course']['id']}/tasks/generate",
        headers=ws["teacher"],
        json={"topic_id": ws["topic"].id},
    )
    assert broken.status_code == 422 and broken.json()["detail"] == "solution_does_not_compile"


def test_ft21_draft_from_a_chosen_book_chapter(
    client: TestClient,
    modelled: dict[str, Any],
    collection: MaterialVersion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = modelled
    url = f"/api/materials/{collection.material_id}/versions/{collection.id}/chapters"
    [chapter] = client.get(url, headers=ws["teacher"]).json()
    assert chapter == {"chapter": "1-тарау", "first_page": 12, "last_page": 12, "chunks": 1}
    provider = ScriptedProvider([_draft_answer("// fake:ECHO\nint main() {}")])
    monkeypatch.setattr("app.api.learning.get_provider", lambda: provider)
    created = client.post(
        f"/api/courses/{ws['course']['id']}/tasks/generate",
        headers=ws["teacher"],
        json={"topic_id": ws["topic"].id, "version_id": collection.id, "chapter": "1-тарау"},
    )
    assert created.status_code == 201
    fragments = provider.requests[0].data_blocks["book_fragments"]
    assert "Жұп па?" in fragments and "12" in fragments  # chapter text with its page
    assert client.get(url, headers=ws["student"]).status_code == 403
    assert (
        client.post(
            f"/api/courses/{ws['course']['id']}/tasks/generate",
            headers=ws["student"],
            json={"topic_id": ws["topic"].id},
        ).status_code
        == 403
    )


@pytest.fixture
def collection(ws: dict[str, Any], db: Session, school: School) -> MaterialVersion:
    material = Material(
        course_id=ws["course"]["id"],
        title="Есептер жинағы",
        kind="problems",
        rights_confirmed_by=school["teacher_a"].id,
        rights_confirmed_at=datetime.now(UTC),
    )
    db.add(material)
    db.flush()
    version = MaterialVersion(
        material_id=material.id,
        version=1,
        filename="problems.pdf",
        stored_name="x",
        mime="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        status="ready",
    )
    db.add(version)
    db.flush()
    db.add(
        Chunk(
            version_id=version.id,
            position=0,
            chapter="1-тарау",
            page=12,
            text="1. Жұп па? n саны жұп болса YES шығарыңыз. Мысал: 4 → YES",
            embedding=[0.0] * EMBEDDING_DIM,
        )
    )
    db.flush()
    return version


def test_ft23_problems_are_extracted_from_a_collection_as_drafts(
    client: TestClient,
    ws: dict[str, Any],
    collection: MaterialVersion,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = {
        "problems": [
            {
                "title": "Жұп па?",
                "statement": "n саны жұп болса YES шығарыңыз.",
                "examples": [{"input": "4\n", "output": "YES\n"}],
            },
            {"title": "", "statement": "incomplete"},
        ]
    }
    provider = ScriptedProvider([json.dumps(answer, ensure_ascii=False)])
    monkeypatch.setattr("app.api.learning.get_provider", lambda: provider)
    url = f"/api/materials/{collection.material_id}/extract-problems"
    first = client.post(url, headers=ws["teacher"], json={"version_id": collection.id})
    assert first.status_code == 201, first.text
    [summary] = first.json()["tasks"]
    task = db.get(Task, summary["id"])
    assert task is not None and task.status == "draft" and task.reference_solution == ""
    assert [(t.input, t.expected_output, t.is_hidden) for t in task.tests] == [
        ("4\n", "YES\n", False)
    ]
    assert "12" in task.source_note and "ФТ-23" in task.source_note
    assert "Жұп па?" in provider.requests[0].data_blocks["collection"]
    last = client.post(
        url,
        headers=ws["teacher"],
        json={"version_id": collection.id, "offset": first.json()["next_offset"]},
    )
    assert last.json()["done"] is True and last.json()["tasks"] == []


# Code similarity (ФТ-30) --------------------------------------------------------------------

ORIGINAL = """#include <iostream>
using namespace std;
int main() {
    int n; cin >> n;
    long long total = 0;
    for (int i = 1; i <= n; ++i) { if (i % 3 == 0 || i % 5 == 0) total += i; }
    cout << total << endl;
    return 0;
}
"""
RENAMED = """#include <iostream>
using namespace std;
// my own solution
int main() {
    int count; cin >> count;
    long long sum = 0;
    for (int k = 1; k <= count; ++k) {
        if (k % 3 == 0 || k % 5 == 0) sum += k;
    }
    cout << sum << endl;
    return 0;
}
"""
DIFFERENT = """#include <bits/stdc++.h>
int main() {
    std::string s; std::getline(std::cin, s);
    std::reverse(s.begin(), s.end());
    std::map<char, int> seen;
    for (char c : s) seen[c]++;
    std::cout << s << ' ' << seen.size() << '\\n';
}
"""


def test_ft30_renaming_and_reformatting_do_not_hide_copying() -> None:
    pairs = {
        (p["a"], p["b"]): p["similarity"]
        for p in builtin_pairs({1: ORIGINAL, 2: RENAMED, 3: DIFFERENT})
    }
    assert pairs[(1, 2)] >= 0.8
    assert pairs[(1, 3)] < 0.4 and pairs[(2, 3)] < 0.4


def test_ft30_jplag_csv_is_read() -> None:
    text = (
        "submissionName1,submissionName2,averageSimilarity,maximumSimilarity\n"
        "u1,u2,0.83,0.9\nu1,u3,12.5,20\n"
    )
    assert _parse_csv(text) == [("u1", "u2", 0.83), ("u1", "u3", 0.125)]


@pytest.mark.skipif(shutil.which("java") is None, reason="JPlag needs Java (the analyzer image)")
def test_ft30_jplag_compares_in_the_analyzer() -> None:
    from pathlib import Path

    from app.core.config import get_settings
    from app.services.similarity import jplag_pairs

    jar = Path(get_settings().jplag_jar)
    if not jar.is_file():
        pytest.skip("JPlag jar is installed only in the analyzer image")
    pairs = jplag_pairs({1: ORIGINAL, 2: RENAMED, 3: DIFFERENT}, jar)
    best = max(pairs, key=lambda p: p["similarity"])
    assert (best["a"], best["b"]) == (1, 2)


@pytest.fixture
def inline_similarity(db: Session) -> Iterator[None]:
    def run_inline(report_id: int) -> None:
        set_system(db)  # like jobs.similarity_job, which runs in the analyzer worker
        report = db.get(SimilarityReport, report_id)
        assert report is not None
        run_report(db, report, ("builtin", builtin_pairs))
        db.commit()

    app.dependency_overrides[get_similarity_enqueue] = lambda: run_inline
    yield
    app.dependency_overrides.pop(get_similarity_enqueue, None)


@pytest.mark.usefixtures("inline_similarity")
def test_ft30_similarity_report_for_the_teacher(
    client: TestClient, ws: dict[str, Any], school: School, make_user: MakeUser, db: Session
) -> None:
    twin = make_user("twin@example.com", Role.STUDENT)
    db.add(GroupMember(group_id=school["group_a"].id, user_id=twin.id))
    db.flush()
    twin_headers = login(client, "twin@example.com")
    _submit(client, ws, _open(client, ws), "// fake:OK\n" + ORIGINAL)
    sid = _open(client, ws, twin_headers)
    response = client.post(
        f"/api/sessions/{sid}/submit",
        headers=twin_headers,
        json={"code": "// fake:OK\n" + RENAMED, "explanation": "өзім жаздым"},
    )
    assert response.status_code == 201
    url = f"/api/assessments/{ws['assessment']['id']}/similarity"
    started = client.post(url, headers=ws["teacher"], json={"task_id": ws["task"]["id"]})
    assert started.status_code == 202
    [report] = client.get(url, headers=ws["teacher"]).json()
    assert report["status"] == "done" and report["engine"] == "builtin"
    [pair] = report["pairs"]
    assert pair["similarity"] >= 0.8
    assert {pair["a_name"], pair["b_name"]} == {school["student_a"].full_name, twin.full_name}
    assert client.get(url, headers=ws["student"]).status_code == 403
    assert db.scalar(select(SimilarityReport.engine)) == "builtin"


# OCR (ФТ-37) --------------------------------------------------------------------------------


def _pdf_with_blank_page() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_ft37_scanned_pages_go_to_ocr_in_kazakh_and_russian() -> None:
    calls: list[list[int]] = []

    def fake_ocr(data: bytes, numbers: list[int]) -> dict[int, str]:
        calls.append(numbers)
        return {n: "Цикл — қайталану. Цикл — повторение." for n in numbers}

    [page] = extract_pdf(_pdf_with_blank_page(), ocr=fake_ocr)
    assert calls == [[1]] and page.text.startswith("Цикл") and page.page == 1
    [plain] = extract_pdf(_pdf_with_blank_page())  # without OCR the page stays empty
    assert plain.text == ""


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is in the extractor image")
def test_ft37_tesseract_reads_kazakh_and_russian() -> None:
    from app.services.extract import tesseract_ocr

    assert tesseract_ocr(_pdf_with_blank_page(), [1]).get(1, "").strip() == ""
