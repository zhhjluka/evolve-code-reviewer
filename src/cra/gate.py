"""
Static Gate — 不依赖 LLM 的代码质量硬检查 (v0.3.0)

Stage 0: 在 PR 进入 AI 审查之前运行，直接阻断最严重的问题。

新增 (v0.3.0):
- 认知复杂度检查
- 嵌套深度 / 函数行数 / 参数数量独立告警
- 命令注入 / 路径遍历 / 不安全反序列化 / XSS
- AST 级别安全分析（eval/exec/compile 调用）
- 配置文件驱动阈值 (.code-review.yaml)
"""

import ast
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
    warning_count: int = 0

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


@dataclass
class GateConfig:
    """门控配置，从 .code-review.yaml 读取"""
    cyclomatic_threshold: int = 15
    cognitive_threshold: int = 20
    max_function_lines: int = 80
    max_nesting_depth: int = 4
    max_parameters: int = 5


def load_gate_config(config_path: Optional[str] = None) -> GateConfig:
    """从 .code-review.yaml 加载门控配置"""
    if config_path is None:
        config_path = str(Path.cwd() / ".code-review.yaml")

    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        gate_cfg = data.get("gate", {})
        return GateConfig(
            cyclomatic_threshold=gate_cfg.get("complexity_threshold", 15),
            cognitive_threshold=gate_cfg.get("cognitive_threshold", 20),
            max_function_lines=gate_cfg.get("max_function_lines", 80),
            max_nesting_depth=gate_cfg.get("max_nesting_depth", 4),
            max_parameters=gate_cfg.get("max_parameters", 5),
        )
    except Exception:
        return GateConfig()


# ─── 复杂度检查 ────────────────────────────────────────────────────

def check_complexity(filepath: str, config: GateConfig) -> list[GateIssue]:
    """圈复杂度 + 认知复杂度检查"""
    try:
        from radon.visitors import ComplexityVisitor
    except ImportError:
        return [GateIssue(
            file=filepath, line=0, rule="COMPLEXITY-SETUP",
            severity="warning", message="radon not installed. pip install radon"
        )]

    with open(filepath) as f:
        source = f.read()

    try:
        visitor = ComplexityVisitor.from_code(source)
    except SyntaxError:
        return []

    issues = []

    for func in visitor.functions:
        # 圈复杂度
        if func.complexity > config.cyclomatic_threshold:
            issues.append(GateIssue(
                file=filepath, line=func.lineno,
                rule="COMPLEXITY-CYCLOMATIC",
                severity="blocker",
                message=(
                    f"'{func.name}': cyclomatic complexity {func.complexity} "
                    f"(threshold: {config.cyclomatic_threshold}). "
                    f"Split into smaller functions."
                ),
                evidence=f"def {func.name}(...):  # cyclomatic={func.complexity}"
            ))

        # 认知复杂度（radon 4.0+ 支持）
        if hasattr(func, 'cognitive_complexity') and func.cognitive_complexity > config.cognitive_threshold:
            issues.append(GateIssue(
                file=filepath, line=func.lineno,
                rule="COMPLEXITY-COGNITIVE",
                severity="blocker" if func.cognitive_complexity > config.cognitive_threshold * 1.5 else "warning",
                message=(
                    f"'{func.name}': cognitive complexity {func.cognitive_complexity} "
                    f"(threshold: {config.cognitive_threshold}). "
                    f"Refactor nested logic and break-heavy flow."
                ),
                evidence=f"def {func.name}(...):  # cognitive={func.cognitive_complexity}"
            ))

    return issues


def check_code_metrics(filepath: str, config: GateConfig) -> list[GateIssue]:
    """函数行数 / 嵌套深度 / 参数数量检查（AST 级别）"""
    with open(filepath) as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name

            # 函数行数
            if hasattr(node, 'end_lineno') and node.end_lineno:
                func_lines = node.end_lineno - node.lineno + 1
                if func_lines > config.max_function_lines:
                    issues.append(GateIssue(
                        file=filepath, line=node.lineno,
                        rule="METRICS-FUNC-LENGTH",
                        severity="warning" if func_lines < config.max_function_lines * 1.5 else "blocker",
                        message=(
                            f"'{func_name}': {func_lines} lines "
                            f"(threshold: {config.max_function_lines}). "
                            f"Consider extracting helper functions."
                        ),
                        evidence=f"def {func_name}(...):  # {func_lines} lines"
                    ))

            # 参数数量（跳过 self/cls）
            args = [a for a in node.args.args if a.arg not in ("self", "cls")]
            if len(args) > config.max_parameters:
                issues.append(GateIssue(
                    file=filepath, line=node.lineno,
                    rule="METRICS-PARAM-COUNT",
                    severity="warning",
                    message=(
                        f"'{func_name}': {len(args)} parameters "
                        f"(threshold: {config.max_parameters}). "
                        f"Consider grouping into a dataclass or config dict."
                    ),
                    evidence=f"def {func_name}({', '.join(a.arg for a in args)}):"
                ))

    return issues


def check_nesting_depth(filepath: str, config: GateConfig) -> list[GateIssue]:
    """AST 级别嵌套深度检查"""
    with open(filepath) as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues = []

    class NestingVisitor(ast.NodeVisitor):
        def __init__(self):
            self.max_depth = 0
            self.deepest_node = None

        def _measure_depth(self, node):
            depth = 0
            current = node
            while hasattr(current, 'parent'):
                if isinstance(current, (ast.If, ast.For, ast.While, ast.Try,
                                       ast.With, ast.ExceptHandler, ast.FunctionDef,
                                       ast.AsyncFunctionDef)):
                    depth += 1
                current = current.parent
            return depth

    # 简化版本：用递归遍历统计每个节点的嵌套层级
    def _walk(node, depth=0, parent=None):
        node.parent = parent
        nesting_types = (ast.If, ast.For, ast.While, ast.Try,
                        ast.ExceptHandler, ast.With)
        if isinstance(node, nesting_types):
            depth += 1

        if depth > config.max_nesting_depth:
            nonlocal issues  # can't use nonlocal inside nested function— use list append instead

        for child in ast.iter_child_nodes(node):
            _walk(child, depth, node)

    # Simpler approach: just count nesting in functions
    for func_node in ast.walk(tree):
        if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            def count_max_nesting(node, current_depth=0):
                nesting = (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.With)
                if isinstance(node, nesting):
                    current_depth += 1
                max_d = current_depth
                for child in ast.iter_child_nodes(node):
                    max_d = max(max_d, count_max_nesting(child, current_depth))
                return max_d

            max_depth = count_max_nesting(func_node)
            if max_depth > config.max_nesting_depth:
                issues.append(GateIssue(
                    file=filepath, line=func_node.lineno,
                    rule="METRICS-NESTING",
                    severity="warning" if max_depth <= config.max_nesting_depth + 2 else "blocker",
                    message=(
                        f"'{func_node.name}': max nesting depth {max_depth} "
                        f"(threshold: {config.max_nesting_depth}). "
                        f"Use guard clauses or extract nested blocks."
                    ),
                    evidence=f"def {func_node.name}(...):  # nesting={max_depth}"
                ))

    return issues


# ─── 安全检查 ──────────────────────────────────────────────────────

_SQL_PATTERNS = [
    (r'(?:f["\']|["\'].*\{.*\}.*["\']|["\']\s*\+).*\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b',
     "SEC-SQL-FSTRING", "SQL injection: string interpolation in SQL. Use parameterized queries."),
    (r'(?:\.execute|\.executemany)\(\s*f["\']',
     "SEC-SQL-EXECUTE", "SQL injection: f-string in execute(). Use parameterized queries."),
]

_SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|secret|password|token|auth)\s*[:=]\s*["\'][^\s]{8,}["\']',
     "SEC-HARDCODED-KEY", "Hardcoded secret. Use env vars or secrets manager."),
    (r'(?i)(-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----)',
     "SEC-PRIVATE-KEY", "Private key in source code. Never commit private keys."),
]

_CMD_INJECTION_PATTERNS = [
    (r'(?:os|subprocess)\.(?:system|popen|call|run|Popen)\(\s*f',
     "SEC-CMD-INJECT", "Command injection: f-string/format in shell command. Use subprocess with arg list and shell=False."),
    (r'(?:os|subprocess)\.(?:system|popen|call|run|Popen)\(\s*["\'].*\s*\+',
     "SEC-CMD-INJECT", "Command injection: string concatenation in shell command."),
    (r'(?:os|subprocess)\.(?:system|popen|call|run|Popen)\(\s*["\'].*\$',
     "SEC-CMD-INJECT", "Potential command injection: shell variable expansion in subprocess string."),
]

_PATH_TRAVERSAL_PATTERNS = [
    (r'os\.path\.join\s*\(.*request\.', "SEC-PATH-TRAVERSAL",
     "Path traversal risk: user input in file path. Validate/sanitize paths."),
    (r'open\s*\(\s*.*request\.', "SEC-PATH-OPEN",
     "Path traversal risk: user input in open(). Validate/sanitize paths."),
]

_DESERIALIZE_PATTERNS = [
    (r'pickle\.(load|loads)\(', "SEC-DESERIALIZE-PICKLE",
     "Insecure deserialization: pickle.load(s) on untrusted data."),
    (r'yaml\.load\(', "SEC-DESERIALIZE-YAML",
     "Insecure deserialization: yaml.load() without SafeLoader."),
    (r'(eval|exec|compile)\s*\(', "SEC-DANGEROUS-BUILTIN",
     "Dangerous builtin: eval/exec/compile. Avoid unless strictly necessary."),
]

_XSS_PATTERNS = [
    (r'(?:mark_safe|safe\s*=\s*True|\.html\s*\()',
     "SEC-XSS-UNSAFE", "Potential XSS: unescaped output. Use auto-escaping or mark_safe only when safe."),
]


def check_security(filepath: str) -> list[GateIssue]:
    """全面安全检查：注入、密钥、命令执行、路径遍历、反序列化、XSS"""
    issues = []

    with open(filepath) as f:
        lines = f.readlines()

    for i, line in enumerate(lines, 1):
        # SQL 注入
        for pattern, rule_id, message in _SQL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker", message=message,
                    evidence=line.strip()[:100],
                ))
                break

        # 硬编码密钥
        for pattern, rule_id, message in _SECRET_PATTERNS:
            if re.search(pattern, line):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker", message=message,
                    evidence="[REDACTED]",
                ))
                break

        # 命令注入
        for pattern, rule_id, message in _CMD_INJECTION_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker", message=message,
                    evidence=line.strip()[:100],
                ))
                break

        # 路径遍历
        for pattern, rule_id, message in _PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker", message=message,
                    evidence=line.strip()[:100],
                ))
                break

        # 反序列化
        for pattern, rule_id, message in _DESERIALIZE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="blocker", message=message,
                    evidence=line.strip()[:100],
                ))
                break

        # XSS
        for pattern, rule_id, message in _XSS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append(GateIssue(
                    file=filepath, line=i, rule=rule_id,
                    severity="warning", message=message,
                    evidence=line.strip()[:100],
                ))
                break

    # AST 级别检查
    content = "".join(lines)
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            # 裸 except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(GateIssue(
                    file=filepath, line=node.lineno,
                    rule="SEC-BARE-EXCEPT", severity="blocker",
                    message="Bare 'except:' clause. Specify exception types.",
                    evidence="except:",
                ))
            # eval/exec/compile 调用
            if isinstance(node, ast.Call):
                func_name = _get_call_name(node)
                if func_name in ("eval", "exec", "compile"):
                    issues.append(GateIssue(
                        file=filepath, line=node.lineno,
                        rule="SEC-DANGEROUS-BUILTIN", severity="blocker",
                        message=f"Dangerous builtin '{func_name}()'. Avoid unless strictly necessary.",
                        evidence=f"{func_name}(...)",
                    ))
    except SyntaxError:
        pass

    return issues


def _get_call_name(node: ast.Call) -> Optional[str]:
    """获取函数调用的名称"""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


# ─── JS/TS Lint ────────────────────────────────────────────────────

def check_js_lint(filepath: str) -> list[GateIssue]:
    """对 JS/TS 文件运行 ESLint（如果可用）"""
    ext = Path(filepath).suffix
    if ext not in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        return []

    try:
        result = subprocess.run(
            ["npx", "eslint", filepath, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return []

        import json
        data = json.loads(result.stdout)
        issues = []
        for file_data in data:
            for msg in file_data.get("messages", []):
                severity = "blocker" if msg.get("severity") == 2 else "warning"
                issues.append(GateIssue(
                    file=filepath, line=msg.get("line", 0),
                    rule=f"ESLINT-{msg.get('ruleId', 'unknown')}",
                    severity=severity,
                    message=msg.get("message", ""),
                ))
        return issues
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return [GateIssue(
            file=filepath, line=0, rule="LINT-SETUP",
            severity="warning",
            message="ESLint not available. Install with: npm install eslint"
        )]


# ─── 汇总 ──────────────────────────────────────────────────────────

def run_gate(filepath: str,
             complexity_threshold: int = 15,
             config: Optional[GateConfig] = None) -> GateResult:
    """运行所有静态门控检查。"""
    if config is None:
        config = load_gate_config()
        # CLI 参数覆盖配置文件
        config.cyclomatic_threshold = complexity_threshold

    all_issues = (
        check_complexity(filepath, config) +
        check_code_metrics(filepath, config) +
        check_nesting_depth(filepath, config) +
        check_security(filepath) +
        check_js_lint(filepath)
    )

    blockers = [i for i in all_issues if i.severity == "blocker"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    return GateResult(
        passed=len(blockers) == 0,
        issues=all_issues,
        blocker_count=len(blockers),
        warning_count=len(warnings),
    )


def format_gate_result(result: GateResult) -> str:
    """格式化门控结果为可读文本。"""
    if result.passed:
        msg = "✅ Static gate: PASSED"
        if result.warning_count:
            msg += f" ({result.warning_count} warning(s))"
        return msg

    lines = ["❌ Static gate: FAILED", ""]

    # 先列阻断项
    blockers = [i for i in result.issues if i.severity == "blocker"]
    if blockers:
        lines.append(f"  🔴 {len(blockers)} blocker(s):")
        for issue in blockers:
            lines.append(f"     {issue.file}:{issue.line} [{issue.rule}]")
            lines.append(f"     {issue.message}")
            if issue.evidence:
                lines.append(f"     → {issue.evidence}")

    # 再列警告
    warnings = [i for i in result.issues if i.severity == "warning"]
    if warnings:
        lines.append(f"  🟡 {len(warnings)} warning(s):")
        for issue in warnings:
            lines.append(f"     {issue.file}:{issue.line} [{issue.rule}]")
            lines.append(f"     {issue.message}")

    return "\n".join(lines)
