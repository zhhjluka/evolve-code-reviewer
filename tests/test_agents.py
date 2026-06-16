"""TDD: Agent 模块测试套件

测试覆盖:
- Agent 数据模型 (ReviewIssue, ReviewReport)
- 问题分类器 (可自动优化 vs 需人工判断)
- Arbiter (去重 + 冲突解决 + 报告格式化)
"""
import pytest
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# 导入被测模块（如果还不存在，先写接口，测试会红）
# ═══════════════════════════════════════════════════════════════

# 先用 dataclass 定义期望的接口，然后在实现中引用
# from cra.agents.types import ReviewIssue, ReviewReport, IssueCategory


# ═══════════════════════════════════════════════════════════════
# 数据模型测试
# ═══════════════════════════════════════════════════════════════

class TestReviewIssue:
    """审查问题的数据模型"""

    def test_issue_has_required_fields(self):
        """问题必须有: agent来源、严重程度、文件位置、消息"""
        from cra.agents.types import ReviewIssue
        
        issue = ReviewIssue(
            agent="security",
            severity="blocker",
            file="src/app.py",
            line=42,
            rule="SEC-SQL-INJECTION",
            message="SQL injection detected",
            suggestion="Use parameterized queries",
        )
        assert issue.agent == "security"
        assert issue.severity == "blocker"
        assert issue.line == 42

    def test_issue_optional_fields_default(self):
        """可选字段默认值"""
        from cra.agents.types import ReviewIssue
        
        issue = ReviewIssue(
            agent="readability",
            severity="suggestion",
            file="src/utils.py",
            line=10,
            rule="READ-NAMING",
            message="Unclear variable name",
        )
        assert issue.evidence == ""
        assert issue.suggestion == ""
        assert issue.fix_code == ""
        # 默认 category 不自动推断，由 Agent 显式设置


class TestIssueCategory:
    """问题分类: 可自动优化 vs 需人工判断"""

    def test_security_is_always_needs_human(self):
        """安全漏洞的修复方式需要人工判断"""
        from cra.agents.types import ReviewIssue, IssueCategory, classify_issue
        
        issue = ReviewIssue(
            agent="security", severity="blocker",
            file="app.py", line=1, rule="SEC-X", message="vuln",
        )
        assert classify_issue(issue) == IssueCategory.NEEDS_HUMAN

    def test_complexity_is_auto_fixable(self):
        """高复杂度可以自动优化（OpenEvolve 拆分函数）"""
        from cra.agents.types import ReviewIssue, IssueCategory, classify_issue
        
        issue = ReviewIssue(
            agent="complexity", severity="blocker",
            file="app.py", line=1, rule="COMPLEXITY-HIGH", message="too complex",
        )
        assert classify_issue(issue) == IssueCategory.AUTO_FIXABLE

    def test_performance_is_auto_fixable(self):
        """性能问题可以自动优化（算法替换、缓存等）"""
        from cra.agents.types import ReviewIssue, IssueCategory, classify_issue
        
        issue = ReviewIssue(
            agent="performance", severity="suggestion",
            file="app.py", line=1, rule="PERF-N1", message="N+1 query",
        )
        assert classify_issue(issue) == IssueCategory.AUTO_FIXABLE

    def test_readability_is_auto_fixable(self):
        """可读性问题可以自动优化（命名、注释、结构）"""
        from cra.agents.types import ReviewIssue, IssueCategory, classify_issue
        
        issue = ReviewIssue(
            agent="readability", severity="suggestion",
            file="app.py", line=1, rule="READ-NAME", message="bad name",
        )
        assert classify_issue(issue) == IssueCategory.AUTO_FIXABLE

    def test_style_is_auto_fixable(self):
        """风格问题可以自动修复"""
        from cra.agents.types import ReviewIssue, IssueCategory, classify_issue
        
        issue = ReviewIssue(
            agent="style", severity="nit",
            file="app.py", line=1, rule="STYLE-FMT", message="fmt",
        )
        assert classify_issue(issue) == IssueCategory.AUTO_FIXABLE

    def test_explicit_category_overrides_auto(self):
        """如果 issue 已经设置了 category，使用设置值"""
        from cra.agents.types import ReviewIssue, IssueCategory, classify_issue
        
        # 默认是 needs_human，即使复杂度 Agent 产出也保持
        issue = ReviewIssue(
            agent="complexity", severity="blocker",
            file="app.py", line=1, rule="X", message="m",
            # 不设 category → 默认 needs_human
        )
        # ReviewIssue 的默认 category 是 needs_human
        assert issue.category == IssueCategory.NEEDS_HUMAN
        
        # 显式设置 auto_fixable
        issue2 = ReviewIssue(
            agent="complexity", severity="blocker",
            file="app.py", line=1, rule="X", message="m",
            category="auto_fixable",
        )
        assert issue2.category == IssueCategory.AUTO_FIXABLE


# ═══════════════════════════════════════════════════════════════
# Arbiter 测试
# ═══════════════════════════════════════════════════════════════

class TestArbiterDeduplicate:
    """去重逻辑"""

    def test_same_location_merged(self):
        """同一文件的同一行附近 → 合并"""
        from cra.agents.types import ReviewIssue
        from cra.arbiter import deduplicate
        
        issues = [
            ReviewIssue(agent="complexity", severity="blocker", file="a.py", line=47, rule="C1", message="too complex"),
            ReviewIssue(agent="readability", severity="suggestion", file="a.py", line=48, rule="R1", message="unclear"),
        ]
        merged = deduplicate(issues, line_tolerance=3)
        assert len(merged) == 1
        assert "complexity" in merged[0].agents
        assert "readability" in merged[0].agents

    def test_different_files_not_merged(self):
        """不同文件 → 不合并"""
        from cra.agents.types import ReviewIssue
        from cra.arbiter import deduplicate
        
        issues = [
            ReviewIssue(agent="security", severity="blocker", file="a.py", line=10, rule="S1", message="vuln"),
            ReviewIssue(agent="security", severity="blocker", file="b.py", line=10, rule="S1", message="vuln"),
        ]
        merged = deduplicate(issues)
        assert len(merged) == 2

    def test_far_apart_lines_not_merged(self):
        """同一文件但行号差距大 → 不合并"""
        from cra.agents.types import ReviewIssue
        from cra.arbiter import deduplicate
        
        issues = [
            ReviewIssue(agent="security", severity="blocker", file="a.py", line=10, rule="S1", message="v"),
            ReviewIssue(agent="security", severity="blocker", file="a.py", line=100, rule="S2", message="v"),
        ]
        merged = deduplicate(issues, line_tolerance=5)
        assert len(merged) == 2


class TestArbiterConflictResolution:
    """冲突解决"""

    def test_security_wins_over_complexity(self):
        """安全 > 复杂度"""
        from cra.arbiter import resolve_conflict
        
        result = resolve_conflict(
            blocker_agent="complexity",
            blocker_message="Function too long (85 lines)",
            conflicting_agent="security",
            conflicting_message="Must add input validation (+5 lines)",
        )
        assert result["winner"] == "security"
        assert "extract validation" in result["resolution"].lower() or "separate function" in result["resolution"].lower()

    def test_higher_priority_wins(self):
        """优先级高的 Agent 的建议优先"""
        from cra.arbiter import resolve_conflict
        
        # readability < complexity
        result = resolve_conflict("readability", "Rename variable", "complexity", "Split function")
        assert result["winner"] == "complexity"

    def test_same_priority_first_wins(self):
        """同优先级保持原建议"""
        from cra.arbiter import resolve_conflict
        
        result = resolve_conflict("security", "Fix SQL injection", "security", "Add rate limiting")
        assert result["winner"] in ("security",)  # 同 Agent 都接受
        assert "both" in result["resolution"].lower() or "security" in result["resolution"].lower()


class TestArbiterReport:
    """报告生成"""

    def test_formats_blockers_first(self):
        """阻断项排在建议前面"""
        from cra.agents.types import ReviewIssue
        from cra.arbiter import generate_report
        
        issues = [
            ReviewIssue(agent="readability", severity="suggestion", file="a.py", line=10, rule="R1", message="unclear name", suggestion="Rename to x"),
            ReviewIssue(agent="security", severity="blocker", file="a.py", line=47, rule="S1", message="SQL injection", suggestion="Use params"),
        ]
        report = generate_report(issues, pr_number=42, source_branch="feat/x", target_branch="main")
        # 阻断项应该排在前面
        blocker_pos = report.find("SQL injection")
        suggest_pos = report.find("unclear name")
        assert blocker_pos < suggest_pos
        assert "PR #42" in report
        assert "feat/x" in report

    def test_empty_issues(self):
        """无问题时的报告"""
        from cra.arbiter import generate_report
        report = generate_report([], pr_number=1, source_branch="feat/x", target_branch="main")
        assert "No issues" in report or "PASSED" in report or "clean" in report.lower()


# ═══════════════════════════════════════════════════════════════
# Agent 基类测试
# ═══════════════════════════════════════════════════════════════

class TestAgentBase:
    """Agent 基类功能"""

    def test_agent_has_name_and_prompt(self):
        """每个 Agent 必须有 name 和 system_prompt"""
        from cra.agents.base import ReviewAgent
        
        class TestAgent(ReviewAgent):
            name = "test"
            system_prompt = "You are a test agent"
            def review(self, code: str) -> list:
                return []
        
        agent = TestAgent()
        assert agent.name == "test"
        assert "test agent" in agent.system_prompt

    def test_agent_extracts_issues_from_diff(self):
        """Agent 接受 code diff 返回问题列表"""
        from cra.agents.base import ReviewAgent
        from cra.agents.types import ReviewIssue
        
        class TestAgent(ReviewAgent):
            name = "test"
            system_prompt = "test prompt"
            def review(self, code: str) -> list[ReviewIssue]:
                return [ReviewIssue(
                    agent=self.name, severity="suggestion",
                    file="test.py", line=1, rule="TEST", message="found issue",
                )]
        
        agent = TestAgent()
        issues = agent.review("some code")
        assert len(issues) == 1
        assert issues[0].agent == "test"


class TestAgentEnsemble:
    """多 Agent 并行运行"""

    def test_ensemble_runs_all_agents(self):
        """Ensemble 运行所有注册的 Agent"""
        from cra.agents.base import ReviewAgent
        from cra.agents.types import ReviewIssue
        from cra.agents.ensemble import run_all_agents
        
        class MockAgent(ReviewAgent):
            name = "mock"
            system_prompt = "mock"
            def review(self, code: str) -> list[ReviewIssue]:
                return [ReviewIssue(
                    agent=self.name, severity="suggestion",
                    file="test.py", line=1, rule="MOCK", message="mock issue",
                )]
        
        results = run_all_agents("code", agents=[MockAgent(), MockAgent()])
        assert "mock" in results
        assert len(results["mock"]) == 1
