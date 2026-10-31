"""Application settings, read only from environment variables (spec 14.1: secrets out of code)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "prod"
    database_url: str
    redis_url: str
    jwt_secret: str = Field(min_length=32)
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    login_max_attempts: int = 5
    login_window_seconds: int = 900
    cookie_secure: bool = True
    llm_provider: str = "fake"
    judge0_url: str = "http://judge0-server:2358"
    judge0_authn_token: str = ""
    # Repository seed/ directory (mounted at /seed in docker).
    seed_dir: Path = Path(__file__).resolve().parents[3] / "seed"
    max_import_bytes: int = 10 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
