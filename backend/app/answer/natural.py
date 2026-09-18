"""LLM wording over a closed, validator-enforced verified fact envelope."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from backend.app.facts.availability import DataAvailabilityContext
from backend.app.facts.verified import FactOutputValidator, FactType, VerifiedFactSet
from backend.app.llm.base import LLMProvider, LLMRequest, LLMTask
from backend.app.schemas.data_contracts import AnswerSpec


class NaturalAnswerDraft(BaseModel):
    answer: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid", frozen=True)


class NaturalAnswerComposer:
    """Compose fluent text while preserving deterministic evidence/provenance."""

    _SYSTEM = """你只负责把已验证事实改写成自然、简洁的用户回答。
不得增加、删除或修改任何数字、成员、排名顺序、时间、筛选、比较、趋势、原因、
数据可用期间或刷新状态。不要输出模型 key、canonical 字段、fact/result ID、DAX、
technical scope 标签。available_data_horizon 只表示模型中可观测到的事实期间，绝不能写成
“数据更新到”。若 safe_fallback 已说明 horizon/无数据，必须保留该含义。
只输出 JSON：{\"answer\":\"...\"}。"""

    def __init__(self, provider: LLMProvider, *, max_repairs: int = 1) -> None:
        self._provider = provider
        self._max_repairs = max(0, min(max_repairs, 1))

    async def compose(
        self,
        fallback: AnswerSpec,
        facts: VerifiedFactSet,
        *,
        data_availability: DataAvailabilityContext | None,
    ) -> AnswerSpec:
        payload = self._payload(fallback, facts, data_availability)
        candidate = await self._generate(payload)
        answer = fallback.model_copy(
            update={"answer": candidate.answer, "summary": candidate.answer}
        )
        errors = self._validate(answer, fallback, facts, data_availability)
        if errors and self._max_repairs:
            candidate = await self._generate(payload, errors=errors)
            answer = fallback.model_copy(
                update={"answer": candidate.answer, "summary": candidate.answer}
            )
            errors = self._validate(answer, fallback, facts, data_availability)
        return fallback if errors else answer

    async def _generate(
        self,
        payload: dict[str, object],
        *,
        errors: list[str] | None = None,
    ) -> NaturalAnswerDraft:
        system = self._SYSTEM
        if errors:
            system += "\n上一次输出被事实验证拒绝：" + ",".join(errors)
        response = await self._provider.generate(
            LLMRequest(
                task=LLMTask.ANSWER,
                scenario_key="natural_answer",
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, default=str),
                    },
                ],
            ),
            NaturalAnswerDraft,
        )
        if not isinstance(response.structured, NaturalAnswerDraft):
            raise TypeError("natural_answer_response_missing")
        return response.structured

    @staticmethod
    def _payload(
        fallback: AnswerSpec,
        facts: VerifiedFactSet,
        availability: DataAvailabilityContext | None,
    ) -> dict[str, object]:
        visible = []
        for fact in facts.facts:
            if fact.fact_type in {
                FactType.RESULT_METADATA,
                FactType.OBSERVED_DATA_COVERAGE,
            }:
                continue
            visible.append({
                "type": fact.fact_type.value,
                "value": fact.value,
                "values": fact.values,
                "measure": fact.measure,
                "dimensions": fact.dimensions,
                "time_range": (
                    fact.time_range.model_dump(mode="json")
                    if fact.time_range is not None
                    else None
                ),
            })
        return {
            "safe_fallback": fallback.answer,
            "verified_facts": visible,
            "user_facing_scope": fallback.evidence.get("user_facing_scope", ""),
            "observed_data_coverage": facts.observed_data_coverage.model_dump(
                mode="json"
            ),
            "available_data_horizon": (
                availability.available_data_horizon.model_dump(mode="json")
                if availability is not None
                and availability.available_data_horizon is not None
                else None
            ),
        }

    @staticmethod
    def _validate(
        answer: AnswerSpec,
        fallback: AnswerSpec,
        facts: VerifiedFactSet,
        availability: DataAvailabilityContext | None,
    ) -> list[str]:
        errors = FactOutputValidator().validate_answer(answer, facts)
        for token in FactOutputValidator._NUMBER.findall(fallback.answer):
            normalized = FactOutputValidator._normalize_number(token)
            candidate_numbers = {
                FactOutputValidator._normalize_number(item)
                for item in FactOutputValidator._NUMBER.findall(answer.answer)
            }
            if normalized not in candidate_numbers:
                errors.append("verified_numeric_claim_omitted")
                break
        for ranking in facts.by_type(FactType.RANKING):
            for item in ranking.values:
                for value in item.get("dimensions", {}).values():
                    if str(value) not in answer.answer:
                        errors.append("verified_ranking_item_omitted")
                        break
        scope = fallback.evidence.get("user_facing_scope", "")
        if isinstance(scope, str):
            for item in (part.strip() for part in scope.split("，")):
                if item and item not in answer.answer:
                    errors.append("verified_scope_item_omitted")
                    break
        measure = fallback.evidence.get("user_facing_measure")
        if isinstance(measure, str) and measure and measure not in answer.answer:
            errors.append("verified_measure_label_omitted")
        forbidden = {
            facts.semantic_model_key,
            facts.fact_set_id,
            facts.result_id,
            *(fact.fact_id for fact in facts.facts),
        }
        if any(token and token in answer.answer for token in forbidden):
            errors.append("technical_identity_exposed")
        if any(
            f"{item.field}=" in answer.answer
            for item in fallback.filters
        ):
            errors.append("technical_filter_syntax_exposed")
        fallback_requires_horizon = "可观测到" in fallback.answer
        if fallback_requires_horizon and "可观测到" not in answer.answer:
            errors.append("available_data_horizon_omitted")
        return list(dict.fromkeys(errors))
