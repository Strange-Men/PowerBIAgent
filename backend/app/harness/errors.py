"""Harness 统一异常类型"""


class HarnessError(Exception):
    """Harness 基础异常"""
    pass


class ToolNotRegisteredError(HarnessError):
    """工具未注册"""
    pass


class ToolPolicyDeniedError(HarnessError):
    """工具策略拒绝"""
    pass


class TurnStateError(HarnessError):
    """Turn 状态非法转换"""
    pass


class ValidationError(HarnessError):
    """验证失败"""
    pass


class ContextBuildError(HarnessError):
    """上下文构建失败"""
    pass


class TurnLimitExceededError(HarnessError):
    """Turn 资源超限（工具调用次数、重试次数等）"""
    pass
