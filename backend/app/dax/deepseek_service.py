"""DeepSeekDAXService — M1.3 真实 DAX 生成

基于 DeepSeekLLMProvider 从已验证的 QueryPlan 生成只读 DAX 查询。
- 复用现有 DAXRequest 模型
- 独立 DAX 只读安全验证
- 最多一次格式修复
- Service 不保存请求级可变状态，支持并发
"""

from __future__ import annotations

from typing import Optional

from backend.app.dax.prompt import build_dax_messages
from backend.app.dax.safety import DAXSafetyResult, DAXSafetyValidator
from backend.app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMTask,
    LLMValidationError,
)
from backend.app.query_plan.context import build_schema_view, render_schema_text
from backend.app.schemas.data_contracts import DAXRequest, QueryPlan, SemanticModelSchema


class DAXGenerationError(Exception):
    """DAX 生成异常"""
    pass


class DeepSeekDAXService:
    """基于 DeepSeek Provider 的真实 DAX 生成服务

    构造函数：
        provider: 非 Mock LLMProvider
        max_dax_repairs: 最大修复次数（固定 1 次）
    """

    def __init__(
        self,
        provider: LLMProvider,
        max_dax_repairs: int = 1,
    ):
        if provider.is_mock:
            raise DAXGenerationError(
                "DeepSeekDAXService 要求非 Mock Provider"
            )

        self._provider = provider
        self._max_repairs = max(0, min(max_dax_repairs, 1))
        self._safety_validator = DAXSafetyValidator()

    # ── 公共 API ──

    async def generate(
        self,
        query_plan: QueryPlan,
        schema: SemanticModelSchema,
        *,
        semantic_model_key: Optional[str] = None,
        request_id: str = "",
    ) -> DAXRequest:
        """从 QueryPlan 和 Schema 生成 DAX 查询

        Args:
            query_plan: 已验证的 QueryPlan
            schema: SemanticModelSchema
            semantic_model_key: 语义模型 Key
            request_id: 请求 ID

        Returns:
            DAXRequest: 包含经验证的只读 DAX 查询

        Raises:
            DAXGenerationError: 生成失败
        """
        effective_model_key = semantic_model_key or schema.key

        # 1. 构建 Schema 视图
        schema_view = build_schema_view(schema)
        schema_text = render_schema_text(schema_view)

        # 2. 构建 QueryPlan 文本摘要
        qp_summary = self._format_query_plan_summary(query_plan)

        # 3. 首次请求
        try:
            dax_request = await self._try_generate(
                qp_summary, schema_text, effective_model_key, request_id,
            )
            # 安全验证
            safety = self._safety_validator.validate(dax_request.dax, schema)
            if not safety.is_valid:
                # 安全验证失败 → 尝试修复
                if self._max_repairs < 1:
                    raise DAXGenerationError(
                        f"DAX 安全验证失败（修复已禁用）: {'; '.join(safety.errors)}"
                    )
                # 进入修复流程
                dax_request = await self._try_repair(
                    qp_summary, schema_text, effective_model_key, request_id,
                    error_code="dax_safety_failed",
                    illegal_objects=", ".join(safety.errors[:5]),
                )
                safety = self._safety_validator.validate(dax_request.dax, schema)
                if not safety.is_valid:
                    raise DAXGenerationError(
                        f"DAX 安全验证失败（修复后仍无效）: {'; '.join(safety.errors)}"
                    )
            return dax_request
        except DAXGenerationError:
            raise
        except LLMValidationError as e:
            error_code = getattr(e, "error_code", None) or ""
            if not self._is_repairable(error_code):
                raise DAXGenerationError(
                    "DAX 生成失败（不可修复错误）"
                ) from e
            if self._max_repairs < 1:
                raise DAXGenerationError(
                    "DAX 生成失败（格式修复已禁用）"
                ) from e
        except LLMProviderError as e:
            raise DAXGenerationError(
                "DAX 生成失败（Provider 错误）"
            ) from e
        except Exception as e:
            raise DAXGenerationError(
                "DAX 生成失败"
            ) from e

        # 4. 一次格式修复
        try:
            dax_request = await self._try_generate(
                qp_summary, schema_text, effective_model_key, request_id,
                repair_error_code="invalid_content_json_or_schema",
            )
            safety = self._safety_validator.validate(dax_request.dax, schema)
            if not safety.is_valid:
                raise DAXGenerationError(
                    f"DAX 安全验证失败（格式修复后）: {'; '.join(safety.errors)}"
                )
            return dax_request
        except DAXGenerationError:
            raise
        except LLMValidationError as e:
            raise DAXGenerationError(
                "DAX 生成失败（格式修复后仍无效）"
            ) from e
        except LLMProviderError as e:
            raise DAXGenerationError(
                "DAX 生成失败（Provider 错误）"
            ) from e
        except Exception as e:
            raise DAXGenerationError(
                "DAX 生成失败（未知错误）"
            ) from e

    # ── 内部方法 ──

    async def _try_generate(
        self,
        qp_summary: str,
        schema_text: str,
        semantic_model_key: str,
        request_id: str,
        repair_error_code: Optional[str] = None,
    ) -> DAXRequest:
        """单次 DAX 生成调用"""
        messages = build_dax_messages(
            query_plan_summary=qp_summary,
            schema_text=schema_text,
            semantic_model_key=semantic_model_key,
            request_id=request_id,
            repair_error_code=repair_error_code,
        )

        req = LLMRequest(
            messages=messages,
            task=LLMTask.DAX,
        )

        response = await self._provider.generate(req, DAXRequest)

        if response.structured is None:
            raise DAXGenerationError("Provider 返回的 structured 为 None")

        dax_req = response.structured
        # 确保字段正确
        dax_req.semantic_model_key = semantic_model_key
        dax_req.request_id = request_id
        dax_req.is_mock = False
        return dax_req

    async def _try_repair(
        self,
        qp_summary: str,
        schema_text: str,
        semantic_model_key: str,
        request_id: str,
        error_code: str,
        illegal_objects: str = "",
    ) -> DAXRequest:
        """DAX 安全修复调用"""
        messages = build_dax_messages(
            query_plan_summary=qp_summary,
            schema_text=schema_text,
            semantic_model_key=semantic_model_key,
            request_id=request_id,
            repair_error_code=error_code,
            illegal_objects=illegal_objects,
        )

        req = LLMRequest(
            messages=messages,
            task=LLMTask.DAX,
        )

        response = await self._provider.generate(req, DAXRequest)
        if response.structured is None:
            raise DAXGenerationError("Provider 返回的 structured 为 None")

        dax_req = response.structured
        dax_req.semantic_model_key = semantic_model_key
        dax_req.request_id = request_id
        dax_req.is_mock = False
        return dax_req

    @staticmethod
    def _format_query_plan_summary(plan: QueryPlan) -> str:
        """格式化 QueryPlan 为文本摘要（不发送完整模型 JSON）"""
        parts = [f"标准化问题：{plan.normalized_question}"]

        if plan.measures:
            parts.append(f"指标：{', '.join(plan.measures)}")
        if plan.dimensions:
            parts.append(f"维度：{', '.join(plan.dimensions)}")
        if plan.filters:
            filter_strs = [
                f"{f.field} {f.operator.value} {f.value}"
                for f in plan.filters
            ]
            parts.append(f"筛选条件：{'; '.join(filter_strs)}")
        if plan.time_range:
            if hasattr(plan.time_range, "model_dump_json"):
                parts.append(f"结构化时间范围：{plan.time_range.model_dump_json()}")
            else:
                parts.append(f"时间范围：{plan.time_range}")
        if plan.sort:
            parts.append(f"排序：{plan.sort}")
        if plan.top_n:
            parts.append(f"Top N：{plan.top_n}")
        if plan.comparison_mode:
            parts.append(f"对比模式：{plan.comparison_mode}")

        return "\n".join(parts)

    @staticmethod
    def _is_repairable(error_code: str) -> bool:
        return error_code in {"invalid_content_json", "output_schema_invalid"}

    def validate_safety(self, dax: str, schema: Optional[SemanticModelSchema] = None) -> DAXSafetyResult:
        """公开的 DAX 安全验证（不访问网络）"""
        return self._safety_validator.validate(dax, schema)

    # ── 属性 ──

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def max_dax_repairs(self) -> int:
        return self._max_repairs
