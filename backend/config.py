from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    teacher_password: str
    session_secret: str
    database_url: str
    cookie_secure: bool
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            teacher_password=os.getenv("TEACHER_PASSWORD", "change-me"),
            session_secret=os.getenv("SESSION_SECRET", "development-only-secret"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./practice-hell.db"),
            cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            llm_provider=os.getenv("LLM_PROVIDER", "mock"),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
        )
