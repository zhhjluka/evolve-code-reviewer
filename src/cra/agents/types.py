"""Agent 数据模型"""
from dataclasses import dataclass, field
from enum import Enum


class IssueCategory(str, Enum):
    AUTO_FIXABLE = "auto_fixable"    # 可自动优化（OpenEvolve 进化）
    NEEDS_HUMAN = "needs_human"      # 需人工判断


@dataclass
class ReviewIssue:
    """审查 Agent 发现的一个问题"""
    agent: str              # 来源 Agent: security/complexity/performance/readability/style
    severity: str           # blocker / suggestion / nit
    file: str               # 文件路径
    line: int               # 行号
    rule: str               # 规则 ID
    message: str            # 问题描述
    suggestion: str = ""    # 修复建议
    evidence: str = ""      # 证据（代码片段）
    fix_code: str = ""      # 修复代码示例
    category: str = "needs_human"  # auto_fixable / needs_human（默认需人工判断）


class MergedIssue:
    """Arbiter 去重合并后的问题"""
    agents: list[str]       # 来源 Agent 列表
    severity: str           # 取最高严重程度
    file: str
    lines: list[int]        # 合并的行号
    rules: list[str]
    messages: list[str]
    suggestions: list[str]

    def __init__(self, issue: ReviewIssue):
        self.agents = [issue.agent]
        self.severity = issue.severity
        self.file = issue.file
        self.lines = [issue.line]
        self.rules = [issue.rule]
        self.messages = [issue.message]
        self.suggestions = [issue.suggestion] if issue.suggestion else []

    def merge(self, other: ReviewIssue):
        self.agents.append(other.agent)
        self.lines.append(other.line)
        self.rules.append(other.rule)
        self.messages.append(other.message)
        if other.suggestion:
            self.suggestions.append(other.suggestion)
        # 取最高严重程度
        severity_order = {"blocker": 3, "suggestion": 2, "nit": 1}
        if severity_order.get(other.severity, 0) > severity_order.get(self.severity, 0):
            self.severity = other.severity

    @property
    def line_range(self) -> str:
        if len(self.lines) == 1:
            return str(self.lines[0])
        return f"{min(self.lines)}-{max(self.lines)}"


def classify_issue(issue: ReviewIssue) -> str:
    """根据 Agent 来源自动判断问题类别"""
    # 安全漏洞：修复方式取决于上下文（怎么修才是安全的？）
    if issue.agent == "security":
        return IssueCategory.NEEDS_HUMAN

    # 复杂度 / 性能 / 可读性 / 风格：可以自动优化
    if issue.agent in ("complexity", "performance", "readability", "style"):
        return IssueCategory.AUTO_FIXABLE

    # 默认：需要人工判断
    return IssueCategory.NEEDS_HUMAN
