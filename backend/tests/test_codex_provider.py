from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
import pytest

from backend.app.ai.providers.codex import (
    CodexProvider,
    _safe_cli_error,
    _strict_json_schema,
)
from backend.app.ai.providers.factory import create_structured_provider
from backend.app.core.config import Settings
from backend.app.schemas.analysis import AnswerQualityBatch, ArticleQualityReview


class DemoResult(BaseModel):
    status: str


class FakeProcess:
    def __init__(self, command: tuple[str, ...]):
        self.command = command
        self.returncode: int | None = None

    async def communicate(self, input_bytes: bytes):
        assert b"<user_material>" in input_bytes
        output_path = Path(self.command[self.command.index("--output-last-message") + 1])
        output_path.write_text('{"status":"ok"}', encoding="utf-8")
        self.returncode = 0
        return b"", b""

    def kill(self) -> None:
        self.returncode = -1

    async def wait(self) -> int:
        return self.returncode or 0


@pytest.mark.asyncio
async def test_codex_structured_provider_uses_schema_and_validates(monkeypatch) -> None:
    captured: dict[str, tuple[str, ...]] = {}
    monkeypatch.setattr("backend.app.ai.providers.codex.shutil.which", lambda _: "codex.cmd")

    async def fake_subprocess(*command, **kwargs):
        captured["command"] = command
        return FakeProcess(command)

    monkeypatch.setattr("backend.app.ai.providers.codex.asyncio.create_subprocess_exec", fake_subprocess)
    provider = CodexProvider(Settings(_env_file=None, codex_model="gpt-test"))

    result = await provider.generate_structured(
        system_prompt="只返回状态",
        user_prompt="测试材料",
        output_schema=DemoResult,
        model_role="fast_text_model",
    )

    assert result.data.status == "ok"
    assert result.usage.provider == "codex"
    assert result.usage.model == "gpt-test"
    assert result.usage.input_tokens == 0
    assert "--output-schema" in captured["command"]
    assert "--sandbox" in captured["command"]
    assert "--ephemeral" in captured["command"]


def test_factory_creates_codex_provider(monkeypatch) -> None:
    monkeypatch.setattr("backend.app.ai.providers.codex.shutil.which", lambda _: "codex.cmd")
    provider = create_structured_provider("codex", Settings(_env_file=None))
    assert isinstance(provider, CodexProvider)


def test_cli_error_detail_does_not_copy_prompt_material() -> None:
    detail = _safe_cli_error(
        "user\n网页中的不可信回答和私人材料\nERROR: invalid output schema\n".encode()
    )

    assert detail == "ERROR: invalid output schema"
    assert "不可信回答" not in detail


def test_cli_error_detail_extracts_only_safe_multiline_error_message() -> None:
    detail = _safe_cli_error(
        (
            'user\n{"message":"网页里的普通字段"}\n'
            'ERROR: {\n  "error": {\n'
            '    "message": "Invalid schema for response_format answer_quality",\n'
            '    "type": "invalid_request_error"\n  }\n}\n'
        ).encode()
    )

    assert detail == "ERROR: Invalid schema for response_format answer_quality"
    assert "网页里的普通字段" not in detail


@pytest.mark.parametrize("model", [AnswerQualityBatch, ArticleQualityReview])
def test_strict_schema_closes_every_object_and_requires_every_property(model) -> None:
    schema = _strict_json_schema(model.model_json_schema())

    def assert_strict(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                assert_strict(item)
            return
        if not isinstance(value, dict):
            return
        assert "default" not in value
        if value.get("type") == "object" or "properties" in value:
            properties = value.get("properties", {})
            assert value["additionalProperties"] is False
            assert value["required"] == list(properties)
        for item in value.values():
            assert_strict(item)

    assert_strict(schema)
