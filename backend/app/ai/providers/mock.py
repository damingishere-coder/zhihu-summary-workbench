from __future__ import annotations

import re
import json
import time
from typing import TypeVar

from pydantic import BaseModel

from backend.app.ai.providers.base import (
    StructuredOutputProvider,
    StructuredProviderResult,
    TextGenerationProvider,
    ProviderUsage,
)
from backend.app.schemas.ai import AnswerClaimExtraction
from backend.app.schemas.analysis import (
    AnswerClaimBatch,
    AnswerClaimItem,
    AnswerQualityBatch,
    AnswerQualityItem,
    ArticleGeneration,
    ArticleParagraph,
    ArticleQualityReview,
    ClusterRefinement,
    ClusterRefinementItem,
    OpinionMapData,
)
from backend.app.schemas.draft import DraftRewriteResult
from backend.app.schemas.image import InfographicContentData, InfographicPoint


T = TypeVar("T", bound=BaseModel)


class MockProvider(TextGenerationProvider, StructuredOutputProvider):
    name = "mock"
    model = "deterministic-claim-extractor-v1"

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_role: str,
    ) -> tuple[str, ProviderUsage]:
        started = time.perf_counter()
        text = f"Mock 模式已处理输入：{user_prompt[:120]}"
        usage = ProviderUsage(
            provider=self.name,
            model=self.model,
            model_role=model_role,
            input_tokens=max(1, len(user_prompt) // 2),
            output_tokens=max(1, len(text) // 2),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return text, usage

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model_role: str,
    ) -> StructuredProviderResult[T]:
        started = time.perf_counter()
        if output_schema is not AnswerClaimExtraction:
            data = self._generate_phase_two(output_schema, user_prompt)
            usage = ProviderUsage(
                provider=self.name,
                model=self.model,
                model_role=model_role,
                input_tokens=max(1, len(user_prompt) // 2),
                output_tokens=max(1, len(data.model_dump_json()) // 2),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return StructuredProviderResult(
                data=output_schema.model_validate(data.model_dump()),
                usage=usage,
            )

        answer_match = re.search(r"示例回答：\s*(.+)", user_prompt, re.DOTALL)
        answer = (answer_match.group(1) if answer_match else user_prompt).strip()
        sentences = [
            item.strip("。！？!?；; ")
            for item in re.split(r"[。！？!?；;\n]+", answer)
            if item.strip()
        ]
        claims = sentences[:4] or ["需要先补充可分析的回答内容"]
        summary = "；".join(claims[:2])
        data = AnswerClaimExtraction(
            summary=summary[:1000],
            core_claims=claims,
            supporting_reasons=claims[1:3],
            position="建议型",
            risks_or_limitations=["第一阶段结果用于验证流程，需要人工审核"],
            quality_score=min(92, 55 + len(answer) // 20),
            relevance_score=88,
        )
        usage = ProviderUsage(
            provider=self.name,
            model=self.model,
            model_role=model_role,
            input_tokens=max(1, len(user_prompt) // 2),
            output_tokens=max(1, len(data.model_dump_json()) // 2),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return StructuredProviderResult(
            data=output_schema.model_validate(data.model_dump()),
            usage=usage,
        )

    @staticmethod
    def _input_payload(user_prompt: str) -> dict[str, object]:
        marker = "输入 JSON："
        raw = user_prompt.split(marker, 1)[-1].strip()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("MockProvider 输入必须是 JSON 对象")
        return value

    def _generate_phase_two(
        self, output_schema: type[T], user_prompt: str
    ) -> BaseModel:
        payload = self._input_payload(user_prompt)
        if output_schema is AnswerQualityBatch:
            items: list[AnswerQualityItem] = []
            for answer in payload.get("answers", []):
                if not isinstance(answer, dict):
                    continue
                text = str(answer.get("plain_content") or "")
                base = min(96, 48 + len(text) // 35)
                vote_bonus = min(10, int(answer.get("vote_count") or 0) // 100)
                filtered = bool(answer.get("filter_reason"))
                items.append(
                    AnswerQualityItem(
                        answer_id=str(answer.get("answer_id") or ""),
                        relevance_score=35 if filtered else min(96, base + 8),
                        quality_score=25 if filtered else min(98, base + vote_bonus),
                        information_density=20
                        if filtered
                        else min(95, 50 + len(set(text)) // 20),
                        include=not filtered,
                        reason=str(answer.get("filter_reason") or "内容与问题相关且具备可提取观点"),
                    )
                )
            return AnswerQualityBatch(items=items)

        if output_schema is AnswerClaimBatch:
            items: list[AnswerClaimItem] = []
            for answer in payload.get("answers", []):
                if not isinstance(answer, dict):
                    continue
                text = str(answer.get("plain_content") or "").strip()
                sentences = [
                    item.strip("。！？!?；; ")
                    for item in re.split(r"[。！？!?；;\n]+", text)
                    if len(item.strip()) >= 8
                ]
                claims = sentences[:4] or ["该回答信息不足，需要人工判断"]
                items.append(
                    AnswerClaimItem(
                        answer_id=str(answer.get("answer_id") or ""),
                        summary="；".join(claims[:2])[:1200],
                        core_claims=claims,
                        supporting_reasons=sentences[1:4],
                        examples=sentences[4:6],
                        data_or_evidence=[
                            item for item in sentences if re.search(r"\d", item)
                        ][:4],
                        position="经验建议" if "建议" in text else "分析型",
                        applicable_conditions=[
                            item
                            for item in sentences
                            if any(word in item for word in ("如果", "当", "适合", "前提"))
                        ][:4],
                        risks_or_limitations=[
                            item
                            for item in sentences
                            if any(word in item for word in ("但是", "风险", "不一定", "避免"))
                        ][:4],
                        unique_insights=claims[-1:],
                        possible_factual_claims=[
                            item for item in sentences if re.search(r"\d", item)
                        ][:4],
                        quality_score=min(96, 58 + len(text) // 45),
                        relevance_score=88,
                    )
                )
            return AnswerClaimBatch(items=items)

        if output_schema is ClusterRefinement:
            source = [
                item
                for item in payload.get("rough_clusters", [])
                if isinstance(item, dict)
            ]
            clusters: list[ClusterRefinementItem] = []
            for index, item in enumerate(source):
                claims = [str(value) for value in item.get("claims", []) if value]
                support = len(item.get("answer_ids", []))
                if index == 0 or support >= 3:
                    cluster_type = "consensus"
                elif index == 1:
                    cluster_type = "disagreement"
                elif support <= 1:
                    cluster_type = "minority"
                else:
                    cluster_type = "condition"
                clusters.append(
                    ClusterRefinementItem(
                        source_cluster_indexes=[int(item.get("index", index))],
                        name=(claims[0] if claims else f"观点簇 {index + 1}")[:80],
                        summary="；".join(claims[:3])[:2000]
                        or "该观点簇需要人工命名",
                        cluster_type=cluster_type,
                        opposing_reasons=claims[1:2]
                        if cluster_type == "disagreement"
                        else [],
                        applicable_conditions=[
                            claim
                            for claim in claims
                            if any(word in claim for word in ("如果", "当", "前提"))
                        ][:3],
                        is_mainstream=cluster_type == "consensus",
                        is_minority=cluster_type == "minority",
                        is_controversial=cluster_type == "disagreement",
                        confidence=min(95, 60 + support * 5),
                        information_gain=70 if cluster_type == "minority" else 60,
                    )
                )
            return ClusterRefinement(clusters=clusters)

        if output_schema is OpinionMapData:
            clusters = [
                item for item in payload.get("clusters", []) if isinstance(item, dict)
            ]
            summaries = [str(item.get("summary") or item.get("name") or "") for item in clusters]
            sources = list(
                dict.fromkeys(
                    source
                    for item in clusters
                    for source in item.get("source_answer_ids", [])
                )
            )
            forced = [
                summary
                for summary, item in zip(summaries, clusters, strict=False)
                if item.get("write_policy") == "force"
            ]
            consensus = list(dict.fromkeys(forced + [
                summary
                for summary, item in zip(summaries, clusters, strict=False)
                if item.get("cluster_type") == "consensus"
            ]))
            disagreements = [
                summary
                for summary, item in zip(summaries, clusters, strict=False)
                if item.get("cluster_type") == "disagreement"
            ]
            minority = [
                summary
                for summary, item in zip(summaries, clusters, strict=False)
                if item.get("cluster_type") == "minority"
            ]
            first = (consensus or summaries or ["现有回答需要结合具体条件判断"])[0]
            return OpinionMapData(
                question_summary=str(payload.get("question_title") or ""),
                one_sentence_answer=first[:500],
                main_dimensions=[str(item.get("name") or "") for item in clusters[:8]],
                main_consensus=consensus[:8],
                main_disagreements=disagreements[:8],
                minority_but_valuable_views=minority[:8],
                common_misunderstandings=["高赞不等于结论适用于所有人"],
                applicable_conditions=list(
                    dict.fromkeys(
                        condition
                        for item in clusters
                        for condition in item.get("applicable_conditions", [])
                    )
                )[:8],
                risks=["回答中的数字和高风险事实仍需人工核验"],
                practical_suggestions=[
                    "先确认自己的目标和限制条件",
                    "优先采用多个独立回答共同支持的做法",
                ],
                source_answer_ids=sources,
            )

        if output_schema is ArticleGeneration:
            opinion = payload.get("opinion_map")
            if not isinstance(opinion, dict):
                opinion = {}
            clusters = [
                item for item in payload.get("clusters", []) if isinstance(item, dict)
            ]
            sections = [
                ("p001", "一句话结论", [str(opinion.get("one_sentence_answer") or "")]),
                ("p002", "一、这个问题下，大多数回答的共识是什么", opinion.get("main_consensus", [])),
                ("p003", "二、大家真正存在分歧的地方是什么", opinion.get("main_disagreements", [])),
                ("p004", "三、为什么看起来相互矛盾", opinion.get("applicable_conditions", [])),
                ("p005", "四、哪些观点最值得参考", opinion.get("minority_but_valuable_views", [])),
                ("p006", "五、哪些前提容易被忽略", opinion.get("common_misunderstandings", [])),
                ("p007", "六、综合这些回答，我的总结与建议", opinion.get("practical_suggestions", [])),
            ]
            paragraphs: list[ArticleParagraph] = []
            blocks: list[str] = [f"# {payload.get('question_title', '')}"]
            all_sources = [str(value) for value in opinion.get("source_answer_ids", [])]
            all_cluster_ids = [str(item.get("id")) for item in clusters if item.get("id")]
            for paragraph_id, heading, values in sections:
                clean_values = [str(value) for value in values if value]
                paragraph_text = "。".join(clean_values) or "这一部分尚缺少足够的独立来源，需要人工补充。"
                content = f"## {heading}\n\n{paragraph_text}"
                blocks.append(content)
                paragraphs.append(
                    ArticleParagraph(
                        paragraph_id=paragraph_id,
                        content=paragraph_text,
                        cluster_ids=all_cluster_ids[:4],
                        source_answer_ids=all_sources[:12],
                    )
                )
            notice = "本文由 AI 辅助整理现有回答，观点和事实仍需结合原回答人工核验。"
            blocks.append(f"> {notice}")
            paragraphs.append(
                ArticleParagraph(
                    paragraph_id="p008",
                    content=notice,
                    cluster_ids=[],
                    source_answer_ids=[],
                )
            )
            return ArticleGeneration(
                title=f"{payload.get('question_title', '')}｜多回答综合总结",
                content="\n\n".join(blocks),
                paragraphs=paragraphs,
            )

        if output_schema is ArticleQualityReview:
            article = payload.get("article")
            if not isinstance(article, dict):
                article = {}
            content = str(article.get("content") or "")
            paragraph_sources = article.get("paragraphs", [])
            missing_sources = [
                str(item.get("paragraph_id"))
                for item in paragraph_sources
                if isinstance(item, dict)
                and not item.get("source_answer_ids")
                and item.get("paragraph_id") != "p008"
            ]
            risky = any(
                word in str(payload.get("question_title") or "")
                for word in ("医疗", "法律", "金融", "投资", "疾病", "用药")
            )
            issues = (
                [f"段落 {item} 缺少来源" for item in missing_sources]
                + (["高风险主题必须人工审核"] if risky else [])
            )
            score = max(60, 94 - len(issues) * 8)
            return ArticleQualityReview(
                passed=not missing_sources,
                score=score,
                checks={
                    "covers_consensus": "共识" in content,
                    "covers_disagreement": "分歧" in content,
                    "sources_traceable": not missing_sources,
                    "ai_notice_present": "AI 辅助" in content,
                    "no_absolute_claims": not any(
                        word in content for word in ("百分之百", "绝对", "一定会")
                    ),
                },
                issues=issues,
                risk_level="high" if risky else "normal",
                requires_human_review=True,
                summary="Mock 独立审核已完成；通过前仍需运营人员检查原回答来源。",
            )

        if output_schema is DraftRewriteResult:
            source = str(payload.get("text") or "").strip()
            sentences = [
                item.strip()
                for item in re.split(r"(?<=[。！？!?])", source)
                if item.strip()
            ]
            deduplicated = list(dict.fromkeys(sentences))
            instruction = str(payload.get("instruction") or "")
            if "简洁" in instruction or "精简" in instruction:
                deduplicated = deduplicated[:4]
            rewritten = "".join(deduplicated).strip() or source
            return DraftRewriteResult(text=rewritten)

        if output_schema is InfographicContentData:
            opinion = payload.get("opinion_map")
            if not isinstance(opinion, dict):
                opinion = {}
            clusters = [
                item for item in payload.get("clusters", []) if isinstance(item, dict)
            ]
            consensus_values = [
                str(item) for item in opinion.get("main_consensus", []) if item
            ][:4]
            if not consensus_values:
                consensus_values = [
                    str(item.get("summary") or item.get("name") or "")
                    for item in clusters
                    if item.get("summary") or item.get("name")
                ][:4]
            conclusion = str(
                opinion.get("one_sentence_answer")
                or (consensus_values[0] if consensus_values else "需要结合具体条件判断")
            )
            source_cluster_ids = [
                str(item.get("id")) for item in clusters if item.get("id")
            ][:16]
            return InfographicContentData(
                title=str(payload.get("question_title") or "多回答综合总结")[:48],
                one_line_conclusion=conclusion[:96],
                consensus=[
                    InfographicPoint(
                        title=f"共识 {index}",
                        description=value[:110],
                    )
                    for index, value in enumerate(consensus_values, start=1)
                ],
                disagreements=[
                    str(item)[:96]
                    for item in opinion.get("main_disagreements", [])
                    if item
                ][:4],
                conditions=[
                    str(item)[:96]
                    for item in opinion.get("applicable_conditions", [])
                    if item
                ][:4],
                suggestions=[
                    str(item)[:96]
                    for item in opinion.get("practical_suggestions", [])
                    if item
                ][:4],
                visual_keywords=[
                    str(item)[:20]
                    for item in opinion.get("main_dimensions", [])
                    if item
                ][:8],
                source_cluster_ids=source_cluster_ids,
                source_answer_ids=[
                    str(item)
                    for item in opinion.get("source_answer_ids", [])
                    if item
                ][:100],
            )

        raise TypeError(f"MockProvider 尚未注册结构：{output_schema.__name__}")
