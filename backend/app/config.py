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

    # --- LLM provider (Phase 5: grounded explanation narrative) ---
    # API key for the LLM gateway. Empty string => LLM disabled; the app falls
    # back to the rule-based explanation.
    llm_api_key: str = ""

    # Base URL for an OpenAI-compatible chat-completions endpoint.
    # Defaults to OpenRouter's API (no SDK required; we call it with httpx).
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # Model ID (e.g. an OpenRouter model name). Empty string (the code default)
    # means "not configured" -> LLM disabled. Free OpenRouter models rotate; the
    # actual ID is set via .env, never hard-coded here.
    llm_model: str = ""

    # Daily budget cap: max LLM calls per process-day. In-process counter only
    # (Redis stays deferred to a later caching phase).
    llm_daily_cap: int = 100

    # Finnhub key for live prices (deferred).
    finnhub_api_key: str = ""

    # --- CORS (Phase 6: browser frontend) ---
    # Comma-separated list of origins allowed to call the API from a browser.
    # Empty string disables CORS handling entirely. Defaults to the Vite dev
    # server; production origins are added via .env, never hard-coded.
    cors_origins: str = "http://localhost:5173"

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