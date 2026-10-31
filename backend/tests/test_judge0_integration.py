"""Stage 2 acceptance against a real Judge0 (ФТ-31, spec 14.1).

Runs only when JUDGE0_TEST_URL points to a Judge0 1.13.1 instance (and JUDGE0_TEST_TOKEN
if it requires one). Judge0 1.13.1 needs cgroup v1, which neither GitHub Actions nor
the development machine has (questions.md, Q-15), so CI skips this file.

    JUDGE0_TEST_URL=http://localhost:2358 pytest tests/test_judge0_integration.py
"""

import os
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.enums import Verdict
from app.judge.client import RunRequest, RunStatus
from app.judge.judge0 import Judge0Client
from app.services.grading import verdict_for
from app.services.seed_content import read_package_dir
from app.services.task_import import TaskDraftData, parse_package

URL = os.environ.get("JUDGE0_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="JUDGE0_TEST_URL is not set (Q-15)")

SAMPLES = Path(__file__).parent / "judge_samples"
EXPERIMENT = get_settings().seed_dir / "tasks" / "experiment"


@pytest.fixture(scope="module")
def judge() -> Judge0Client:
    assert URL is not None
    return Judge0Client(URL, os.environ.get("JUDGE0_TEST_TOKEN"))


def _verdicts(judge: Judge0Client, draft: TaskDraftData, source: str) -> list[Verdict]:
    verdicts = []
    for test in draft.tests:
        result = judge.run(
            RunRequest(
                source, "cpp17", test.input, draft.time_limit_ms / 1000, draft.memory_limit_kb
            )
        )
        verdicts.append(verdict_for(result, test.expected_output))
    return verdicts


@pytest.mark.parametrize("key", sorted(p.name for p in EXPERIMENT.iterdir() if p.is_dir()))
def test_ft31_reference_solution_of_every_seed_task_gets_ok(judge: Judge0Client, key: str) -> None:
    draft = parse_package(read_package_dir(EXPERIMENT / key))
    assert set(_verdicts(judge, draft, draft.reference_solution)) == {Verdict.OK}


@pytest.mark.parametrize("verdict", ["WA", "TLE", "MLE", "RE", "CE"])
def test_ft31_prepared_wrong_solution_gets_expected_verdict(
    judge: Judge0Client, verdict: str
) -> None:
    draft = parse_package(read_package_dir(EXPERIMENT / "EXP-I-1"))
    source = (SAMPLES / f"{verdict.lower()}.cpp").read_text()
    assert Verdict(verdict) in _verdicts(judge, draft, source)


def test_sec14_student_code_cannot_reach_the_network(judge: Judge0Client) -> None:
    source = (SAMPLES / "network.cpp").read_text()
    result = judge.run(RunRequest(source, "cpp17", "", 5.0, 262144))
    assert result.status == RunStatus.FINISHED
    assert result.stdout.strip() == "BLOCKED"
