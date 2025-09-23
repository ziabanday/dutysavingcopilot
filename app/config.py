# app/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Winner config (defaults) ---
    FUSION_ALPHA: float = 0.75
    BM25_K1: float = 1.4
    BM25_B: float = 0.8
    TOP_K: int = 6

    # --- Guardrails / ops ---
    STRICT_JSON: int = 1
    ABSTAIN_ON_NO_EVIDENCE: int = 1
    MAX_TOKENS: int = 320
    TIMEOUT_S: int = 15
    WARMUP: int = 1

    # --- Optional extras (lower-case to match your env exactly) ---
    openai_api_key: Optional[str] = None
    database_url: Optional[str] = None
    log_level: Optional[str] = None
    max_monthly_tokens: Optional[int] = None
    cors_origins: Optional[str] = None  # parse CSV later if needed

    # Pydantic v2 settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",   # accept unknown env keys without error
    )

settings = Settings()
