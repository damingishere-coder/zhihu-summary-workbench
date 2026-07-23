from __future__ import annotations

import hashlib
import math
import re

from backend.app.ai.providers.base import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    """无需下载模型的多语言字符 n-gram 特征哈希 Embedding。

    它适合离线开发、测试和中文相似观点粗聚类；生产环境仍可通过
    EmbeddingProvider 接口替换为更强的本地多语言模型。
    """

    dimensions = 256
    model = "local-multilingual-char-ngram-v1"

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = re.sub(r"\s+", "", text.lower())
        if not normalized:
            return [""]
        features = list(normalized)
        features.extend(
            normalized[index : index + size]
            for size in (2, 3)
            for index in range(max(0, len(normalized) - size + 1))
        )
        return features

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            raw = [0.0] * self.dimensions
            for feature in self._features(text):
                digest = hashlib.blake2b(
                    feature.encode("utf-8"), digest_size=8
                ).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                raw[index] += sign
            norm = math.sqrt(sum(value * value for value in raw)) or 1.0
            vectors.append([value / norm for value in raw])
        return vectors
