from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_HOST: str
    APP_PORT: int

    # DB
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str

    # Ollama
    OLLAMA_HOST: str
    OLLAMA_TIMEOUT: int
    OLLAMA_MODEL: str
    OLLAMA_TEMPERATURE: float
    OLLAMA_MAX_TOKENS: int
    OLLAMA_TOP_P: float
    ALLOWED_LLM_MODELS: List[str] = ["llama3", "phi3"]

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
