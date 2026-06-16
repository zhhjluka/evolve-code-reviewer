"""Agent 基类"""
from abc import ABC, abstractmethod
from .types import ReviewIssue


class ReviewAgent(ABC):
    """所有审查 Agent 的基类"""

    name: str = "base"
    system_prompt: str = ""

    @abstractmethod
    def review(self, code: str) -> list[ReviewIssue]:
        """审查代码，返回发现的问题列表"""
        ...
