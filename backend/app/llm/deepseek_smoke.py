"""DeepSeek 最小真实连通测试 — M1.1

通过 Settings 运行时加载 Key，执行一次最小合成请求。
不打开/读取 .env 文本。不输出 Key/Authorization/Prompt/完整响应。
不写入文件、日志、Trace 或 Smoke Dump。不使用真实业务数据。

运行：
    python -m backend.app.llm.deepseek_smoke

安全输出：
    success=true/false
    provider=deepseek
    model=<配置模型名>
    prompt_tokens=<int>
    completion_tokens=<int>
    total_tokens=<int>
    error_type=<脱敏类型>
    status_code=<可选>
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal


class DeepSeekSmokeResponse(BaseModel):
    """Smoke 测试期望的最小响应"""
    status: Literal["ok"]


# 合成消息 — 不包含真实业务数据
SMOKE_MESSAGES = [
    {
        "role": "user",
        "content": (
            "Return only one valid JSON object with exactly one key 'status' "
            'set to "ok". Do not include any other text, explanation, or '
            "markdown formatting. Output example: {\"status\":\"ok\"}"
        ),
    },
]


async def _run_smoke() -> dict:
    """执行一次真实连通测试。返回脱敏结果 dict。"""
    from backend.app.config.settings import Settings
    from backend.app.llm.deepseek import DeepSeekLLMProvider
    from backend.app.llm.base import (
        LLMAuthenticationError,
        LLMConfigurationError,
        LLMConnectionError,
        LLMProviderError,
        LLMRateLimitError,
        LLMRequestError,
        LLMResponseError,
        LLMServiceError,
        LLMTimeoutError,
        LLMValidationError,
        LLMRequest,
    )

    settings = Settings()

    # 检查 Key
    if not settings.is_deepseek_configured:
        return {
            "success": False,
            "error_type": "deepseek_api_key_missing",
        }

    # 构造 Provider
    provider = DeepSeekLLMProvider(
        api_key=settings.deepseek_api_key,  # type: ignore[arg-type]
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=float(settings.request_timeout_seconds),
    )

    request = LLMRequest(messages=SMOKE_MESSAGES)

    try:
        response = await provider.generate(request, DeepSeekSmokeResponse)
        await provider.aclose()

        return {
            "success": True,
            "provider": "deepseek",
            "model": response.model or settings.deepseek_model,
            "prompt_tokens": response.usage.get("prompt_tokens", 0),
            "completion_tokens": response.usage.get("completion_tokens", 0),
            "total_tokens": response.usage.get("total_tokens", 0),
        }
    except LLMConfigurationError as e:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": "configuration_error",
        }
    except LLMAuthenticationError as e:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": "authentication_error",
            "status_code": e.status_code,
        }
    except LLMRateLimitError as e:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": "rate_limit_error",
            "status_code": e.status_code,
        }
    except LLMConnectionError:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": "connection_error",
        }
    except LLMTimeoutError:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": "timeout",
        }
    except (LLMRequestError, LLMResponseError, LLMValidationError, LLMServiceError) as e:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": type(e).__name__.replace("LLM", "").replace("Error", "").lower(),
            "status_code": getattr(e, "status_code", None),
        }
    except LLMProviderError as e:
        await provider.aclose()
        return {
            "success": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "error_type": "provider_error",
        }


def main() -> int:
    """命令行入口"""
    result = asyncio.run(_run_smoke())

    # 仅输出脱敏字段
    for key in ("success", "provider", "model", "prompt_tokens",
                 "completion_tokens", "total_tokens", "error_type", "status_code"):
        if key in result and result[key] is not None:
            print(f"{key}={result[key]}")

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
