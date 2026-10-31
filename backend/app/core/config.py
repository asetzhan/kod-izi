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
    # Spec 14.1: teachers and administrators must use TOTP.
    require_2fa_for_staff: bool = True
    # Spec 14.3: personal data is kept for this many days after the pilot, then anonymized.
    retention_days: int = 365
    consent_version: str = "2026-1"
    require_consent: bool = True
    # Non-superuser role the application switches to (migration 0006); empty disables.
    db_app_role: str = Field(default="kodizi_app", pattern=r"^([a-z_][a-z0-9_]{0,62})?$")
    # Signed, short-lived links to material files (spec 14.1).
    file_link_ttl_seconds: int = 300
    llm_provider: str = "fake"
    judge0_url: str = "http://judge0-server:2358"
    judge0_authn_token: str = ""
    # Load tests without Judge0 only: `simulated` (refused when APP_ENV=prod).
    judge_backend: Literal["judge0", "simulated"] = "judge0"
    simulated_judge_delay_s: float = 0.2
    # Load tests without an RQ worker only: grade in a thread of the API process.
    grading_inline: bool = False
    # Repository seed/ directory (mounted at /seed in docker).
    seed_dir: Path = Path(__file__).resolve().parents[3] / "seed"
    max_import_bytes: int = 10 * 1024 * 1024
    # Local LLM (Q-08, Q-09).
    ollama_url: str = "http://ollama:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_embed_model: str = "bge-m3"
    llm_daily_quota: int = 40  # assistant and question requests per student per day
    # Teaching materials (ФТ-06): stored outside the web root.
    material_dir: Path = Path("/data/materials")
    max_material_bytes: int = 50 * 1024 * 1024
    clamav_host: str = "clamav"
    clamav_port: int = 3310


@lru_cache
def get_settings() -> Settings:
    return Settings()
