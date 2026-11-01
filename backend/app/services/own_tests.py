"""ОТ-06: the student's own tests and the stress test, as in CPEditor.

Every program here (solution, slow correct solution, generator) is student code, so it
runs only in Judge0 (CLAUDE.md), with the problem's limits.
"""

from dataclasses import dataclass

from app.core.enums import Verdict
from app.judge.client import JudgeClient, RunResult, RunStatus
from app.models import StudentTest, Task
from app.services.grading import normalize_output, run_request, verdict_for

MAX_OWN_TESTS = 50
MAX_STRESS_ITERATIONS = 30
OUTPUT_SHOWN = 4000


@dataclass(frozen=True)
class OwnResult:
    test_id: int
    status: str  # judge status
    verdict: Verdict | None  # only when the student gave the expected answer
    output: str
    time_ms: int | None


def run_own(
    judge: JudgeClient, task: Task, code: str, language: str, tests: list[StudentTest]
) -> list[OwnResult]:
    """Run every saved test with one button; compare only where the answer is given."""
    out = []
    for test in tests:
        result = judge.run(run_request(task, code, language, test.input))
        verdict = verdict_for(result, test.expected_output) if test.expected_output else None
        out.append(
            OwnResult(
                test.id,
                result.status.value,
                verdict,
                result.stdout[:OUTPUT_SHOWN] or result.compile_output[:OUTPUT_SHOWN],
                round(result.time_s * 1000) if result.time_s is not None else None,
            )
        )
        if result.status == RunStatus.COMPILE_ERROR:
            break
    return out


@dataclass(frozen=True)
class StressResult:
    status: str  # ok, mismatch, generator_failed, brute_failed, solution_failed
    iterations: int
    input: str = ""
    expected: str = ""  # the slow correct solution's answer
    actual: str = ""
    detail: str = ""


def _failed(result: RunResult) -> bool:
    return result.status != RunStatus.FINISHED


def _detail(result: RunResult) -> str:
    return (result.compile_output or result.stderr or result.status.value)[:OUTPUT_SHOWN]


def stress(
    judge: JudgeClient,
    task: Task,
    language: str,
    solution: str,
    brute: str,
    generator: str,
    iterations: int,
) -> StressResult:
    """The generator gets the test number as input and prints a test; the solution and
    the slow correct solution must print the same answer. Stops at the first difference
    and shows that input."""
    for i in range(1, iterations + 1):
        generated = judge.run(run_request(task, generator, language, f"{i}\n"))
        if _failed(generated):
            return StressResult("generator_failed", i, detail=_detail(generated))
        case = generated.stdout
        expected = judge.run(run_request(task, brute, language, case))
        if _failed(expected):
            return StressResult(
                "brute_failed", i, input=case[:OUTPUT_SHOWN], detail=_detail(expected)
            )
        actual = judge.run(run_request(task, solution, language, case))
        if _failed(actual) or normalize_output(actual.stdout) != normalize_output(expected.stdout):
            return StressResult(
                "mismatch" if not _failed(actual) else "solution_failed",
                i,
                input=case[:OUTPUT_SHOWN],
                expected=expected.stdout[:OUTPUT_SHOWN],
                actual=actual.stdout[:OUTPUT_SHOWN],
                detail="" if not _failed(actual) else _detail(actual),
            )
    return StressResult("ok", iterations)
