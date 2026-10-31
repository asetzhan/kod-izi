"""ФТ-31: Judge0 client and grading rules, with Judge0 replaced by a mock HTTP transport."""

import base64
import json
from typing import Any

import httpx
import pytest

from app.judge.client import JudgeUnavailableError, RunRequest, RunResult, RunStatus
from app.judge.judge0 import COMPILER_OPTIONS, Judge0Client, to_result
from app.services.grading import normalize_output, verdict_for
from app.services.questions import template_questions


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def judge0(status_id: int, **fields: Any) -> dict[str, Any]:
    return {"status": {"id": status_id}, **fields}


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (judge0(3, stdout=b64("5\n"), time="0.01", memory=1200), RunStatus.FINISHED),
        (judge0(4, stdout=b64("6\n")), RunStatus.FINISHED),
        (judge0(5, time="2.0"), RunStatus.TIME_LIMIT),
        (judge0(6, compile_output=b64("error")), RunStatus.COMPILE_ERROR),
        (judge0(11, memory=1000), RunStatus.RUNTIME_ERROR),
        (judge0(7, memory=262000), RunStatus.MEMORY_LIMIT),
        (judge0(11, stderr=b64("std::bad_alloc")), RunStatus.MEMORY_LIMIT),
        (judge0(13), RunStatus.INTERNAL_ERROR),
    ],
)
def test_ft31_judge0_statuses_are_mapped(data: dict[str, Any], expected: RunStatus) -> None:
    assert to_result(data, memory_limit_kb=262144).status == expected


def test_ft31_client_sends_fixed_options_and_no_network() -> None:
    sent: list[dict[str, Any]] = []
    polls = iter([judge0(1), judge0(2), judge0(3, stdout=b64("42\n"), time="0.05", memory=2048)])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            sent.append(json.loads(request.content))
            return httpx.Response(201, json={"token": "abc"})
        assert request.url.path == "/submissions/abc"
        return httpx.Response(200, json=next(polls))

    http = httpx.Client(base_url="http://judge0", transport=httpx.MockTransport(handler))
    client = Judge0Client("http://judge0", "token", poll_interval_s=0, http=http)
    result = client.run(RunRequest("int main(){}", "cpp20", "1 2\n", 1.0, 65536))

    assert result == RunResult(RunStatus.FINISHED, stdout="42\n", time_s=0.05, memory_kb=2048)
    body = sent[0]
    assert body["enable_network"] is False
    assert body["compiler_options"] == COMPILER_OPTIONS["cpp20"]
    assert base64.b64decode(body["stdin"]).decode() == "1 2\n"
    assert body["memory_limit"] == 65536


def test_ft31_unreachable_judge_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    http = httpx.Client(base_url="http://judge0", transport=httpx.MockTransport(handler))
    client = Judge0Client("http://judge0", None, http=http)
    with pytest.raises(JudgeUnavailableError):
        client.run(RunRequest("x", "cpp17", "", 1.0, 65536))


def test_ft31_output_comparison_ignores_trailing_whitespace() -> None:
    assert normalize_output("1 2  \n3\n\n\n") == normalize_output("1 2\r\n3")
    ok = RunResult(RunStatus.FINISHED, stdout="EVEN \n\n")
    assert verdict_for(ok, "EVEN\n").value == "OK"
    assert verdict_for(RunResult(RunStatus.FINISHED, stdout="ODD\n"), "EVEN\n").value == "WA"


def test_ft27_template_questions_follow_the_code() -> None:
    questions = template_questions("vector<int> a(n); for (int i = 0; i < n; ++i) {}", "ru")
    assert questions[0].startswith("Когда останавливается")
    assert "границы массива" in questions[1]
    assert len(template_questions("int main() {}", "kk")) == 2
