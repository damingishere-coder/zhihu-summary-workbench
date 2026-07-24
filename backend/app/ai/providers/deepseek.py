from __future__ import annotations

import asyncio
import json
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.app.ai.providers.base import (
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUsage,
    StructuredOutputProvider,
    StructuredProviderResult,
    TextGenerationProvider,
)
from backend.app.core.config import Settings


T = TypeVar("T", bound=BaseModel)


class DeepSeekProvider(TextGenerationProvider, StructuredOutputProvider):
    name = "deepseek"

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.deepseek_key_value:
            raise ProviderConfigurationError(
                "未配置 DEEPSEEK_API_KEY，请在本机 .env 中配置后重试"
            )

    def _model_for_role(self, model_role: str) -> str:
        mapping = {
            "fast_text_model": self.settings.deepseek_fast_model,
            "reasoning_model": self.settings.deepseek_reasoning_model,
            "fallback_text_model": self.settings.deepseek_fallback_model,
        }
        return mapping.get(model_role, self.settings.deepseek_fast_model)

    async def _request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_role: str,
        structured: bool,
    ) -> tuple[str, ProviderUsage]:
        url = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"
        started = time.perf_counter()
        last_error: Exception | None = None
        primary_model = self._model_for_role(model_role)
        fallback_model = self._model_for_role("fallback_text_model")
        models = [primary_model]
        if model_role != "fallback_text_model" and fallback_model != primary_model:
            models.append(fallback_model)
        retry_count = 0
        for model_index, model in enumerate(models):
            payload: dict[str, object] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            }
            if structured:
                payload["response_format"] = {"type": "json_object"}
            for attempt in range(3 if model_index == 0 else 1):
                try:
                    async with httpx.AsyncClient(
                        timeout=self.settings.ai_request_timeout_seconds
                    ) as client:
                        response = await client.post(
                            url,
                            headers={
                                "Authorization": (
                                    f"Bearer {self.settings.deepseek_key_value}"
                                ),
                                "Content-Type": "application/json",
                            },
                            json=payload,
                        )
                        response.raise_for_status()
                        body = response.json()
                    content = body["choices"][0]["message"]["content"]
                    usage_payload = body.get("usage", {})
                    input_tokens = int(usage_payload.get("prompt_tokens", 0))
                    output_tokens = int(usage_payload.get("completion_tokens", 0))
                    return content, ProviderUsage(
                        provider=self.name,
                        model=model,
                        model_role=model_role,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        estimated_cost=(
                            input_tokens
                            * self.settings.deepseek_input_cost_per_million
                            + output_tokens
                            * self.settings.deepseek_output_cost_per_million
                        )
                        / 1_000_000,
                        fallback_used=model_index > 0,
                        retry_count=retry_count,
                    )
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                    last_error = exc
                    retry_count += 1
                    if attempt < 2 and model_index == 0:
                        await asyncio.sleep(0.5 * (2**attempt))
        raise ProviderResponseError(f"DeepSeek 请求失败：{last_error}")

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_role: str,
    ) -> tuple[str, ProviderUsage]:
        return await self._request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_role=model_role,
            structured=False,
        )

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model_role: str,
    ) -> StructuredProviderResult[T]:
        schema_prompt = (
            f"{system_prompt}\n\n只返回一个 JSON 对象，并严格满足以下 JSON Schema：\n"
            f"{json.dumps(output_schema.model_json_schema(), ensure_ascii=False)}"
        )
        content, usage = await self._request(
            system_prompt=schema_prompt,
            user_prompt=user_prompt,
            model_role=model_role,
            structured=True,
        )
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        try:
            data = output_schema.model_validate_json(cleaned)
        except (ValidationError, json.JSONDecodeError) as exc:
            repair_prompt = (
                "以下模型输出不是有效的目标 JSON。只修复 JSON 结构和字段类型，"
                "不要补充新事实；返回一个 JSON 对象：\n\n"
                f"{cleaned}"
            )
            repaired, repair_usage = await self._request(
                system_prompt=(
                    "你是 JSON 修复器。输出必须严格满足这个 JSON Schema：\n"
                    f"{json.dumps(output_schema.model_json_schema(), ensure_ascii=False)}"
                ),
                user_prompt=repair_prompt,
                model_role=model_role,
                structured=True,
            )
            repaired = repaired.strip()
            if repaired.startswith("```"):
                repaired = repaired.removeprefix("```json").removeprefix("```")
                repaired = repaired.removesuffix("```").strip()
            try:
                data = output_schema.model_validate_json(repaired)
            except (ValidationError, json.JSONDecodeError) as repair_exc:
                raise ProviderResponseError(
                    f"DeepSeek 结构化输出自动修复失败：{repair_exc}"
                ) from repair_exc
            usage.input_tokens += repair_usage.input_tokens
            usage.output_tokens += repair_usage.output_tokens
            usage.duration_ms += repair_usage.duration_ms
            usage.estimated_cost += repair_usage.estimated_cost
            usage.retry_count += repair_usage.retry_count + 1
            usage.fallback_used = (
                usage.fallback_used or repair_usage.fallback_used
            )
        return StructuredProviderResult(data=data, usage=usage)
