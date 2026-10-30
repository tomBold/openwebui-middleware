from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.upstream import OpenAIUpstream


def get_upstream(request: Request) -> OpenAIUpstream:
    upstream: OpenAIUpstream = request.app.state.upstream
    return upstream


def get_system_prompt(request: Request) -> str:
    system_prompt: str = request.app.state.system_prompt
    return system_prompt


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


UpstreamDep = Annotated[OpenAIUpstream, Depends(get_upstream)]
SystemPromptDep = Annotated[str, Depends(get_system_prompt)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
