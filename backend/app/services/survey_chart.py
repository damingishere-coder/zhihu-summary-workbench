"""HTML chart with deterministic counts; suitable for the existing PNG renderer."""
from html import escape


def survey_chart_html(payload: dict, width: int, height: int) -> str:
    survey = payload['opinion_survey']
    rows = survey['rows'][:8]
    denominator = survey['denominator']
    blocks = []
    for i, row in enumerate(rows, 1):
        counts = row['counts']
        percent = f"{row['support_percent']:.1f}%" if denominator else '无可识别作者'
        bar_width = row['support_percent'] or 0
        blocks.append(f'''<section class="row">
          <div class="safe-text" data-field="观点"><b>{i:02d}</b> {escape(row['name'])}</div>
          <div class="bar-line"><div class="track"><div class="bar" style="width:{bar_width}%"></div></div>
          <strong class="safe-text" data-field="支持人数">{counts['supports']} 人 · {percent}</strong></div>
          <p class="safe-text" data-field="其他态度">反对 {counts['opposes']} · 有条件认同 {counts['conditional']} · 混合 {counts['mixed']} · 仅提及 {counts['related']} 人</p>
        </section>''')
    common = [r for r in survey['rows'] if r['counts']['supports'] >= 2][:2]
    themes = ''.join(f"<p class='safe-text' data-field='共同观点'>• {escape(r['summary'][:100])}{'…' if len(r['summary']) > 100 else ''}</p>" for r in common)
    if not themes:
        themes = '<p class="safe-text" data-field="共同观点">当前已归类样本中，尚无至少两位可识别作者明确支持的共同观点。</p>'
    title = escape(payload.get('question_title') or payload.get('title') or '回答观点汇总')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
    * {{ box-sizing:border-box }} body {{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#18334e;background:#edf2f8}}
    .canvas {{width:{width}px;height:{height}px;padding:48px 60px;background:#f7f9fd}}
    .kicker {{color:#3967cc;font-size:22px;font-weight:700;letter-spacing:3px}}
    h1 {{font-size:38px;line-height:1.5;margin:18px 0;overflow-wrap:anywhere}}
    .scope {{background:#e8efff;padding:22px 26px;border-radius:16px;font-size:24px;line-height:1.6}}
    h2 {{font-size:27px;margin:26px 0 12px}} .row {{padding:17px 0;border-bottom:1px solid #d9e1ef;font-size:25px;line-height:1.5}}
    b {{color:#7391c7;margin-right:8px}} .bar-line {{display:flex;align-items:center;gap:22px;margin:9px 0}}
    .track {{flex:1;background:#e1e8f4;height:16px;border-radius:8px}} .bar {{height:16px;background:#3967cc;border-radius:8px}}
    strong {{min-width:210px;font-size:23px}} p {{font-size:21px;line-height:1.6;margin:5px 0;overflow-wrap:anywhere}}
    .themes {{background:white;border-radius:14px;padding:20px 25px;margin-top:24px}}
    .footer {{font-size:19px;line-height:1.65;color:#546880;margin-top:24px;border-top:2px solid #d9e1ef;padding-top:18px}}
    </style><main class="canvas"><div class="kicker">回答作者 · 观点调查</div>
    <h1 class="safe-text" data-field="问题">{title}</h1>
    <div class="scope safe-text" data-field="采集范围">保存 {survey['collected_answers']} 条回答 · 分析 {survey['analyzed_answers']} 条<br>
    识别 {denominator} 位作者 · 未归类 {survey['unclassified_authors']} 位 · 身份不明 {survey['unidentified_answers']} 条回答</div>
    <h2>各观点的明确支持人数</h2><p class="safe-text" data-field="图表口径">占比以 {denominator} 位可识别作者为分母；展示 {len(rows)}/{len(survey['rows'])} 个观点，完整分布及来源见正文。</p>
    {''.join(blocks)}<div class="themes"><h2>回答中重复出现的观点</h2>{themes}</div>
    <div class="footer">{escape(survey['method'])}<br>仅代表已采集样本，未确认覆盖全部回答。匿名来源单列；归类由 AI 辅助，原回答和完整统计随文章版本保存。</div>
    </main></html>'''
