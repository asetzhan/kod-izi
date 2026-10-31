"""Judge0 client interface. The implementation is stage 2 (ФТ-24, ФТ-31).

Student code is executed only through Judge0, never in the backend process.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RunRequest:
    source: str
    language: str  # "cpp17" or "cpp20"
    stdin: str
    cpu_time_limit_s: float
    memory_limit_kb: int


@dataclass(frozen=True)
class RunResult:
    verdict: str  # OK, WA, TLE, MLE, RE, CE
    stdout: str
    stderr: str
    time_s: float | None
    memory_kb: int | None


class JudgeClient(Protocol):
    def run(self, request: RunRequest) -> RunResult: ...
