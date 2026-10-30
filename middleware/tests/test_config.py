import pytest
from pydantic import ValidationError

from app.config import Settings


def test_models_accept_comma_separated_string() -> None:
    settings = Settings(openai_api_key="key", openai_models="gpt-5.4-mini, gpt-6-luna")

    assert settings.openai_models == ["gpt-5.4-mini", "gpt-6-luna"]


def test_api_key_is_not_exposed_in_repr() -> None:
    settings = Settings(openai_api_key="super-secret")

    assert "super-secret" not in repr(settings)
    assert settings.openai_api_key.get_secret_value() == "super-secret"


def test_log_level_is_normalised_and_validated() -> None:
    assert Settings(openai_api_key="key", log_level="debug").log_level == "DEBUG"

    with pytest.raises(ValidationError, match="LOG_LEVEL must be one of"):
        Settings(openai_api_key="key", log_level="loud")


def test_api_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
