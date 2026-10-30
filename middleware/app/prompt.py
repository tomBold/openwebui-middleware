from pathlib import Path
from typing import Any

Message = dict[str, Any]


def load_system_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def inject_system_prompt(messages: list[Message], system_prompt: str) -> list[Message]:
    return [{"role": "system", "content": system_prompt}, *messages]
