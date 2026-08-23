from __future__ import annotations

from backend.app.ai.providers.base import (
    StructuredOutputProvider,
    TextGenerationProvider,
)
from backend.app.ai.providers.codex import CodexProvider
from backend.app.ai.providers.deepseek import DeepSeekProvider
from backend.app.ai.providers.mock import MockProvider
from backend.app.core.config import Settings


def create_structured_provider(
    mode: str, settings: Settings
) -> StructuredOutputProvider:
    if mode == "deepseek":
        return DeepSeekProvider(settings)
    if mode == "codex":
        return CodexProvider(settings)
    return MockProvider()


def create_text_provider(
    mode: str, settings: Settings
) -> TextGenerationProvider:
    if mode == "deepseek":
        return DeepSeekProvider(settings)
    if mode == "codex":
        return CodexProvider(settings)
    return MockProvider()
