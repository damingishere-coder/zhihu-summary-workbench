from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


@dataclass(slots=True)
class ProviderUsage:
    provider: str
    model: str
    model_role: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    estimated_cost: float = 0
    cache_hit: bool = False
    fallback_used: bool = False
    retry_count: int = 0


@dataclass(slots=True)
class StructuredProviderResult(Generic[T]):
    data: T
    usage: ProviderUsage


class TextGenerationProvider(ABC):
    @abstractmethod
    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_role: str,
    ) -> tuple[str, ProviderUsage]:
        raise NotImplementedError


class StructuredOutputProvider(ABC):
    @abstractmethod
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model_role: str,
    ) -> StructuredProviderResult[T]:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class ImageGenerationProvider(ABC):
    @abstractmethod
    def capability(self) -> BaseModel:
        raise NotImplementedError
