from __future__ import annotations

from backend.app.ai.providers.base import ImageGenerationProvider
from backend.app.schemas.ai import ImageWorkflowCapability
from backend.app.schemas.analysis import OpinionMapData


class ManualImageWorkflowProvider(ImageGenerationProvider):
    """手动生图工作流；只生成 Prompt，不调用任何图片 API。"""

    def capability(self) -> ImageWorkflowCapability:
        return ImageWorkflowCapability()

    def infographic_content(
        self, *, question_title: str, opinion_map: OpinionMapData
    ) -> dict[str, object]:
        return {
            "title": question_title[:48],
            "one_line_conclusion": opinion_map.one_sentence_answer[:90],
            "consensus": [
                {"title": f"共识 {index}", "description": item[:90]}
                for index, item in enumerate(opinion_map.main_consensus[:4], start=1)
            ],
            "disagreements": [item[:90] for item in opinion_map.main_disagreements[:3]],
            "conditions": [item[:72] for item in opinion_map.applicable_conditions[:3]],
            "suggestions": [item[:72] for item in opinion_map.practical_suggestions[:3]],
            "visual_keywords": list(
                dict.fromkeys(opinion_map.main_dimensions[:6] + ["知识整理", "观点关系"])
            ),
            "source_answer_ids": opinion_map.source_answer_ids,
        }

    def prompts(
        self,
        *,
        question_title: str,
        infographic: dict[str, object],
        visual_style: str,
        aspect_ratio: str,
    ) -> tuple[str, str]:
        keywords = "、".join(str(item) for item in infographic.get("visual_keywords", []))
        prompt_zh = f"""主题：围绕“{question_title}”的知识总结信息图背景。
使用场景：知乎长回答开头的“一图看懂”封面底图，后续会由 HTML/CSS 叠加准确中文。
画面主体：用抽象但可理解的视觉隐喻表现 {keywords or "观点、共识与分歧"}。
构图：竖版 {aspect_ratio}，主体位于下半部或边缘，中上部保留大面积安静的文字区域。
视觉风格：{visual_style}，专业、克制、可信，适合内容运营工作台。
色彩：浅灰白底、安静蓝色主色、少量暖橙强调；不使用荧光色和大面积渐变。
背景复杂度：低，层次清楚，不抢夺后续文字注意力。
尺寸与比例：建议 1080×1440，比例 {aspect_ratio}。
禁止：水印、Logo、二维码、人物肖像特写、密集小元素、发光特效、可识别品牌。
硬性要求：图片内不得生成中文、英文、数字或任何文字；不要绘制文字占位符。"""
        prompt_en = f"""Create a restrained editorial background illustration for a knowledge-summary infographic about "{question_title}".
Use case: the opening visual of a Zhihu long-form answer. Accurate Chinese copy will be overlaid later with HTML/CSS.
Subject: an abstract but understandable metaphor for {keywords or "opinions, consensus, and disagreement"}.
Composition: vertical {aspect_ratio}; keep a large calm negative-space area in the upper and central zones for copy.
Style: {visual_style}; professional, calm, trustworthy, editorial, low visual noise.
Palette: off-white and cool gray, quiet blue as the primary accent, very limited warm orange.
Suggested size: 1080×1440.
Do not include logos, watermarks, QR codes, recognizable brands, portrait close-ups, neon glow, or dense decorative details.
Hard constraint: no Chinese characters, English letters, numbers, captions, labels, or any other text inside the image."""
        return prompt_zh, prompt_en
