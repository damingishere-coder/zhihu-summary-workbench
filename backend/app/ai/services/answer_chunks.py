"""Complete long-answer coverage without silently truncating the tail."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from backend.app.ai.providers.base import StructuredProviderResult, ProviderResponseError
from backend.app.schemas.analysis import AnswerQualityBatch, AnswerClaimBatch


def chunks(answers: list[dict[str, Any]], *, size: int = 6000):
    result = []
    for answer in answers:
        text = str(answer.get("plain_content", ""))
        for start in range(0, max(1, len(text)), size):
            result.append({**answer, "answer_id": f"{answer['answer_id']}@{start}",
                           "original_id": answer["answer_id"], "source_start": start,
                           "source_end": min(len(text), start + size), "plain_content": text[start:start + size]})
    return result


def add_usage(left, right):
    if left is None:
        return replace(right)
    for name in ("input_tokens", "output_tokens", "duration_ms", "estimated_cost", "retry_count"):
        setattr(left, name, getattr(left, name) + getattr(right, name))
    left.cache_hit = left.cache_hit and right.cache_hit
    left.fallback_used = left.fallback_used or right.fallback_used
    return left


async def analyze_chunks(answers, call, *, quality: bool):
    rows = chunks(answers)
    collected = []
    usage = None
    for offset in range(0, len(rows), 4):
        batch = rows[offset:offset + 4]
        response = await call(batch)
        expected = {row["answer_id"]: row for row in batch}
        returned = [item.answer_id for item in response.data.items]
        if set(returned) != set(expected) or len(returned) != len(expected):
            raise ProviderResponseError("回答分段结果缺失、重复或引用了未知来源，未将不完整分析计为成功")
        usage = add_usage(usage, response.usage)
        for item in response.data.items:
            original = expected[item.answer_id]
            item.answer_id = original["original_id"]
            if not quality:
                item.source_start = original["source_start"]
                item.source_end = original["source_end"]
            collected.append(item)
    if quality:
        by_id = {}
        for item in collected:
            if item.answer_id not in by_id:
                by_id[item.answer_id] = item
            else:
                saved = by_id[item.answer_id]
                saved.include = saved.include or item.include
                for name in ("relevance_score", "quality_score", "information_density"):
                    setattr(saved, name, max(getattr(saved, name), getattr(item, name)))
                if item.include:
                    saved.reason = item.reason
        data = AnswerQualityBatch(items=list(by_id.values()))
    else:
        data = AnswerClaimBatch(items=collected)
    return StructuredProviderResult(data=data, usage=usage)
