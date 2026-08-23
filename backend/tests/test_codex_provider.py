from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
import pytest

from backend.app.ai.providers.codex import CodexProvider
from backend.app.ai.providers.factory import create_structured_provider
from backend.app.core.config import Settings


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
