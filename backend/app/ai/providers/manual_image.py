from __future__ import annotations

from backend.app.ai.providers.base import ImageGenerationProvider
from backend.app.schemas.ai import ImageWorkflowCapability


class ManualImageWorkflowProvider(ImageGenerationProvider):
    """第三阶段手动生图工作流的能力声明；不会调用任何图片 API。"""

    def capability(self) -> ImageWorkflowCapability:
        return ImageWorkflowCapability()

