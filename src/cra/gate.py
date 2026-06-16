"""
Static Gate — 不依赖 LLM 的代码质量硬检查。

Stage 0: 在 PR 进入 AI 审查之前运行，直接阻断最严重的问题。
"""

import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GateIssue:
    file: str
    line: int
    rule: str
    severity: str  # "blocker" | "warning"
    message: str
    evidence: str = ""


@dataclass
class GateResult:
    passed: bool
    issues: list[GateIssue] = field(default_factory=list)
    blocker_count: int = 0

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


# ─── 复杂度检查 ────────────────────────────────────────────────────

def check_complexity(filepath: str, threshold: int = 15) -> list[GateIssue]:
    """
    使用 radon 检查圈复杂度。超过阈值的函数返回 🔴 blocker。
    """
    try:
        import radon.complexity as rcomp
        from radon.visitors import ComplexityVisitor
    except ImportError:
        return [GateIssue(
            file=filepath, line=0, rule="COMPLEXITY-SETUP",
            severity="warning",
            message="radon not installed. Install with: pip install radon"
        )]

    with open(filepath) as f:
        source = f.read()

    visitor = ComplexityVisitor.from_code(source)
    issues = []

    for func in visitor.functions:
        if func.complexity > threshold:
            issues.append(GateIssue(
                file=filepath,
                line=func.lineno,
                rule="COMPLEXITY-HIGH",
                severity="blocker",
                message=(
                    f"Function '{func.name}' has cyclomatic complexity "
                    f"{func.complexity} (threshold: {threshold}). "
                    f"Consider splitting into smaller functions."
                ),
                evidence=f"def {func.name}(...):  # complexity={func.complexity}"
            ))

    return issues


# ─── 安全检查 ──────────────────────────────────────────────────────

_SQL_PATTERNS = [
    (r'(?:f["\']|["\'].*\{.*\}.*["\']|["\']\s*\+).*\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b',
     "SQL-INJECTION-FSTRING",
     "Potential SQL injection: string interpolation used in SQL query. Use parameterized queries."),
    (r'(?:\.execute|\.executemany)\(\s*f["\']',
     "SQL-INJECTION-FORMAT",
     "Potential SQL injection: f-string passed to execute(). Use parameterized queries."),
]

_SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|secret|password|token|auth)\s*[:=]\s*["\'][^\s]{8,}["\']',
     "HARDCODED-SECRET",
     "Hardcoded secret detected. Use environment variables or a secrets manager."),
    (r'(?i)(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)',
     "HARDCODED-PRIVATE-KEY",
     "Private key found in source code. Never commit private keys."),
]


def check_security(filepath: str) -> list[GateIssue]:
    """检查 SQL 注入和硬编码密钥。"""
    issues = []

    with open(filepath) as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        for pattern, rule_id, message in _SQL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker",
                    message=message,
                    evidence=line.strip()[:100],
                ))
                break  # one issue per line per category

        for pattern, rule_id, message in _SECRET_PATTERNS:
            if re.search(pattern, line):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker",
                    message=message,
                    evidence="[REDACTED]",
                ))

    # Check for bare except
    content = "".join(lines)
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(GateIssue(
                    file=filepath, line=node.lineno,
                    rule="BARE-EXCEPT",
                    severity="blocker",
                    message="Bare 'except:' clause detected. Specify exception types.",
                    evidence="except:",
                ))
    except SyntaxError:
        pass

    return issues


# ─── 汇总 ──────────────────────────────────────────────────────────

def run_gate(filepath: str, complexity_threshold: int = 15) -> GateResult:
    """运行所有静态门控检查。"""
    all_issues = (
        check_complexity(filepath, complexity_threshold) +
        check_security(filepath)
    )

    blockers = [i for i in all_issues if i.severity == "blocker"]

    return GateResult(
        passed=len(blockers) == 0,
        issues=all_issues,
        blocker_count=len(blockers),
    )


def format_gate_result(result: GateResult) -> str:
    """格式化门控结果为可读文本。"""
    if result.passed:
        return "✅ Static gate: PASSED"

    lines = ["❌ Static gate: FAILED", ""]
    for issue in result.issues:
        icon = "🔴" if issue.severity == "blocker" else "🟡"
        lines.append(
            f"  {icon} {issue.file}:{issue.line} [{issue.rule}]"
        )
        lines.append(f"     {issue.message}")
        if issue.evidence:
            lines.append(f"     Code: {issue.evidence}")
    return "\n".join(lines)
