"""Report-intent weak-signal prompt — registry-owned analysis goals only.

The LLM draft must never contain DAX, HTML, CSS, numbers, free field names,
visual types or queries.  Only the fixed section registry below is usable.
"""

from __future__ import annotations

REGISTRY_DESCRIPTIONS = (
    "sales_kpi — 总销售额",
    "quantity_kpi — 总销量",
    "orders_kpi — 总订单数",
    "aov_kpi — 平均订单金额",
    "time_trend — 销售趋势（随时间变化）",
    "category_contribution — 品类销售构成",
    "region_comparison — 区域销售对比",
    "top_products — 头部产品",
    "top_customers — 头部客户",
)

SYSTEM_PROMPT = """你是 Power BI 销售分析报表的「分析目标识别器」，只回答一个问题：用户想看哪些分析目标？

## 允许的分析目标 ID（只能从这里选择）
%s

## 硬性规则
1. 只能输出合法 JSON 对象：{"report_section_ids": ["<id>", ...]}
2. 只能输出用户语言中明确提到的分析目标；用户没提到的目标一律不得输出
3. 禁止输出：DAX、SQL、HTML、CSS、JavaScript、数字、字段名、图表类型、查询描述、解释文本
4. 禁止输出不在允许列表中的任何 ID
5. 用户没有明确提到任何分析目标时，输出空列表 {"report_section_ids": []}
6. 不得添加 Markdown 代码块，不得添加注释
""" % "\n".join(f"- {item}" for item in REGISTRY_DESCRIPTIONS)


def build_report_intent_messages(
    user_input: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户输入：{user_input}\n"
                "请输出用户明确提到的分析目标 ID。"
            ),
        },
    ]
