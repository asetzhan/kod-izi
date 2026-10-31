"""Judge0 CE client (ФТ-31). Judge0 runs on an internal network without internet (spec 14.1).

Judge0 1.13.1 has no "memory limit" status: a program killed for memory ends as a
runtime error, so it is reported as MEMORY_LIMIT when the used memory reached the limit
or the program died of std::bad_alloc.
"""

import base64
import time
from typing import Any

import httpx

from app.judge.client import JudgeUnavailableError, RunRequest, RunResult, RunStatus

CPP_LANGUAGE_ID = 54  # C++ (GCC 9.2.0) in Judge0 CE 1.13.1
# Fixed by the server, never taken from the student. GCC 9 calls C++20 "c++2a".
COMPILER_OPTIONS = {"cpp17": "-std=c++17 -O2", "cpp20": "-std=c++2a -O2"}
OUTPUT_LIMIT = 64 * 1024

# https://github.com/judge0/judge0/blob/master/docs/api/statuses.md
STATUS_IN_QUEUE, STATUS_PROCESSING = 1, 2
STATUS_ACCEPTED, STATUS_WRONG_ANSWER, STATUS_TLE, STATUS_CE = 3, 4, 5, 6
RUNTIME_STATUSES = {7, 8, 9, 10, 11, 12}  # SIGSEGV, SIGXFSZ, SIGFPE, SIGABRT, NZEC, other


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _unb64(value: str | None) -> str:
    if not value:
        return ""
    return base64.b64decode(value).decode("utf-8", errors="replace")[:OUTPUT_LIMIT]


# Must not exceed MAX_* in infra/judge0/judge0.conf, or Judge0 refuses the run.
MAX_CPU_TIME_S = 10
MAX_WALL_TIME_S = 20
MAX_MEMORY_KB = 524288


def wall_time_s(cpu_time_s: float) -> float:
    return min(max(cpu_time_s * 3, 5), MAX_WALL_TIME_S)


def to_result(data: dict[str, Any], memory_limit_kb: int) -> RunResult:
    status_id = int(data["status"]["id"])
    stdout = _unb64(data.get("stdout"))
    stderr = _unb64(data.get("stderr"))
    compile_output = _unb64(data.get("compile_output"))
    time_s = float(data["time"]) if data.get("time") else None
    memory_kb = int(data["memory"]) if data.get("memory") else None

    if status_id in (STATUS_ACCEPTED, STATUS_WRONG_ANSWER):
        status = RunStatus.FINISHED
    elif status_id == STATUS_TLE:
        status = RunStatus.TIME_LIMIT
    elif status_id == STATUS_CE:
        status = RunStatus.COMPILE_ERROR
    elif status_id in RUNTIME_STATUSES:
        out_of_memory = "bad_alloc" in stderr or (
            memory_kb is not None and memory_kb >= memory_limit_kb * 0.95
        )
        status = RunStatus.MEMORY_LIMIT if out_of_memory else RunStatus.RUNTIME_ERROR
    else:
        status = RunStatus.INTERNAL_ERROR
    return RunResult(status, stdout, stderr, compile_output, time_s, memory_kb)


class Judge0Client:
    def __init__(
        self,
        base_url: str,
        auth_token: str | None,
        *,
        poll_interval_s: float = 0.25,
        timeout_s: float = 60.0,
        http: httpx.Client | None = None,
    ) -> None:
        headers = {"X-Auth-Token": auth_token} if auth_token else {}
        self._http = http or httpx.Client(base_url=base_url, headers=headers, timeout=10.0)
        self._poll = poll_interval_s
        self._timeout = timeout_s

    def run(self, request: RunRequest) -> RunResult:
        body = {
            "source_code": _b64(request.source),
            "language_id": CPP_LANGUAGE_ID,
            "compiler_options": COMPILER_OPTIONS[request.language],
            "stdin": _b64(request.stdin),
            "cpu_time_limit": request.cpu_time_limit_s,
            "wall_time_limit": wall_time_s(request.cpu_time_limit_s),
            "memory_limit": request.memory_limit_kb,
            "enable_network": False,
            "redirect_stderr_to_stdout": False,
        }
        try:
            created = self._http.post("/submissions?base64_encoded=true&wait=false", json=body)
            created.raise_for_status()
            token = created.json()["token"]
            # Queue time plus the run itself; never wait longer than the configured cap.
            deadline = time.monotonic() + min(
                self._timeout, wall_time_s(request.cpu_time_limit_s) + 30
            )
            while True:
                response = self._http.get(
                    f"/submissions/{token}",
                    params={
                        "base64_encoded": "true",
                        "fields": "status,stdout,stderr,compile_output,time,memory",
                    },
                )
                response.raise_for_status()
                data = response.json()
                if int(data["status"]["id"]) not in (STATUS_IN_QUEUE, STATUS_PROCESSING):
                    return to_result(data, request.memory_limit_kb)
                if time.monotonic() > deadline:
                    raise JudgeUnavailableError("Judge0 did not finish in time")
                time.sleep(self._poll)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise JudgeUnavailableError(f"Judge0 request failed: {exc}") from exc
