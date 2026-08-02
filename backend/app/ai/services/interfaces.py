from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QuestionEvaluator(ABC):
    @abstractmethod
    async def evaluate(self, question: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class AnswerQualityEvaluator(ABC):
    @abstractmethod
    async def evaluate(self, answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError


class AnswerClaimExtractor(ABC):
    @abstractmethod
    async def extract(self, *, question_title: str, answer_text: str) -> Any:
        raise NotImplementedError


class ClaimClusterRefiner(ABC):
    @abstractmethod
    async def refine(self, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError


class OpinionMapGenerator(ABC):
    @abstractmethod
    async def generate(self, clusters: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError


class ArticleGenerator(ABC):
    @abstractmethod
    async def generate(self, opinion_map: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class ArticleReviewer(ABC):
    @abstractmethod
    async def review(self, article: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class InfographicContentGenerator(ABC):
    @abstractmethod
    async def generate(self, opinion_map: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class VisualAssetGenerator(ABC):
    @abstractmethod
    async def prepare(self, infographic: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

