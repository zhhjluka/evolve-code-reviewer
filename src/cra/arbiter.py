"""Arbiter — 去重、冲突解决、审查报告生成"""

from datetime import datetime
from .agents.types import ReviewIssue, MergedIssue

# 优先级链：数字越大优先级越高
_PRIORITY = {
    "security": 50,
    "performance": 30,
    "complexity": 25,
    "readability": 10,
    "style": 5,
}


def deduplicate(issues: list[ReviewIssue], line_tolerance: int = 3) -> list[MergedIssue]:
    """按文件+行号范围去重，将同一位置的多个问题合并为一个 MergedIssue"""
    if not issues:
        return []

    merged: list[MergedIssue] = []

    for issue in issues:
        found = False
        for m in merged:
            if m.file == issue.file and any(
                abs(issue.line - line) <= line_tolerance for line in m.lines
            ):
                m.merge(issue)
                found = True
                break
        if not found:
            merged.append(MergedIssue(issue))

    return merged


def resolve_conflict(blocker_agent: str, blocker_message: str,
                     conflicting_agent: str, conflicting_message: str) -> dict:
    """解决两个 Agent 的建议冲突"""
    blocker_priority = _PRIORITY.get(blocker_agent, 0)
    conflicting_priority = _PRIORITY.get(conflicting_agent, 0)

    if blocker_priority >= conflicting_priority:
        winner = blocker_agent
        resolution = _generate_resolution(winner, blocker_message, conflicting_agent, conflicting_message)
    else:
        winner = conflicting_agent
        resolution = _generate_resolution(winner, conflicting_message, blocker_agent, blocker_message)

    return {"winner": winner, "resolution": resolution}


def _generate_resolution(winner: str, winner_msg: str,
                         loser: str, loser_msg: str) -> str:
    """生成冲突解决建议"""
    if winner == "security":
        return (f"Security requirement ({winner_msg}) takes priority. "
                f"Address the {loser} concern ({loser_msg}) in a separate function if possible.")
    if winner == "complexity" and loser == "readability":
        return (f"Complexity reduction ({winner_msg}) is more important. "
                f"Readability ({loser_msg}) will improve as a side effect of refactoring.")
    return f"Both concerns are valid. Prioritize {winner} ({winner_msg}), then address {loser} ({loser_msg})."


def generate_report(issues: list[ReviewIssue], pr_number: int,
                    source_branch: str, target_branch: str,
                    health_score: int = 0) -> str:
    """生成统一的审查报告"""
    merged = deduplicate(issues)

    blockers = [m for m in merged if m.severity == "blocker"]
    suggestions = [m for m in merged if m.severity == "suggestion"]
    nits = [m for m in merged if m.severity == "nit"]

    if not merged:
        return "✅ All clean — no issues found."

    lines = [
        f"## 📋 Code Review Report — PR #{pr_number}",
        "",
        f"**Branch**: `{source_branch}` → `{target_branch}`",
        f"**Review Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Issues**: {len(blockers)} 🔴 {len(suggestions)} 🟡 {len(nits)} 💭",
        "",
    ]

    if blockers:
        lines.append(f"### 🔴 Blockers ({len(blockers)} — must fix)")
        lines.append("")
        for i, issue in enumerate(blockers, 1):
            agents_str = ", ".join(issue.agents)
            lines.append(f"**{i}. [{issue.rules[0]}] {issue.messages[0]}**")
            lines.append(f"   📍 `{issue.file}:{issue.line_range}` | Source: {agents_str}")
            if issue.suggestions:
                lines.append(f"   💡 {issue.suggestions[0]}")
            lines.append("")

    if suggestions:
        lines.append(f"### 🟡 Suggestions ({len(suggestions)} — recommend fixing)")
        lines.append("")
        lines.append("| # | Rule | File | Issue | Source |")
        lines.append("|---|------|------|-------|--------|")
        for i, issue in enumerate(suggestions, 1):
            agents_str = ", ".join(issue.agents)
            lines.append(
                f"| {i} | {issue.rules[0]} | `{issue.file}:{issue.line_range}` | "
                f"{issue.messages[0][:60]} | {agents_str} |"
            )
        lines.append("")

    if nits:
        lines.append(f"### 💭 Nits ({len(nits)} — optional)")
        lines.append("")
        for issue in nits:
            lines.append(f"- `{issue.file}:{issue.line_range}`: {issue.messages[0]}")
        lines.append("")

    return "\n".join(lines)
