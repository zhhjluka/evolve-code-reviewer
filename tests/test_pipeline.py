"""TDD: Pipeline 集成测试 — Agent→Evolution→Arbiter 全链路"""
import pytest
from cra.agents.types import ReviewIssue, IssueCategory
from cra.arbiter import deduplicate, generate_report
from cra.gate import GateResult, GateIssue


class TestPipelineIntegration:
    """Agent→Evolution 全链路"""

    def test_auto_fixable_issues_identified(self):
        """Agent 发现的问题正确分类为 auto_fixable/needs_human"""
        issues = [
            ReviewIssue(agent="complexity", severity="blocker", file="a.py", line=10, rule="C1", message="too complex", category="auto_fixable"),
            ReviewIssue(agent="security", severity="blocker", file="a.py", line=20, rule="S1", message="SQL injection", category="needs_human"),
            ReviewIssue(agent="performance", severity="suggestion", file="b.py", line=5, rule="P1", message="N+1", category="auto_fixable"),
            ReviewIssue(agent="readability", severity="suggestion", file="c.py", line=1, rule="R1", message="bad name", category="auto_fixable"),
            ReviewIssue(agent="style", severity="nit", file="d.py", line=1, rule="ST1", message="fmt", category="auto_fixable"),
        ]
        auto = [i for i in issues if i.category == IssueCategory.AUTO_FIXABLE]
        human = [i for i in issues if i.category == IssueCategory.NEEDS_HUMAN]
        assert len(auto) == 4
        assert len(human) == 1
        assert human[0].agent == "security"

    def test_full_report_generation(self):
        """完整的审查报告生成（含阻断+建议+nit）"""
        issues = [
            ReviewIssue(agent="security", severity="blocker", file="a.py", line=10, rule="SEC", message="SQL injection", suggestion="Use params", category="needs_human"),
            ReviewIssue(agent="complexity", severity="blocker", file="b.py", line=5, rule="CMP", message="Too complex", suggestion="Split function", category="auto_fixable"),
            ReviewIssue(agent="readability", severity="suggestion", file="c.py", line=1, rule="READ", message="Bad name", suggestion="Rename", category="auto_fixable"),
            ReviewIssue(agent="style", severity="nit", file="d.py", line=1, rule="STY", message="Format", suggestion="Auto-fix", category="auto_fixable"),
        ]
        report = generate_report(issues, pr_number=99, source_branch="feat/x", target_branch="main")
        assert "PR #99" in report
        assert "SQL injection" in report
        assert "Too complex" in report
        # blockers before suggestions before nits
        b_idx = report.find("SQL")
        s_idx = report.find("Bad name")
        n_idx = report.find("Format")
        assert b_idx < s_idx < n_idx

    def test_empty_pipeline_handled(self):
        """空审查（无问题）正常处理"""
        report = generate_report([], pr_number=1, source_branch="feat/x", target_branch="main")
        assert "no issues" in report.lower()


class TestFeedbackCollector:
    """反馈收集器"""

    def test_record_accept(self):
        """记录采纳操作"""
        from cra.feedback import FeedbackCollector, FeedbackEntry
        import tempfile, json
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = FeedbackCollector(Path(tmpdir))
            collector.record("pr-42", "issue-1", "accept", reviewer="alice")
            
            entries = list(collector.load("pr-42"))
            assert len(entries) == 1
            assert entries[0].action == "accept"
            assert entries[0].reviewer == "alice"

    def test_record_reject(self):
        """记录驳回操作（含原因）"""
        from cra.feedback import FeedbackCollector
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = FeedbackCollector(Path(tmpdir))
            collector.record("pr-42", "issue-2", "reject", reviewer="bob", reason="False positive - framework boilerplate")
            
            entries = list(collector.load("pr-42"))
            assert len(entries) == 1
            assert entries[0].action == "reject"
            assert "framework" in entries[0].reason

    def test_stats_aggregation(self):
        """统计各 Agent 的采纳率"""
        from cra.feedback import FeedbackCollector
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = FeedbackCollector(Path(tmpdir))
            collector.record("pr-1", "sec-1", "accept", agent="security")
            collector.record("pr-1", "sec-2", "reject", agent="security", reason="fp")
            collector.record("pr-1", "cmp-1", "accept", agent="complexity")
            
            stats = collector.stats()
            assert stats["security"]["total"] == 2
            assert stats["security"]["acceptance_rate"] == 0.5
            assert stats["complexity"]["total"] == 1
            assert stats["complexity"]["acceptance_rate"] == 1.0
