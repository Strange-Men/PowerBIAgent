"""One factual analysis, two presentations; snapshots preserve numeric types."""
from datetime import date
from decimal import Decimal
import json

import pytest

from backend.app.facts import VerifiedFactSetBuilder, FactOutputValidator
from backend.app.schemas.data_contracts import CanonicalQueryPlan, QueryResult


def test_exact_supported_locale_fails_safe():
    from backend.app.presentation.locale import SupportedLocale, normalize_locale
    assert {item.value for item in SupportedLocale} == {'zh-CN', 'en-US'}
    for invalid in ['en', 'en-GB', 'zh', 'EN-us', '', None, 'qps-ploc']:
        assert normalize_locale(invalid) == SupportedLocale.ZH_CN
    assert normalize_locale('en-US') == SupportedLocale.EN_US


@pytest.mark.asyncio
async def test_decimal_recipe_roundtrip_and_two_projections_do_not_change_facts():
    from backend.app.presentation.recipe import PresentationRecipe, project_recipe
    from backend.app.persistence.serialization import domain_to_json, json_to_domain
    plan = CanonicalQueryPlan(normalized_question='sales', semantic_model_key='model', measures=['Total Sales'])
    result = QueryResult(result_id='r1', semantic_model_key='model', columns=['[Total Sales]'],
                         rows=[[Decimal('1234567.8912')]], row_count=1, source_mode='real')
    facts = VerifiedFactSetBuilder().build(plan, result)
    recipe = PresentationRecipe(plan=plan, result=result, facts=facts)
    before = recipe.factual_hash
    restored = json_to_domain(PresentationRecipe, domain_to_json(recipe))
    assert restored.result.rows == result.rows
    assert type(restored.result.rows[0][0]) is Decimal
    assert restored.factual_hash == before
    zh = await project_recipe(restored, 'zh-CN')
    en = await project_recipe(restored, 'en-US')
    assert zh.answer != en.answer
    assert '1,234,567.89' in zh.answer and '1,234,567.89' in en.answer
    assert zh.factual_hash == en.factual_hash == before
    assert recipe.facts == facts and recipe.plan == plan and recipe.result == result
    assert zh.presentation.datasets[0].rows == en.presentation.datasets[0].rows
    assert FactOutputValidator().validate_answer(en.answer_spec, facts, locale='en-US') == []


def test_formatter_preserves_value_and_unsupported_locale():
    from backend.app.presentation.formatter import PresentationFormatter, PresentationFormatKind as K
    value = Decimal('1234.5678')
    for locale in ['zh-CN', 'en-US', 'unsupported']:
        assert PresentationFormatter(locale=locale).format(value, K.AMOUNT) == '1,234.57'
        assert value == Decimal('1234.5678')
    assert PresentationFormatter(locale='en-US').format(date(2026, 10, 20), K.DATE) == 'Oct 20, 2026'


def test_english_unproved_claims_are_rejected():
    from backend.app.schemas.data_contracts import AnswerSpec
    plan = CanonicalQueryPlan(normalized_question='sales', semantic_model_key='model', measures=['Total Sales'])
    result = QueryResult(result_id='r1', semantic_model_key='model', columns=['[Total Sales]'], rows=[[100]], row_count=1)
    facts = VerifiedFactSetBuilder().build(plan, result)
    for text in ['Sales increased because of advertising.', 'Sales are up year over year.', 'Data refreshed through October.', 'Sales reached the highest value.']:
        answer = AnswerSpec(answer=text, summary=text, verified_fact_set_id=facts.fact_set_id,
                            fact_ids=[item.fact_id for item in facts.facts])
        assert FactOutputValidator().validate_answer(answer, facts, locale='en-US')


def test_english_comparison_acronyms_do_not_match_inside_measure_names():
    from backend.app.facts import FactBoundedAnswerBuilder
    plan=CanonicalQueryPlan(normalized_question='value',semantic_model_key='model',measures=['Momentum'])
    result=QueryResult(result_id='momentum',semantic_model_key='model',columns=['[Momentum]'],rows=[[100]],row_count=1)
    facts=VerifiedFactSetBuilder().build(plan,result)
    answer=FactBoundedAnswerBuilder().build(plan,result,facts,locale='en-US')
    assert FactOutputValidator().validate_answer(answer,facts,locale='en-US')==[]
    for acronym in ['MoM','YoY']:
        claim=answer.model_copy(update={'answer':f'{acronym} increased by 100.','summary':f'{acronym} increased by 100.'})
        assert 'unverified_comparison_claim' in FactOutputValidator().validate_answer(claim,facts,locale='en-US')


@pytest.mark.parametrize('locale',['zh-CN','en-US'])
def test_filter_display_evidence_is_bounded_to_final_plan_members(locale):
    from backend.app.facts import FactBoundedAnswerBuilder
    from backend.app.schemas.data_contracts import StructuredFilter,FilterOperator
    plan=CanonicalQueryPlan(normalized_question='grouped',semantic_model_key='model',
        measures=['Total Sales'],dimensions=['Country'],
        filters=[StructuredFilter(field='Country',operator=FilterOperator.IN_SET,value=['France','Germany'])])
    result=QueryResult(result_id='grouped',semantic_model_key='model',columns=['Country','[Total Sales]'],
        rows=[['France',Decimal('100.25')],['Germany',Decimal('200.50')]],row_count=2)
    facts=VerifiedFactSetBuilder().build(plan,result)
    before=(plan.model_dump_json(),result.model_dump_json(),facts.model_dump_json())
    answer=FactBoundedAnswerBuilder().build(plan,result,facts,locale=locale,
        user_facing_filter_values={('Country','France'):'France',('Country','Germany'):'Germany',
            ('Country',str(['France','Germany'])):'countries',('Country','Atlantis'):'stale'})
    assert FactOutputValidator().validate_answer(answer,facts,locale=locale)==[]
    assert {item['canonical_value'] for item in answer.evidence['user_facing_filter_values']}=={'France','Germany'}
    assert before==(plan.model_dump_json(),result.model_dump_json(),facts.model_dump_json())
    poisoned=answer.model_copy(update={'evidence':{**answer.evidence,'user_facing_filter_values':[
        *answer.evidence['user_facing_filter_values'],
        {'field':'Country','canonical_value':'Atlantis','display_value':'stale'}]}})
    assert 'user_facing_filter_values_invalid' in FactOutputValidator().validate_answer(poisoned,facts,locale=locale)


@pytest.mark.asyncio
async def test_same_report_spec_two_renderings_preserve_values_points_and_order():
    from backend.tests.unit.test_executive_report_renderer import _report
    from backend.app.report.executive import ExecutiveSalesReportRenderer
    from backend.app.presentation.locale import presentation_locale
    from html.parser import HTMLParser
    class Text(HTMLParser):
        def __init__(self): super().__init__(); self.text=[]; self.style=False
        def handle_starttag(self,tag,attrs): self.style=tag=='style' or self.style
        def handle_endtag(self,tag):
            if tag=='style': self.style=False
        def handle_data(self,data):
            if not self.style: self.text.append(data)
    report=_report()
    before=report.model_dump(mode='json')
    rendered=[]
    for locale in ['zh-CN','en-US']:
        with presentation_locale(locale):
            rendered.append(await ExecutiveSalesReportRenderer().render(report))
    assert report.model_dump(mode='json')==before
    assert rendered[0]!=rendered[1]
    for html in rendered:
        assert 'data-template-key="sales_executive_report"' in html
        for kpi in report.kpis:
            assert format(kpi.value,',.2f') in html or format(kpi.value,',.0f') in html
    zh,en=rendered
    assert 'lang="zh-CN"' in zh and 'lang="en-US"' in en
    text=Text();text.feed(en)
    import re
    visible=''.join(text.text)
    for chart in report.charts:
        for point in chart.series:
            label=str(point['label'])
            if re.search(r'[\u4e00-\u9fff]',label):
                assert label in zh and label in en
                visible=visible.replace(label,'')
    for table in report.tables:
        for row in table.rows:
            for cell in row:
                if isinstance(cell,str) and re.search(r'[\u4e00-\u9fff]',cell):
                    assert cell in zh and cell in en
                    visible=visible.replace(cell,'')
    assert not re.search(r'[\u4e00-\u9fff]',visible)
    assert re.findall(r'<(?:polyline|polygon)[^>]*points="([^"]+)"',zh)==re.findall(r'<(?:polyline|polygon)[^>]*points="([^"]+)"',en)
    assert re.findall(r'data-kpi="([^"]+)"',zh)==re.findall(r'data-kpi="([^"]+)"',en)


def test_fixed_report_axis_layout_uses_source_year_boundaries_in_both_languages():
    from backend.tests.unit.test_report_generation import _trend_chart
    from backend.app.report.fixed import SalesReportRenderer
    from backend.app.presentation.locale import presentation_locale
    import re
    rendered=[]
    for locale in ['zh-CN','en-US']:
        with presentation_locale(locale):rendered.append(SalesReportRenderer._line_chart(_trend_chart(24,cross_year=True)))
    attributes=lambda html:re.findall(r'<text x="[^"]+" y="[^"]+" data-tick-index="[^"]+" data-tick-tier="[^"]+" data-tick-lane="[^"]+"',html)
    assert attributes(rendered[0]) and attributes(rendered[0])==attributes(rendered[1])
    for html in rendered:
        assert '销售额（元）' not in html and 'USD' not in html and 'CNY' not in html
