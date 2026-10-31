from functools import lru_cache

from app.core.config import get_settings
from app.judge.client import JudgeClient
from app.judge.judge0 import Judge0Client
from app.judge.simulated import SimulatedJudge


@lru_cache
def get_judge() -> JudgeClient:
    settings = get_settings()
    if settings.judge_backend == "simulated":
        if settings.app_env == "prod":
            raise RuntimeError("the simulated judge is for load tests, not production")
        return SimulatedJudge(settings.simulated_judge_delay_s)
    return Judge0Client(settings.judge0_url, settings.judge0_authn_token or None)
