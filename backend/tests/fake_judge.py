"""Stand-in for Judge0 in tests: nothing is compiled or executed.

The behaviour is chosen by a marker comment in the source, e.g. `// fake:TLE`.
Without a marker the program "prints" the expected answer for the given input.
"""

import re

from app.judge.client import JudgeUnavailableError, RunRequest, RunResult, RunStatus

MARKER = re.compile(r"//\s*fake:(\w+)")


class FakeJudge:
    def __init__(self, answers: dict[str, str] | None = None) -> None:
        self.answers = answers or {}
        self.requests: list[RunRequest] = []
        self.down = False

    def run(self, request: RunRequest) -> RunResult:
        self.requests.append(request)
        if self.down:
            raise JudgeUnavailableError("judge is down")
        match = MARKER.search(request.source)
        mode = match.group(1) if match else "OK"
        if mode == "CE":
            return RunResult(
                RunStatus.COMPILE_ERROR, compile_output="main.cpp:3: error: expected ';'"
            )
        if mode == "TLE":
            return RunResult(RunStatus.TIME_LIMIT, time_s=request.cpu_time_limit_s)
        if mode == "MLE":
            return RunResult(RunStatus.MEMORY_LIMIT, memory_kb=request.memory_limit_kb)
        if mode == "RE":
            return RunResult(RunStatus.RUNTIME_ERROR, stderr="Segmentation fault", time_s=0.01)
        if mode == "WA":
            return RunResult(RunStatus.FINISHED, stdout="wrong\n", time_s=0.01, memory_kb=900)
        if mode == "ECHO":
            return RunResult(RunStatus.FINISHED, stdout=request.stdin, time_s=0.01, memory_kb=900)
        return RunResult(
            RunStatus.FINISHED,
            stdout=self.answers.get(request.stdin, ""),
            time_s=0.02,
            memory_kb=1024,
        )
