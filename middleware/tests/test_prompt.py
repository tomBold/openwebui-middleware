from pathlib import Path

from app.config import DEFAULT_PROMPT_PATH
from app.prompt import inject_system_prompt, load_system_prompt

SYSTEM_PROMPT_DOC = Path(__file__).parents[2] / "SYSTEM_PROMPT.md"
PROMPT_MARKER = "<!-- prompt:start -->"


def test_injects_prompt_as_first_message() -> None:
    messages = [{"role": "user", "content": "hello"}]

    result = inject_system_prompt(messages, "PROMPT")

    assert result[0] == {"role": "system", "content": "PROMPT"}
    assert result[1:] == messages


def test_keeps_existing_system_message_after_injected_prompt() -> None:
    messages = [
        {"role": "system", "content": "caller system prompt"},
        {"role": "user", "content": "hello"},
    ]

    result = inject_system_prompt(messages, "PROMPT")

    assert [message["role"] for message in result] == ["system", "system", "user"]
    assert result[1]["content"] == "caller system prompt"


def test_does_not_mutate_caller_messages() -> None:
    messages = [{"role": "user", "content": "hello"}]

    inject_system_prompt(messages, "PROMPT")

    assert messages == [{"role": "user", "content": "hello"}]


def test_load_system_prompt_strips_surrounding_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "prompt.md"
    path.write_text("  PROMPT\n\n", encoding="utf-8")

    assert load_system_prompt(path) == "PROMPT"


def test_system_prompt_doc_embeds_the_shipped_prompt() -> None:
    doc = SYSTEM_PROMPT_DOC.read_text(encoding="utf-8")
    prompt = load_system_prompt(DEFAULT_PROMPT_PATH)

    assert PROMPT_MARKER in doc
    assert prompt in doc
