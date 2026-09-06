# App configuration — central, typed access to environment settings.
#
# New concept: pydantic-settings. Each class attribute maps to an environment
# variable (attribute name uppercased by default) and is type-checked. It reads
# values from the `.env` file at the backend/ root. This is the "config as code"
# (12-factor) pattern: one typed Settings object, no scattered os.getenv calls.

from pathlib import Path

from pydantic import AliasChoices, Field
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

    # --- LLM provider (Phase 5: grounded explanation narrative; Part H: ask) ---
    # API key for the LLM gateway. Empty string => LLM disabled; the app falls
    # back to the rule-based explanation. LLM_API_KEY is the primary variable;
    # OPENROUTER_API_KEY is accepted as an alias so an OpenRouter-only setup
    # works without duplicating the key under two names.
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENROUTER_API_KEY"),
    )

    # Base URL for an OpenAI-compatible chat-completions endpoint.
    # Defaults to OpenRouter's API (no SDK required; we call it with httpx).
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # Model ID (e.g. an OpenRouter model name). Empty string (the code default)
    # means "not configured" -> LLM disabled. Free OpenRouter models rotate; the
    # actual ID is set via .env, never hard-coded here.
    llm_model: str = ""

    # Daily budget cap: max LLM calls per process-day. In-process counter only
    # (Redis stays deferred to a later caching phase). Sized for the nightly
    # explanation pre-warm sweep (one call per catalog symbol, ~250) plus
    # headroom for /ask; free OpenRouter models cost nothing per call.
    llm_daily_cap: int = 300

    # Finnhub key for live prices (deferred).
    finnhub_api_key: str = ""

    # --- Upstox market data (Phase 6.5 Part F: dual providers) ---
    # Manually generated Upstox access token ("Analytics Token") used as a
    # Bearer credential for read-only market-data APIs. Empty string means
    # Upstox is not configured and the app operates yfinance-only. The token
    # is server-side only: never logged, never sent to the frontend.
    upstox_analytics_token: str = ""

    # --- OpenRouter (alternative name for the LLM gateway key) ---
    # Consumed via the AliasChoices above: OPENROUTER_API_KEY fills
    # llm_api_key when LLM_API_KEY is not set. Declared so the variable is
    # recognized cleanly; no code reads it directly.
    openrouter_api_key: str = ""

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