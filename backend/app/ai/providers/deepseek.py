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
        model = self._model_for_role(model_role)
        url = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"
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

        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=self.settings.ai_request_timeout_seconds
                ) as client:
                    response = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {self.settings.deepseek_key_value}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    body = response.json()
                content = body["choices"][0]["message"]["content"]
                usage_payload = body.get("usage", {})
                return content, ProviderUsage(
                    provider=self.name,
                    model=model,
                    model_role=model_role,
                    input_tokens=int(usage_payload.get("prompt_tokens", 0)),
                    output_tokens=int(usage_payload.get("completion_tokens", 0)),
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
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
            raise ProviderResponseError(f"DeepSeek 结构化输出校验失败：{exc}") from exc
        return StructuredProviderResult(data=data, usage=usage)

