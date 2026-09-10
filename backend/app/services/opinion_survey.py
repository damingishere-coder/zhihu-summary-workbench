"""Reproducible author counts from saved answers and attributed stance links."""
from __future__ import annotations

from collections import defaultdict
import re
from typing import Any
from urllib.parse import urlsplit

from backend.app.schemas.analysis import ArticleGeneration, ArticleParagraph


SURVEY_VERSION = 3
SHORT_ARTICLE_LIMIT = 500
SURVEY_INSTRUCTION = """把同一知乎问题的回答高度汇聚成一篇有阅读吸引力的短文，而不是调查报告或逐项复述。
标题不超过24字，正文目标300至380字。标题、正文及程序追加的样本说明合计不得超过500字。
开头用来源中真实存在的矛盾、反差或具体问题吸引读者；接着用2至3个短段落串起核心发现，
保留一个会改变理解的分歧或条件，结尾落在一个清晰洞察。禁止夸张标题、虚构亲历和制造共识。
不使用编号章节、统计表、作者名单、逐方向罗列或大段方法说明；不要求把所有观点写进短文。
最多选2至3个最有解释力的人数作为叙事支点。人数和占比只能取自survey，不能用点赞数代替人数。
每个内容段关联真实cluster_ids/source_answer_ids；段落content按顺序拼起来应与正文一致。
归纳答主的观点，不以AI身份解答行业问题、不把样本解释当成核实后的事实。
完整统计、作者分组及采集边界留在来源附件，不写进正文。程序会追加简短样本和AI说明，无须重复。
同一作者可以持多个观点，未归类不等于反对，只代表已采集样本。"""


def article_length(title: str, content: str) -> int:
    """Count punctuation and digits too; whitespace alone is not reading copy."""
    return len(re.sub(r"\s+", "", title + content))


def finalize_short_article(article: ArticleGeneration, survey: dict[str, Any]) -> ArticleGeneration:
    paragraphs = [p for p in article.paragraphs if p.kind == 'content']
    if not paragraphs:
        raise ValueError('短文缺少有来源的正文段落')
    notice = (f"样本：保存{survey['collected_answers']}条、分析{survey['analyzed_answers']}条，"
              f"以{survey['denominator']}位可识别作者计数；观点可重叠，仅代表样本。AI辅助整理，待审核。")
    paragraphs.append(ArticleParagraph(paragraph_id='sample_note', kind='disclosure', content=notice))
    content = '\n\n'.join(p.content for p in paragraphs)
    count = article_length(article.title, content)
    if count > SHORT_ARTICLE_LIMIT:
        raise ValueError(f'短文共{count}字，超过500字上限；请压缩核心发现，不能截断来源或结论')
    return ArticleGeneration(title=article.title, content=content, paragraphs=paragraphs)


def author_key(url: str) -> str | None:
    """Display names are not identities; unknown/anonymous answers stay separate."""
    parsed = urlsplit(url.strip())
    parts = parsed.path.strip('/').split('/')
    if parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'www.zhihu.com', 'zhihu.com'}:
        return None
    if len(parts) != 2 or parts[0] not in {'people', 'org'} or not parts[1]:
        return None
    if parts[1].lower() in {'anonymous', 'anonymous-user'}:
        return None
    return '/'.join(parts)


def combined_relation(relations: set[str]) -> str:
    if 'mixed' in relations or ('opposes' in relations and relations & {'supports', 'conditional'}):
        return 'mixed'
    if 'conditional' in relations:
        return 'conditional'
    if 'supports' in relations:
        return 'supports'
    if 'opposes' in relations:
        return 'opposes'
    return 'related'


def build_survey(answers: list[dict[str, Any]], clusters: list[dict[str, Any]]) -> dict[str, Any]:
    answers_by_id = {str(a['id']): a for a in answers}
    identities = {key: author_key(str(a.get('author_url') or '')) for key, a in answers_by_id.items()}
    authors = {value for value in identities.values() if value}
    denominator = len(authors)
    classified: set[str] = set()
    rows = []
    for cluster in clusters:
        by_author: dict[str, set[str]] = defaultdict(set)
        evidence = []
        unknown = set()
        for answer_id, relation in cluster.get('source_relations', {}).items():
            if answer_id not in answers_by_id:
                raise ValueError('观点统计引用了未保存的回答')
            answer = answers_by_id[answer_id]
            identity = identities[answer_id]
            if identity:
                by_author[identity].add(relation)
            else:
                unknown.add(answer_id)
            evidence.append({'answer_id': answer_id, 'author_key': identity,
                             'author_name': answer.get('author_name', '匿名用户'),
                             'answer_url': answer.get('answer_url', ''), 'relation': relation,
                             'quote': cluster.get('source_evidence_quotes', {}).get(answer_id, '')})
        groups: dict[str, list[str]] = {key: [] for key in ('supports', 'opposes', 'conditional', 'mixed', 'related')}
        for identity, relations in by_author.items():
            stance = combined_relation(relations)
            groups[stance].append(identity)
            if stance != 'related':
                classified.add(identity)
        counts = {key: len(value) for key, value in groups.items()}
        endorsement_count = counts['supports'] + counts['conditional']
        rows.append({'cluster_id': cluster['id'], 'name': cluster['name'], 'summary': cluster['summary'],
                     'counts': counts, 'support_percent': round(counts['supports'] * 100 / denominator, 1) if denominator else None,
                     'endorsement_count': endorsement_count,
                     'endorsement_percent': round(endorsement_count * 100 / denominator, 1) if denominator else None,
                     'author_groups': {k: sorted(v) for k, v in groups.items()},
                     'unidentified_answer_count': len(unknown), 'evidence': evidence})
    rows.sort(key=lambda row: (-row['endorsement_count'], -sum(row['counts'].values()), row['cluster_id']))
    unclassified_records = []
    for identity in sorted(authors - classified):
        sources = [a for aid, a in answers_by_id.items() if identities[aid] == identity]
        unclassified_records.append({'author_key': identity,
            'author_name': sources[0].get('author_name', '匿名用户'),
            'answer_ids': sorted(str(a['id']) for a in sources),
            'analyzed_answer_ids': sorted(str(a['id']) for a in sources if a.get('included_for_analysis')),
            'excluded_answer_ids': sorted(str(a['id']) for a in sources if not a.get('included_for_analysis'))})
    return {'version': SURVEY_VERSION, 'unit': 'identified_author', 'denominator': denominator,
            'collected_answers': len(answers_by_id),
            'analyzed_answers': sum(bool(a.get('included_for_analysis')) for a in answers_by_id.values()),
            'unidentified_answers': sum(value is None for value in identities.values()),
            'unclassified_authors': len(authors - classified),
            'unclassified_author_records': unclassified_records, 'rows': rows,
            'method': '按公开作者主页去重，同一观点每位作者只计一次。认同人数为明确支持与有条件认同之和；认同与反对并存记为混合态度，单独列出。命题本身带条件不等于作者有保留；作者明确保留认同条件时单列。多观点可重叠，占比不必合计100%。未归类不等于反对。'}


def survey_paragraphs(survey: dict[str, Any], answer_ids: list[str]) -> list[ArticleParagraph]:
    n = survey['denominator']
    scope = (f"## 采集与统计范围\n本次保存 {survey['collected_answers']} 条回答，其中 {survey['analyzed_answers']} 条参与观点分析。"
             f"按公开主页去重识别出 {n} 位回答作者，以下占比均以这 {n} 位作者为分母。"
             f"另有 {survey['unidentified_answers']} 条匿名或身份不明回答不计入人数；{survey['unclassified_authors']} 位作者尚未判定明确态度（包含未参与分析、仅相关提及或未涉及各统计观点的情况）。"
             f"\n{survey['method']}本统计仅代表已保存样本，不代表全部回答作者。")
    result = [ArticleParagraph(paragraph_id='survey_scope', content=scope, source_answer_ids=answer_ids)]
    for index, row in enumerate(survey['rows']):
        counts = row['counts']
        percent = f"{row['endorsement_percent']:.1f}%" if n else '无法计算'
        heading = '\n## 各观点有多少人\n' if index == 0 else ''
        content = f"{heading}- {row['name']}：认同 {row['endorsement_count']} 人（{percent}）"
        if counts['conditional']:
            content += f"，其中明确支持 {counts['supports']} 人、有条件认同 {counts['conditional']} 人"
        for key, label in [('opposes', '反对'), ('mixed', '混合态度'), ('related', '仅相关提及')]:
            if counts[key]:
                content += f"；{label} {counts[key]} 人"
        if row['unidentified_answer_count']:
            content += f"；身份不明来源 {row['unidentified_answer_count']} 条"
        content += '。'
        result.append(ArticleParagraph(paragraph_id=f'survey_{index}', content=content,
                     cluster_ids=[row['cluster_id']], source_answer_ids=[a['answer_id'] for a in row['evidence']]))
    unclassified = survey.get('unclassified_author_records', [])
    if unclassified:
        analyzed = [a for a in unclassified if a['analyzed_answer_ids']]
        excluded = [a for a in unclassified if not a['analyzed_answer_ids']]
        names = lambda rows: '、'.join(a['author_name'] for a in rows) or '无'
        result.append(ArticleParagraph(paragraph_id='survey_unclassified',
            content=(f"## 未判定明确态度的作者\n已分析但未判定明确态度 {len(analyzed)} 位：{names(analyzed)}。"
                     f"\n未参与观点分析 {len(excluded)} 位：{names(excluded)}。上述两组均计入已保存作者分母，均不视为反对者；"
                     "同名作者按各自主页区分，回答 ID 与分析状态随统计快照保存。"),
            source_answer_ids=[aid for a in unclassified for aid in a['answer_ids']]))
    return result
