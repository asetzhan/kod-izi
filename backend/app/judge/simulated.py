"""A stand-in for Judge0 for load tests on machines without Judge0 (never in production).

It does not compile or run anything. Each run waits a configurable time, like Judge0
would, and prints nothing, so verdicts are WA. Selected with JUDGE_BACKEND=simulated.
"""

import time

from app.judge.client import RunRequest, RunResult, RunStatus


class SimulatedJudge:
    def __init__(self, delay_s: float) -> None:
        self._delay = delay_s

    def run(self, request: RunRequest) -> RunResult:
        time.sleep(self._delay)
        return RunResult(RunStatus.FINISHED, stdout="", time_s=self._delay, memory_kb=1024)
