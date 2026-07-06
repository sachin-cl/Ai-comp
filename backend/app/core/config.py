"""Application configuration via Pydantic Settings. All values overridable by env vars."""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    secret_key: str = "dev-secret-key-do-not-use-in-production"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://aicompany:aicompany@localhost:5432/aicompany"
    redis_url: str = "redis://localhost:6379/0"

    # LLM providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_llm_provider: str = "mock"
    default_llm_model: str = "mock-small"
    embedding_provider: str = "hash"  # "openai" | "hash"
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_seconds: float = 60.0

    # Budgets & safety
    default_token_budget: int = 2_000_000
    max_revision_loops: int = 3
    max_task_retries: int = 2
    max_agent_iterations: int = 10
    workflow_timeout_minutes: int = 60
    structured_output_repair_attempts: int = 2

    # Auth
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Rate limits (requests per window seconds)
    auth_rate_limit: int = 10
    auth_rate_window: int = 60
    project_create_rate_limit: int = 5
    project_create_rate_window: int = 60

    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:8080"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
