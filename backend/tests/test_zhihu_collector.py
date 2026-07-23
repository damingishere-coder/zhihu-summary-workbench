from backend.app.collectors.zhihu import basic_filter_reason, clean_answer_html


def test_clean_answer_html_preserves_text_links_and_media() -> None:
    plain, markdown, media = clean_answer_html(
        """
        <p>这是一个包含<a href="https://example.com">来源</a>的回答段落。</p>
        <ul><li>第一条建议需要结合具体条件执行。</li></ul>
        <img src="https://pic.example/a.png" alt="示意图">
        <span class="ztext-math" data-tex="x^2+y^2"></span>
        """
    )
    assert "这是一个包含来源的回答段落" in plain
    assert "[来源](https://example.com)" in markdown
    assert media["images"] == ["https://pic.example/a.png"]
    assert media["formulas"] == ["x^2+y^2"]


def test_basic_filter_marks_short_and_ads_without_deleting_content() -> None:
    assert basic_filter_reason("哈哈") == "内容过短"
    assert (
        basic_filter_reason(
            "这是一段看似正常但实际用于推广的长内容，加微信获得资料，"
            "扫码咨询可以领取课程，点击购买还有额外优惠。"
        )
        == "疑似广告"
    )
    assert (
        basic_filter_reason(
            "先从每天十分钟开始，根据实际体能逐渐增加强度，并记录完成情况形成反馈；"
            "如果某天中断，第二天恢复计划即可，不需要因为一次失败彻底放弃。"
        )
        == ""
    )
