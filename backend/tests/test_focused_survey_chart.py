from backend.app.services.focused_survey_chart import focused_rows, focused_survey_chart_html


def test_chart_uses_five_largest_endorsements_and_full_sample_denominator():
    rows = [dict(cluster_id=str(i), name=f'观点{i}', counts=dict(supports=i, conditional=1),
                 endorsement_count=999) for i in range(7)]
    survey = dict(rows=rows, denominator=20, collected_answers=22, analyzed_answers=21)
    assert [r['cluster_id'] for r in focused_rows(survey)] == ['6', '5', '4', '3', '2']
    result = focused_survey_chart_html(dict(title='<测试>', opinion_survey=survey), 1080, 1440)
    assert result.count('class="chart-row"') == 5
    assert 'data-count="7"' in result and '35.0%' in result and '999' not in result
    assert '观点0' not in result and '共 7 项' in result
    assert '&lt;测试&gt;' in result and '占比不必合计 100%' in result
    assert '<img' not in result and '<table' not in result


def test_chart_with_no_identifiable_authors_does_not_invent_percentages():
    survey = dict(rows=[dict(cluster_id='a', name='观点', counts=dict(supports=0, conditional=0))],
                  denominator=0, collected_answers=2, analyzed_answers=2)
    result = focused_survey_chart_html(dict(opinion_survey=survey), 1080, 1440)
    assert '占比不适用' in result and '0.0%' not in result
