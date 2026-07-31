"""报表渲染器抽象接口"""

from abc import ABC, abstractmethod

from backend.app.schemas.data_contracts import ReportSpec


class ReportRenderer(ABC):
    """报表渲染器抽象"""

    @abstractmethod
    async def render(self, report: ReportSpec) -> str:
        """渲染 ReportSpec 为 HTML 字符串"""
        ...

    @property
    @abstractmethod
    def supported_templates(self) -> list[str]:
        """支持的模板列表"""
        ...
