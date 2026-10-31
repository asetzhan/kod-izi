"""Testing through Judge0 (ФТ-31): verdicts OK, WA, TLE, MLE, RE, CE, time and memory."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.enums import SubmissionStatus, TraceKind, Verdict
from app.judge.client import JudgeClient, JudgeUnavailableError, RunRequest, RunResult, RunStatus
from app.models import Submission, SubmissionTestResult, Task, TestCase, WorkSession
from app.services.trace import record_server_event

OUTPUT_KEEP = 4096

STATUS_VERDICT = {
    RunStatus.COMPILE_ERROR: Verdict.CE,
    RunStatus.RUNTIME_ERROR: Verdict.RE,
    RunStatus.TIME_LIMIT: Verdict.TLE,
    RunStatus.MEMORY_LIMIT: Verdict.MLE,
}


def normalize_output(text: str) -> list[str]:
    """Trailing spaces on a line and trailing empty lines do not matter."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def verdict_for(result: RunResult, expected: str) -> Verdict:
    if result.status == RunStatus.FINISHED:
        return (
            Verdict.OK
            if normalize_output(result.stdout) == normalize_output(expected)
            else Verdict.WA
        )
    if result.status == RunStatus.INTERNAL_ERROR:
        raise JudgeUnavailableError("Judge0 internal error")
    return STATUS_VERDICT[result.status]


def run_request(task: Task, source: str, language: str, stdin: str) -> RunRequest:
    return RunRequest(
        source=source,
        language=language,
        stdin=stdin,
        cpu_time_limit_s=task.time_limit_ms / 1000,
        memory_limit_kb=task.memory_limit_kb,
    )


def run_tests(
    judge: JudgeClient, task: Task, source: str, language: str, tests: list[TestCase]
) -> tuple[list[tuple[TestCase, Verdict, RunResult]], str]:
    """Run the tests in order; a compile error stops after the first one."""
    results: list[tuple[TestCase, Verdict, RunResult]] = []
    for test in tests:
        result = judge.run(run_request(task, source, language, test.input))
        verdict = verdict_for(result, test.expected_output)
        results.append((test, verdict, result))
        if verdict == Verdict.CE:
            return results, result.compile_output
    return results, ""


def grade_submission(db: Session, judge: JudgeClient, submission: Submission) -> None:
    """Grade on all tests of the task; the verdict is the first failing test's (ICPC style)."""
    task = db.get(Task, submission.task_id)
    session = db.get(WorkSession, submission.session_id)
    if task is None or session is None:
        raise RuntimeError(f"submission {submission.id} has no task or session")
    submission.status = SubmissionStatus.RUNNING.value
    db.flush()
    try:
        results, compile_output = run_tests(
            judge, task, submission.code, submission.language, task.tests
        )
    except JudgeUnavailableError as exc:
        submission.status = SubmissionStatus.ERROR.value
        submission.error = str(exc)[:1000]
        submission.finished_at = datetime.now(UTC)
        return

    submission.results = [
        SubmissionTestResult(
            test_case_id=test.id,
            position=test.position,
            is_hidden=test.is_hidden,
            verdict=verdict.value,
            time_ms=round(result.time_s * 1000) if result.time_s is not None else None,
            memory_kb=result.memory_kb,
            stdout=result.stdout[:OUTPUT_KEEP],
            stderr=result.stderr[:OUTPUT_KEEP],
        )
        for test, verdict, result in results
    ]
    failing = next((v for _, v, _ in results if v != Verdict.OK), None)
    submission.verdict = (failing or Verdict.OK).value
    submission.tests_total = len(task.tests)
    submission.tests_passed = sum(1 for _, v, _ in results if v == Verdict.OK)
    times = [r.time_s for _, _, r in results if r.time_s is not None]
    memories = [r.memory_kb for _, _, r in results if r.memory_kb is not None]
    submission.max_time_ms = round(max(times) * 1000) if times else None
    submission.max_memory_kb = max(memories) if memories else None
    submission.compile_output = compile_output[:OUTPUT_KEEP]
    submission.status = SubmissionStatus.DONE.value
    submission.finished_at = datetime.now(UTC)
    record_server_event(
        db,
        session,
        TraceKind.VERDICT,
        {
            "submission_id": submission.id,
            "verdict": submission.verdict,
            "tests_passed": submission.tests_passed,
            "tests_total": submission.tests_total,
            "per_test": [v.value for _, v, _ in results],
        },
    )
