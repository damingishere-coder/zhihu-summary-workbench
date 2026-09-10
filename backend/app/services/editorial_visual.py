"""One editorial image supporting the short article; statistics stay in its snapshot."""
from html import escape


def editorial_visual_html(payload: dict, width: int, height: int, background: str) -> str:
    title = escape(str(payload.get('title') or '回答里的共同线索'))
    if len(title) > 12:
        title = title.replace('，', '，<br>', 1)
    survey = payload.get('opinion_survey', {})
    sample = survey.get('collected_answers', 0)
    picture = f'<img class="art" alt="主题插画" src="{escape(background, quote=True)}">' if background else ''
    footer = '模拟配图 · 未调用真实生图' if payload.get('mock_preview') else '主题插画 · AI辅助整理 · 仅代表已采集样本'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>
    *{{box-sizing:border-box}}body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#173b34}}
    .canvas{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:#f5efdf}}
    .art{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
    header{{position:relative;padding:65px 70px 0;max-width:100%}}
    .kicker{{font-size:25px;letter-spacing:3px;font-weight:600;color:#886447}}
    h1{{font-size:78px;line-height:1.5;max-width:900px;margin:26px 0 0;padding:4px 0 8px;overflow-wrap:anywhere;letter-spacing:-2px}}
    .footer{{position:absolute;bottom:14px;left:0;right:0;background:#f5efdf;padding:14px 70px 20px;font-size:21px;color:#635f51}}
    </style><main class="canvas">{picture}<header><div class="kicker safe-text" data-field="样本">{sample} 条回答 · 一个值得想的问题</div>
    <h1 class="safe-text" data-field="标题">{title}</h1></header>
    <div class="footer">{footer}</div></main></html>'''


def editorial_art_prompt(title: str, article: str) -> str:
    return ("为这篇短文创作一张有吸引力的杂志主题插画，只表达一个核心矛盾或具体场景，帮助读者理解文章。"
            "不要图表、数据表、数字、文字、商标或水印，不要把所有观点塞进画面。竖版3:4，"
            "上方30%留浅暖色干净空间供程序排标题，主体位于中下方，底部留一条浅色窄边。"
            "成熟编辑插画，清晰的大形状、纸张肌理，克制而有辨识度。图片仅作概念表达，不伪装成新闻现场照片。"
            f"\n短文标题：{title}\n参考正文：{article}")
