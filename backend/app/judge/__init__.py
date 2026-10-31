from functools import lru_cache

from app.core.config import get_settings
from app.judge.client import JudgeClient
from app.judge.judge0 import Judge0Client


@lru_cache
def get_judge() -> JudgeClient:
    settings = get_settings()
    return Judge0Client(settings.judge0_url, settings.judge0_authn_token or None)
