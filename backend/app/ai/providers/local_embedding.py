from __future__ import annotations

import hashlib
import math

from backend.app.ai.providers.base import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    """第一阶段的可替换本地接口实现，不用于正式语义聚类。"""

    dimensions = 32
    model = "local-hash-interface-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [float(value - 128) for value in digest[: self.dimensions]]
            norm = math.sqrt(sum(value * value for value in raw)) or 1.0
            vectors.append([value / norm for value in raw])
        return vectors

