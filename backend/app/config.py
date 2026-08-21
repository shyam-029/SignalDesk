# App configuration — central, typed access to environment settings.
#
# New concept: pydantic-settings. Each class attribute maps to an environment
# variable (attribute name uppercased by default) and is type-checked. It reads
# values from the `.env` file at the backend/ root. This is the "config as code"
# (12-factor) pattern: one typed Settings object, no scattered os.getenv calls.

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the backend/ directory (parent of app/).
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Application environment: "development" | "production".
    app_env: str = "development"

    # PostgreSQL async connection string, e.g.
    # postgresql+asyncpg://user:pass@host:port/dbname
    database_url: str

    # Redis connection string — optional for now, used in a later caching phase.
    redis_url: str = ""

    # --- Optional API keys (deferred to later phases) ---
    # LLM provider keys (OpenAI / Anthropic) for explanation + NL screener.
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Finnhub key for live prices (deferred).
    finnhub_api_key: str = ""

    model_config = SettingsConfigDict(
        # Read values from `.env` in the backend/ directory.
        env_file=BACKEND_DIR / ".env",
        # Ignore unknown keys so extra env vars never break startup.
        extra="ignore",
        # Treat empty-string values as "not set" so optional keys default cleanly.
        env_ignore_empty=True,
    )


# Module-level singleton: import as `from app.config import settings`.
settings = Settings()