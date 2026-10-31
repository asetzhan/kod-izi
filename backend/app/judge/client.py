"""Code execution interface (ФТ-24, ФТ-31).

Student code is executed only through Judge0, never in the backend process.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RunStatus(StrEnum):
    """What happened to one run; comparing the output with the answer is done by grading."""

    FINISHED = "finished"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIME_LIMIT = "time_limit"
    MEMORY_LIMIT = "memory_limit"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class RunRequest:
    source: str
    language: str  # "cpp17" or "cpp20"
    stdin: str
    cpu_time_limit_s: float
    memory_limit_kb: int


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    stdout: str = ""
    stderr: str = ""
    compile_output: str = ""
    time_s: float | None = None
    memory_kb: int | None = None


class JudgeUnavailableError(RuntimeError):
    pass


class JudgeClient(Protocol):
    def run(self, request: RunRequest) -> RunResult: ...
