"""Declarative M5.10.6 Real Language Stress corpus.

The cases contain language and deterministic runtime expectations only.  They
are never imported by production code and never provide semantic aliases.
"""

from __future__ import annotations


CASES = [
    # General (8)
    {"id": "general_hello", "category": "general", "text": "你好", "outcome": "general"},
    {"id": "general_chat", "category": "general", "text": "我们随便聊聊天吧", "outcome": "general"},
    {"id": "general_tired", "category": "general", "text": "我今天有点累，陪我说两句", "outcome": "general"},
    {"id": "general_mean", "category": "general", "text": "能通俗解释一下为什么平均数会受极端值影响吗？", "outcome": "general"},
    {"id": "general_newton", "category": "general", "text": "牛顿是谁？请用一句话说明", "outcome": "general"},
    {"id": "general_greeting", "category": "general", "text": "帮我写一句自然、不夸张的问候", "outcome": "general"},
    {"id": "general_polish", "category": "general", "text": "把“会议明天开”润色得礼貌一点", "outcome": "general"},
    {"id": "general_report_help", "category": "general", "text": "你通常能怎么帮助我理解一张报表？", "outcome": "general"},

    # General external-current facts (8; first six high risk)
    {"id": "external_gangxia_meal", "category": "external", "text": "我公司在深圳岗厦北，有什么工作餐推荐？", "outcome": "external", "high_risk": True},
    {"id": "external_nearby_mcd", "category": "external", "text": "附近有哪些麦当劳现在还营业？", "outcome": "external", "high_risk": True},
    {"id": "external_weather", "category": "external", "text": "今天深圳天气怎么样？", "outcome": "external", "high_risk": True},
    {"id": "external_apple_price", "category": "external", "text": "苹果现在股价多少？", "outcome": "external", "high_risk": True},
    {"id": "external_news", "category": "external", "text": "今天有什么大新闻？", "outcome": "external", "high_risk": True},
    {"id": "external_open_cafe", "category": "external", "text": "岗厦北附近现在营业的咖啡店有哪些？", "outcome": "external", "high_risk": True},
    {"id": "external_fuel", "category": "external", "text": "深圳今天的汽油价格是多少？", "outcome": "external"},
    {"id": "external_btc", "category": "external", "text": "Could you tell me the current Bitcoin price?", "outcome": "external"},

    # Scalar (8)
    {"id": "scalar_sales_cn", "category": "scalar", "text": "总销售额是多少？", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"]},
    {"id": "scalar_sales_2026", "category": "scalar", "text": "2026年销售额情况", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "time": True},
    {"id": "scalar_sales_this_year", "category": "scalar", "text": "今年销售额给我一个数", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "time": True},
    {"id": "scalar_sales_en", "category": "scalar", "text": "What is our total sales?", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"]},
    {"id": "scalar_amount_en", "category": "scalar", "text": "Please show the sales amount, just the total.", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"]},
    {"id": "scalar_canonical_literal", "category": "scalar", "text": "Total Sales是多少？", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"]},
    {"id": "scalar_sales_amount_cn", "category": "scalar", "text": "麻烦查一下整体销售金额", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"]},
    {"id": "scalar_orders", "category": "scalar", "text": "Could you briefly give me the total order count?", "outcome": "completed", "shape": "scalar", "measures": ["Total Orders"]},

    # Member/filter (10; first eight high risk)
    {"id": "member_south_literal", "category": "member", "text": "2025年5月South销售额是多少", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "South"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_south_lower", "category": "member", "text": "show me south sales amount for May 2025", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "South"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_south_cn", "category": "member", "text": "帮我看看2025年五月南方的销售额", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "South"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_south_wrapper", "category": "member", "text": "Could you briefly show 2025年5月华南销售额?", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "South"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_north_literal", "category": "member", "text": "2025年5月North销售额是多少", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "North"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_north_lower", "category": "member", "text": "north sales amount in May 2025, please", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "North"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_north_cn", "category": "member", "text": "2025年五月北方的销售金额有多少？", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "North"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_north_wrapper", "category": "member", "text": "Could you show 2025年5月华北销售额，简短一点", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "North"}], "time": True, "time_range": {"start_date": "2025-05-01", "end_date": "2025-05-31"}, "high_risk": True},
    {"id": "member_set_regions", "category": "member", "text": "华南和华北的销售额分别是多少？", "outcome": "completed", "shape": "member_set", "measures": ["Total Sales"], "dimensions": ["Region"], "filters": [{"field": "Region", "operator": "in", "value": ["South", "North"]}]},
    {"id": "member_filtered_total", "category": "member", "text": "把华南和华北合在一起算销售额", "outcome": "completed", "shape": "filtered_aggregation", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "in", "value": ["South", "North"]}]},

    # Grouped (6)
    {"id": "grouped_product_cn", "category": "grouped", "text": "每个产品的销售额分别是多少？", "outcome": "completed", "shape": "grouped", "measures": ["Total Sales"], "dimensions": ["Product"]},
    {"id": "grouped_product_en", "category": "grouped", "text": "Break down total sales by product.", "outcome": "completed", "shape": "grouped", "measures": ["Total Sales"], "dimensions": ["Product"]},
    {"id": "grouped_region_cn", "category": "grouped", "text": "各地区销售金额给我对比一下", "outcome": "completed", "shape": "grouped", "measures": ["Total Sales"], "dimensions": ["Region"]},
    {"id": "grouped_region_en", "category": "grouped", "text": "sales amount for each region", "outcome": "completed", "shape": "grouped", "measures": ["Total Sales"], "dimensions": ["Region"]},
    {"id": "grouped_category_mixed", "category": "grouped", "text": "请按 Category 展示 sales amount", "outcome": "completed", "shape": "grouped", "measures": ["Total Sales"], "dimensions": ["Category"]},
    {"id": "grouped_orders_product", "category": "grouped", "text": "产品维度分别有多少订单？", "outcome": "completed", "shape": "grouped", "measures": ["Total Orders"], "dimensions": ["Product"]},

    # Ranking (8; first three high risk)
    {"id": "ranking_top3_cn", "category": "ranking", "text": "销售额最高的三个产品", "outcome": "completed", "shape": "ranking", "measures": ["Total Sales"], "dimensions": ["Product"], "top_n": 3, "sort": "desc", "high_risk": True},
    {"id": "ranking_top3_en", "category": "ranking", "text": "top 3 products by sales amount", "outcome": "completed", "shape": "ranking", "measures": ["Total Sales"], "dimensions": ["Product"], "top_n": 3, "sort": "desc", "high_risk": True},
    {"id": "ranking_top3_mixed", "category": "ranking", "text": "麻烦 show the three products with the highest 销售额", "outcome": "completed", "shape": "ranking", "measures": ["Total Sales"], "dimensions": ["Product"], "top_n": 3, "sort": "desc", "high_risk": True},
    {"id": "ranking_three_word_order", "category": "ranking", "text": "产品里按销售金额排在前三的是哪些？", "outcome": "completed", "shape": "ranking", "measures": ["Total Sales"], "dimensions": ["Product"], "top_n": 3, "sort": "desc"},
    {"id": "ranking_quantity_top3", "category": "ranking", "text": "销量最大的三款产品给我列出来", "outcome": "completed", "shape": "ranking", "measures": ["Total Quantity"], "dimensions": ["Product"], "top_n": 3, "sort": "desc"},
    {"id": "ranking_orders_low2", "category": "ranking", "text": "订单数最低的两个产品", "outcome": "completed", "shape": "ranking", "measures": ["Total Orders"], "dimensions": ["Product"], "top_n": 2, "sort": "asc"},
    {"id": "ranking_top1", "category": "ranking", "text": "哪个产品的销售额最高？", "outcome": "completed", "shape": "ranking", "measures": ["Total Sales"], "dimensions": ["Product"], "top_n": 1, "sort": "desc"},
    {"id": "ranking_no_number", "category": "ranking", "text": "哪些产品销售额最高？", "outcome": "blocked"},

    # Trend/time (8; first three high risk)
    {"id": "trend_recent6_cn", "category": "trend", "text": "最近6个月销售额趋势", "outcome": "completed", "shape": "trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True, "high_risk": True},
    {"id": "trend_recent6_en", "category": "trend", "text": "sales trend for the last 6 months", "outcome": "completed", "shape": "trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True, "high_risk": True},
    {"id": "trend_h2_cn", "category": "trend", "text": "给我2025年后6个月的销售额走势", "outcome": "completed", "shape": "bounded_trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True, "time_range": {"start_date": "2025-07-01", "end_date": "2025-12-31"}, "high_risk": True},
    {"id": "trend_h2_range", "category": "trend", "text": "2025年7月至12月销售额走势", "outcome": "completed", "shape": "bounded_trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True, "time_range": {"start_date": "2025-07-01", "end_date": "2025-12-31"}},
    {"id": "trend_h2_en", "category": "trend", "text": "2025 H2 sales trend by month", "outcome": "completed", "shape": "bounded_trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True, "time_range": {"start_date": "2025-07-01", "end_date": "2025-12-31"}},
    {"id": "trend_vague", "category": "trend", "text": "最近几个月销售趋势", "outcome": "blocked"},
    {"id": "trend_future_empty", "category": "trend", "text": "2026年4月至9月销售额趋势", "outcome": "completed", "shape": "bounded_trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True},
    {"id": "trend_quantity_2025", "category": "trend", "text": "Plot monthly sales quantity throughout 2025.", "outcome": "completed", "shape": "bounded_trend", "measures": ["Total Quantity"], "dimensions": ["YearMonth"], "time": True, "time_range": {"start_date": "2025-01-01", "end_date": "2025-12-31"}},

    # Ambiguous/unknown (6; first four high risk)
    {"id": "unknown_ambiguous_sales", "category": "unknown", "text": "2026年销售情况", "outcome": "blocked", "high_risk": True},
    {"id": "unknown_mars", "category": "unknown", "text": "火星区销售额是多少？", "outcome": "blocked", "high_risk": True},
    {"id": "unknown_moon", "category": "unknown", "text": "月球区的订单数给我看看", "outcome": "blocked", "high_risk": True},
    {"id": "unknown_atlantis", "category": "unknown", "text": "Atlantis sales amount", "outcome": "blocked", "high_risk": True},
    {"id": "unknown_shenzhen", "category": "unknown", "text": "深圳销售额是多少？", "outcome": "blocked"},
    {"id": "unknown_beijing", "category": "unknown", "text": "北京订单数是多少？", "outcome": "blocked"},

    # Follow-up/state (6). Setups are support turns, not corpus scenarios.
    {"id": "state_rank_quantity", "category": "state", "text": "改成销售数量", "outcome": "completed", "shape": "ranking", "measures": ["Total Quantity"], "dimensions": ["Product"], "top_n": 3, "sort": "desc", "setup": [{"text": "销售额最高的三个产品", "outcome": "completed", "shape": "ranking"}]},
    {"id": "state_rank_back_sales", "category": "state", "text": "按销售额", "outcome": "completed", "shape": "ranking", "measures": ["Total Sales"], "dimensions": ["Product"], "top_n": 3, "sort": "desc", "setup": [{"text": "销售额最高的三个产品", "outcome": "completed", "shape": "ranking"}, {"text": "改成销售数量", "outcome": "completed", "shape": "ranking"}, {"text": "讲个笑话", "outcome": "general"}]},
    {"id": "state_region_north", "category": "state", "text": "改成华北", "outcome": "completed", "shape": "scalar", "measures": ["Total Sales"], "filters": [{"field": "Region", "operator": "eq", "value": "North"}], "setup": [{"text": "华南销售额", "outcome": "completed", "shape": "scalar"}]},
    {"id": "state_region_quantity", "category": "state", "text": "换成销售数量", "outcome": "completed", "shape": "scalar", "measures": ["Total Quantity"], "filters": [{"field": "Region", "operator": "eq", "value": "North"}], "setup": [{"text": "华南销售额", "outcome": "completed", "shape": "scalar"}, {"text": "改成华北", "outcome": "completed", "shape": "scalar"}]},
    {"id": "state_complete_vague_time", "category": "state", "text": "最近6个月", "outcome": "completed", "shape": "trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True, "setup": [{"text": "最近几个月销售额趋势", "outcome": "blocked"}]},
    {"id": "state_fresh_after_general", "category": "state", "text": "新问题：总订单数是多少？", "outcome": "completed", "shape": "scalar", "measures": ["Total Orders"], "filters": [], "setup": [{"text": "华南销售额", "outcome": "completed", "shape": "scalar"}, {"text": "我今天有点累，聊两句", "outcome": "general"}]},

    # Explain-change/report (4)
    {"id": "explain_decline_cn", "category": "explain_report", "text": "为什么今年销售额下降？", "outcome": "explain", "shape": "trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True},
    {"id": "explain_worse_cn", "category": "explain_report", "text": "帮我分析今年销售额为什么变差", "outcome": "explain", "shape": "trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True},
    {"id": "explain_decline_en", "category": "explain_report", "text": "what caused this year's sales decline?", "outcome": "explain", "shape": "trend", "measures": ["Total Sales"], "dimensions": ["YearMonth"], "time": True},
    {"id": "report_2025", "category": "explain_report", "text": "请生成2025年销售经营分析报表", "outcome": "report", "template": "sales_executive_report"},
]


CATEGORY_COUNTS = {
    "general": 8,
    "external": 8,
    "scalar": 8,
    "member": 10,
    "grouped": 6,
    "ranking": 8,
    "trend": 8,
    "unknown": 6,
    "state": 6,
    "explain_report": 4,
}


# New-disposition focused probes are deliberately outside the frozen 72-case
# corpus. They can be selected explicitly without changing final-stress counts.
FOCUSED_EXPLAIN_CASES = (
    {
        "id": "explain_decline_inverted_cn",
        "category": "explain_report",
        "text": "今年销售额为什么下降？",
        "outcome": "explain",
        "shape": "trend",
        "measures": ["Total Sales"],
        "dimensions": ["YearMonth"],
        "time": True,
    },
)


def validate_corpus() -> None:
    ids = [item["id"] for item in CASES]
    assert len(CASES) == 72
    assert len(ids) == len(set(ids))
    assert sum(bool(item.get("high_risk")) for item in CASES) == 24
    observed = {
        category: sum(item["category"] == category for item in CASES)
        for category in CATEGORY_COUNTS
    }
    assert observed == CATEGORY_COUNTS
    assert not set(ids).intersection(item["id"] for item in FOCUSED_EXPLAIN_CASES)


validate_corpus()
