"""DeepSeekReportSpecService — M1.4-C 真实 ReportSpec 生成"""

from __future__ import annotations

from typing import Optional

from backend.app.harness.validators.validation_service import ValidationService
from backend.app.intent.models import IntentSpec, IntentType
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
    LLMValidationError,
)
from backend.app.report.spec_context import ReportSpecContext
from backend.app.report.spec_prompt import build_spec_messages
from backend.app.schemas.data_contracts import (
    QueryPlan,
    QueryResult,
    ReportSpec,
    SemanticModelSchema,
)


class ReportSpecGenerationError(Exception):
    """ReportSpec 生成异常"""
    pass


_MAX_ILLEGAL_FIELDS = 5

_DEFAULT_ALLOWED_TEMPLATES = {"sales_weekly", "satisfaction", "operating_overview"}


class DeepSeekReportSpecService:
    """基于 DeepSeek Provider 的真实 ReportSpec 生成服务"""

    def __init__(self, provider: LLMProvider, max_repairs: int = 1):
        if provider.is_mock:
            raise ReportSpecGenerationError("DeepSeekReportSpecService 要求非 Mock Provider")
        self._provider = provider
        self._max_repairs = max(0, min(max_repairs, 1))

    async def generate(
        self,
        user_input: str,
        intent: IntentSpec,
        query_plan: QueryPlan,
        query_result: QueryResult,
        schema: SemanticModelSchema,
        *,
        template_key: str = "",
        allowed_templates: set[str] | None = None,
        request_id: str = "",
    ) -> ReportSpec:
        # ── 入口边界校验 ──

        if intent.intent != IntentType.REPORT_GENERATION:
            raise ReportSpecGenerationError(
                f"ReportSpec 生成不支持 intent={intent.intent.value}"
            )

        if query_result.error is not None:
            raise ReportSpecGenerationError(
                f"QueryResult 包含错误: {query_result.error.type}"
            )

        if query_plan.semantic_model_key != schema.key:
            raise ReportSpecGenerationError(
                "QueryPlan.semantic_model_key 与 Schema key 不一致"
                "（report_spec_model_key_mismatch）"
            )
        if query_result.semantic_model_key != schema.key:
            raise ReportSpecGenerationError(
                "QueryResult.semantic_model_key 与 Schema key 不一致"
                "（report_spec_result_model_key_mismatch）"
            )

        if query_result.source_mode not in ("mock", "real"):
            raise ReportSpecGenerationError("非法的 source_mode")

        # 模板权限边界
        # None → 使用默认白名单；空集合 → 无权限
        if allowed_templates is None:
            allowed = _DEFAULT_ALLOWED_TEMPLATES
        else:
            allowed = allowed_templates

        # 模板冲突检测：显式 template_key 与 query_plan.requested_template
        # 两者都非空但不一致时，LLM 调用前拒绝
        explicit_template = template_key.strip() if template_key else ""
        requested_template = (query_plan.requested_template or "").strip()
        if explicit_template and requested_template and explicit_template != requested_template:
            raise ReportSpecGenerationError(
                "模板冲突（report_spec_template_conflict）"
            )

        effective_template = explicit_template or requested_template or "sales_weekly"
        if effective_template not in allowed:
            raise ReportSpecGenerationError(
                "模板不在允许白名单中"
                "（report_spec_template_not_allowed）"
            )

        if not user_input or not user_input.strip():
            raise ReportSpecGenerationError("user_input 不能为空")

        # ── 构建安全上下文 ──
        context = ReportSpecContext.build(
            user_input=user_input,
            result_id=query_result.result_id,
            semantic_model_key=schema.key,
            template_key=effective_template,
            allowed_templates=sorted(allowed),
            columns=query_result.columns,
            rows=query_result.rows,
            row_count=query_result.row_count,
            truncated=query_result.truncated,
            source_mode=query_result.source_mode,
            measures=query_plan.measures,
            dimensions=query_plan.dimensions,
            filters_summary=self._build_filters_summary(query_plan),
            time_range=query_plan.time_range or "",
        )

        validation = ValidationService(
            allowed_templates=sorted(allowed),
            allowed_semantic_models=[schema.key],
        )

        repair_used = False

        # ── 首次请求 ──
        try:
            spec = await self._try_generate(context)
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", None) or ""
            if not self._is_format_repairable(error_code):
                raise ReportSpecGenerationError("ReportSpec 生成失败（不可修复错误）") from e
            if self._max_repairs < 1:
                raise ReportSpecGenerationError("ReportSpec 生成失败（修复已禁用）") from e
            repair_used = True
            try:
                spec = await self._try_generate(
                    context, repair_error_code="invalid_content_json_or_schema",
                )
            except LLMValidationError as e:
                raise ReportSpecGenerationError("ReportSpec 生成失败（格式修复后仍无效）") from e
            except LLMProviderError as e:
                raise ReportSpecGenerationError("ReportSpec 生成失败（Provider 错误）") from e
            except Exception as e:
                raise ReportSpecGenerationError("ReportSpec 生成失败（未知错误）") from e
        except LLMProviderError as e:
            raise ReportSpecGenerationError("ReportSpec 生成失败（Provider 错误）") from e
        except Exception as e:
            raise ReportSpecGenerationError("ReportSpec 生成失败") from e

        # ── 严格验证 ──
        val_result = validation.validate_report_strict(
            spec, query_result, input_truncated=context.input_truncated,
        )
        if not val_result.is_valid:
            if repair_used:
                raise ReportSpecGenerationError(
                    f"ReportSpec 验证失败（修复后仍无效）: "
                    f"{'; '.join(val_result.errors[:3])}"
                )
            if self._max_repairs < 1:
                raise ReportSpecGenerationError(
                    f"ReportSpec 验证失败（修复已禁用）: "
                    f"{'; '.join(val_result.errors[:3])}"
                )

            repair_used = True
            illegal_fields = self._extract_illegal_fields(val_result)
            try:
                spec = await self._try_generate(
                    context,
                    repair_error_code="report_spec_validation_failed",
                    illegal_fields=illegal_fields,
                )
            except LLMValidationError as e:
                raise ReportSpecGenerationError("ReportSpec 生成失败（验证修复 JSON 无效）") from e
            except LLMProviderError as e:
                raise ReportSpecGenerationError("ReportSpec 生成失败（Provider 错误）") from e
            except Exception as e:
                raise ReportSpecGenerationError("ReportSpec 生成失败（验证修复未知错误）") from e

            val_result = validation.validate_report_strict(
                spec, query_result, input_truncated=context.input_truncated,
            )
            if not val_result.is_valid:
                raise ReportSpecGenerationError(
                    f"ReportSpec 验证失败（验证修复后仍无效）: "
                    f"{'; '.join(val_result.errors[:3])}"
                )

        return spec

    async def _try_generate(
        self, context: ReportSpecContext,
        repair_error_code: str | None = None,
        illegal_fields: str = "",
    ) -> ReportSpec:
        messages = build_spec_messages(
            context, repair_error_code=repair_error_code, illegal_fields=illegal_fields,
        )
        request = LLMRequest(messages=messages, task=LLMTask.REPORT)
        response = await self._provider.generate(request, ReportSpec)
        if response.structured is None:
            raise ReportSpecGenerationError("Provider 返回的 structured 为 None")
        return response.structured

    @staticmethod
    def _is_format_repairable(error_code: str) -> bool:
        return error_code in {"invalid_content_json", "output_schema_invalid"}

    @staticmethod
    def _build_filters_summary(query_plan: QueryPlan) -> str:
        if not query_plan.filters:
            return ""
        return "; ".join(f"{f.field} {f.operator.value} {f.value}" for f in query_plan.filters)

    @staticmethod
    def _extract_illegal_fields(val_result) -> str:
        import re
        field_set: set[str] = set()
        for err in val_result.errors:
            m = re.search(r"'([^']+)'", err)
            if m:
                field_set.add(m.group(1))
        fields = sorted(field_set)[:_MAX_ILLEGAL_FIELDS]
        return ", ".join(fields) if fields else "（未知字段）"

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def max_repairs(self) -> int:
        return self._max_repairs
