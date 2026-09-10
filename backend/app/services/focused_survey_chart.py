"""A compact, deterministic statistical figure from the frozen author survey."""
from html import escape
from math import ceil, floor, log10


def focused_rows(survey: dict) -> list[dict]:
    # Select by the actual measure drawn, including conditional endorsement.
    return sorted(survey['rows'], key=lambda r: -(r['counts']['supports'] + r['counts']['conditional']))[:5]


def focused_survey_chart_html(payload: dict, width: int, height: int) -> str:
    survey = payload['opinion_survey']
    rows = focused_rows(survey)
    denominator = survey['denominator']
    maximum = max((r['counts']['supports'] + r['counts']['conditional'] for r in rows), default=0)
    rough_step = max(1, maximum / 4)
    magnitude = 10 ** floor(log10(rough_step))
    step = next(x * magnitude for x in (1, 2, 5, 10) if x * magnitude >= rough_step)
    ceiling = max(step, ceil(maximum / step) * step)
    plot_left, plot_width = 0, 750
    marks = []
    for tick in range(0, int(ceiling) + 1, int(step)):
        x = plot_left + tick / ceiling * plot_width
        marks.append(f'<line x1="{x}" x2="{x}" y1="42" y2="{len(rows) * 155 + 30}" stroke="#e1e5e9" stroke-width="1"/>'
                     f'<text x="{x}" y="24" text-anchor="middle" fill="#71808d" font-size="21">{tick}</text>')
    for index, row in enumerate(rows):
        count = row['counts']['supports'] + row['counts']['conditional']
        percent = f'{count / denominator * 100:.1f}%' if denominator else '占比不适用'
        y = 75 + index * 155
        bar_width = count / ceiling * plot_width
        marks.append(f'<g class="chart-row" data-cluster-id="{escape(str(row["cluster_id"]), quote=True)}" data-count="{count}">'
                     f'<rect x="0" y="{y - 33}" width="910" height="47" fill="#ffffff"/>'
                     f'<text x="0" y="{y}" fill="#223645" font-size="29">{escape(row["name"])}</text>'
                     f'<rect x="0" y="{y + 25}" width="{bar_width:.4f}" height="36" fill="#207c83"/>'
                     f'<text x="{bar_width + 18:.4f}" y="{y + 54}" fill="#163b45" font-size="29" font-weight="700">{count}'
                     f'<tspan fill="#73828c" font-size="23" font-weight="400"> 人 · {percent}</tspan></text></g>')
    if not rows:
        marks.append('<text x="0" y="100" font-size="30">当前样本尚无可绘制的观点</text>')
    title = escape(str(payload.get('title') or '回答里的观点分布'))
    footer = f'认同＝明确支持＋有条件认同；占比以 {denominator} 位可识别作者为分母。'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
    *{{box-sizing:border-box}}body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#223645}}
    .canvas{{width:{width}px;height:{height}px;background:#fff;position:relative;padding:65px 70px}}
    .kicker{{font-size:23px;letter-spacing:3px;color:#207c83;font-weight:700;border-left:6px solid #207c83;padding-left:15px}}
    h1{{font-size:48px;line-height:1.6;margin:24px 0 16px;padding:4px 0;overflow-wrap:anywhere}}
    .subtitle{{font-size:25px;color:#60717e;line-height:1.8;margin:0 0 25px}}
    .chart{{display:block;width:100%;height:auto;overflow:visible}}
    .foot{{position:absolute;left:70px;right:70px;bottom:55px;border-top:1px solid #dbe1e5;padding-top:20px;font-size:21px;line-height:1.9;color:#697985}}
    .source{{color:#87949c;font-size:20px}}
    </style><main class="canvas"><div class="kicker safe-text" data-field="图表类型">知乎回答 · 观点分布</div>
    <h1 class="safe-text" data-field="标题">{title}</h1>
    <p class="subtitle safe-text" data-field="样本">{denominator} 位可识别作者 · 认同人数前 {len(rows)} 项 / 共 {len(survey['rows'])} 项</p>
    <svg class="chart" viewBox="-12 0 940 850" role="img" aria-label="各观点认同人数横向条形图">{''.join(marks)}</svg>
    <footer class="foot"><div class="safe-text" data-field="计数口径">{footer}</div>
    <div class="safe-text" data-field="重叠说明">同一作者可认同多个观点；未认同不等于反对，占比不必合计 100%。</div>
    <div class="source safe-text" data-field="来源">来源：本题保存 {survey['collected_answers']} 条回答，分析 {survey['analyzed_answers']} 条 · AI 辅助归类</div>
    <div class="source safe-text" data-field="范围">仅代表已采集样本，未确认覆盖全部回答；完整统计与来源见文章附件。</div></footer>
    </main></html>'''
