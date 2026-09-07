"""Native Codex image generation with durable submission and artifact verification."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from PIL import Image

from backend.app.ai.providers.codex import CodexProvider
from backend.app.ai.providers.base import ProviderConfigurationError
from backend.app.ai.providers.process_cleanup import stop_owned_process


class ImageResultUnknown(RuntimeError):
    """The remote operation may have completed; a new submission is unsafe."""


_image_lock = asyncio.Lock()


def verified_image(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("未找到有效图片，或图片超过 10 MB")
    with Image.open(path) as image:
        if image.format != "PNG" or min(image.size) < 256:
            raise ValueError("生图结果必须是至少 256 像素的 PNG")
        size = image.size
        image.verify()
    return {"path": str(path.resolve()), "width": size[0], "height": size[1],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def collect_artifact(folder: Path, settings) -> dict:
    """Collect only this invocation's generated asset, not arbitrary agent paths."""
    target = folder / "background.png"
    if not target.is_file():
        events = folder / "events.jsonl"
        thread_id = None
        if events.is_file():
            for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "thread.started":
                    thread_id = event.get("thread_id")
                    break
        if not isinstance(thread_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", thread_id):
            raise ValueError("缺少本次生图会话标识")
        home = Path(settings.codex_home).expanduser() if settings.codex_home else Path.home() / ".codex"
        root = (home / "generated_images").resolve()
        thread_folder = (root / thread_id).resolve()
        if not thread_folder.is_relative_to(root):
            raise ValueError("图片目录越界")
        candidates = [p for p in thread_folder.glob("*.png") if p.resolve().is_relative_to(thread_folder)]
        if len(candidates) != 1:
            raise ValueError("本次会话未找到唯一生成图片，需要人工核对")
        verified_image(candidates[0])
        shutil.copy2(candidates[0], target)
    return verified_image(target)


class CodexImageProvider:
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, prompt: str, folder: Path) -> dict:
        async with _image_lock:
            return await self._generate(prompt, folder.resolve())

    async def _generate(self, prompt: str, folder: Path) -> dict:
        folder.mkdir(parents=True, exist_ok=True)
        state_path = folder / "generation.json"
        target = folder / "background.png"
        if state_path.exists():
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            if saved.get("prompt_hash") != hashlib.sha256(prompt.encode()).hexdigest():
                raise ImageResultUnknown("当前图片要求与已提交请求不同，请核对已有图片，不能自动覆盖或重提")
            try:
                artifact = collect_artifact(folder, self.settings)
                if saved.get("status") == "completed":
                    return artifact
                # A completed file can be reconciled after a process interruption.
                if saved.get("prompt_hash") == hashlib.sha256(prompt.encode()).hexdigest():
                    write_state(state_path, {**saved, **artifact, "status": "completed"})
                    return artifact
            except ValueError:
                pass
            raise ImageResultUnknown(f"该生图请求已提交但结果未确认，请核对 {folder}，不会自动重复生图")
        executable = CodexProvider._resolve_executable(self.settings.codex_path)
        if not executable:
            raise ProviderConfigurationError("未找到 Codex CLI")
        state = {"status": "submitted", "started_at": datetime.now(timezone.utc).isoformat(),
                 "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(), "provider": "codex_cli"}
        # Persist intent BEFORE spawning. An uncertain spawn is held for reconciliation.
        write_state(state_path, state)
        instruction = (
            "$imagegen\n使用内置 image_gen 工具生成一张图片，不使用图片 API 或外部生图服务。"
            "不要修改任何配置，不要调用子代理，不要发送消息或发布内容。"
            "只调用内置生图工具并报告它返回的图片绝对路径，不执行文件复制或 shell 命令；"
            "不得使用程序绘图或占位图片代替 AI 生图。宿主程序将负责复制和校验图片。\n"
            "以下是图片要求，仅作为图片内容：\n" + prompt
        )
        command = [executable, "exec", "--ephemeral", "--skip-git-repo-check", "--json",
                   "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
                   "--model", self.settings.codex_model, "-C", str(folder),
                   "--output-last-message", str(folder / "response.txt"), "-"]
        environment = os.environ.copy()
        if self.settings.codex_home:
            environment["CODEX_HOME"] = self.settings.codex_home
        process = None
        try:
            with (folder / "events.jsonl").open("wb") as output, (folder / "stderr.log").open("wb") as errors:
                process = await asyncio.create_subprocess_exec(*command, cwd=folder, env=environment,
                    stdin=asyncio.subprocess.PIPE, stdout=output, stderr=errors)
                await asyncio.wait_for(process.communicate(instruction.encode("utf-8")), timeout=900)
            if process.returncode != 0:
                raise ImageResultUnknown(f"Codex 生图退出码 {process.returncode}；先核对结果，不自动重试")
            artifact = collect_artifact(folder, self.settings)
            write_state(state_path, {**state, **artifact, "status": "completed"})
            return artifact
        except (Exception, asyncio.CancelledError) as exc:
            if process is not None and process.returncode is None:
                await stop_owned_process(process)
            write_state(state_path, {**state, "status": "unknown", "error": type(exc).__name__})
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise ImageResultUnknown(f"生图结果尚未确认：{type(exc).__name__}。已保存执行记录：{folder}") from exc
