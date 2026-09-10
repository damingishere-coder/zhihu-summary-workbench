"""Reproducible author counts from saved answers and attributed stance links."""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit

from backend.app.schemas.analysis import ArticleParagraph


SURVEY_VERSION = 3
SURVEY_INSTRUCTION = """本产品输出的是该问题下回答作者的观点调查汇总。不要以自己的身份解答原问题，
不要推算题目中的行业数据或提出自己的解释。survey 是程序按作者主页去重得到的统计快照，
人数、占比、分母只能引用 survey，点赞数、来源数和观点条数都不是人数。
正文从‘## 回答里的共性’开始，再写‘## 主要分歧与少数观点’及‘## 这份样本能说明什么’。
写清答主们重复表达的观点、理由、相同前提以及相反/有条件的态度，使用‘这些回答认为’等归纳口吻，
每段关联实际 cluster_ids/source_answer_ids。不得把样本观点写成已经核实的客观事实。
采集范围及逐观点人数由程序在正文前统一插入，不要重复生成统计表，不使用虚构数字或未提供的百分比。
无法识别身份的回答不计入作者人数；未分析/未归类不是反对；允许同一作者持多个观点，占比不必合计100%。
只说明已采集样本，不宣称代表全体知乎用户。"""


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
             f"另有 {survey['unidentified_answers']} 条匿名或身份不明回答不计入人数；{survey['unclassified_authors']} 位作者尚未判定明确态度（仅相关提及或未涉及各统计观点）。"
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
