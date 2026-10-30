from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: SecretStr
    openai_base_url: HttpUrl = HttpUrl("https://api.openai.com/v1")
    openai_models: Annotated[list[str], NoDecode] = ["gpt-4o-mini", "gpt-4o"]
    system_prompt_path: Path = DEFAULT_PROMPT_PATH
    upstream_connect_timeout: float = 10.0
    upstream_read_timeout: float = 120.0
    readiness_timeout: float = 5.0
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("openai_models", mode="before")
    @classmethod
    def split_models(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [model.strip() for model in value.split(",") if model.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
