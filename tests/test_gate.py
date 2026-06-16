"""TDD: Static Gate 完整测试套件

测试覆盖：
- 圈复杂度 / 认知复杂度
- 函数行数 / 嵌套深度 / 参数数量
- SQL 注入 / 命令注入 / 路径遍历
- 硬编码密钥 / 不安全反序列化 / XSS / eval
- 裸 except
- 配置驱动阈值
- JS lint 跳过逻辑
"""

import pytest
from cra.gate import (
    GateIssue,
    GateResult,
    GateConfig,
    check_complexity,
    check_code_metrics,
    check_nesting_depth,
    check_security,
    check_js_lint,
    run_gate,
    format_gate_result,
    load_gate_config,
)


# ════════════════════════════════════════════════════════════════════
# 复杂度检查
# ════════════════════════════════════════════════════════════════════

class TestComplexity:
    """圈复杂度 + 认知复杂度"""

    def test_passes_simple_function(self, write_code, gate_config):
        filepath = write_code("def simple(x):\n    return x + 1\n")
        issues = check_complexity(filepath, gate_config)
        assert issues == []

    def test_catches_high_cyclomatic(self, write_code, gate_config):
        # 圈复杂度 >15: if(x7) + for(x2) + while + and/or(x4) + except = ~18
        filepath = write_code("""
def very_complex(x, items):
    result = 0
    for item in items:
        if item > 0 and x > 0:
            if item % 2 == 0 or x % 2 == 0:
                result += item
            elif item % 3 == 0 and x % 3 == 0:
                try:
                    result += item * 2
                except ValueError:
                    result -= 1
            elif item > 10:
                result += item * 3
            else:
                while result > 100 and x < 100:
                    result -= 10
                    if result < 0:
                        break
        elif item < 0:
            if item > -5 or x < -5:
                result += 1
            elif item > -10:
                result -= 2
            else:
                result -= item
    return result
""")
        issues = check_complexity(filepath, gate_config)
        assert len(issues) >= 1
        assert issues[0].rule == "COMPLEXITY-CYCLOMATIC"
        assert issues[0].severity == "blocker"

    def test_respects_custom_threshold(self, write_code):
        config = GateConfig(cyclomatic_threshold=3)
        # 简单的 if-else 圈复杂度 = 2
        filepath = write_code("""
def has_if(x):
    if x > 0:
        return 1
    return 0
""")
        issues = check_complexity(filepath, config)
        # 2 <= 3 → should pass
        assert issues == []

    def test_handles_syntax_error(self, write_code, gate_config):
        filepath = write_code("def broken(\n    invalid syntax!!!")
        # SyntaxError should be caught gracefully
        try:
            issues = check_complexity(filepath, gate_config)
            assert isinstance(issues, list)
        except SyntaxError:
            pytest.fail("check_complexity should catch SyntaxError")


# ════════════════════════════════════════════════════════════════════
# 代码度量检查（行数/嵌套/参数）
# ════════════════════════════════════════════════════════════════════

class TestCodeMetrics:
    """函数行数 + 参数数量"""

    def test_passes_normal_function(self, write_code, gate_config):
        filepath = write_code("def normal(x, y):\n    return x + y\n")
        issues = check_code_metrics(filepath, gate_config)
        assert issues == []

    def test_catches_long_function(self, write_code):
        config = GateConfig(max_function_lines=3)
        filepath = write_code("def long_func():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n")
        issues = check_code_metrics(filepath, config)
        assert len(issues) >= 1
        assert any(i.rule == "METRICS-FUNC-LENGTH" for i in issues)

    def test_catches_too_many_params(self, write_code):
        config = GateConfig(max_parameters=2)
        filepath = write_code("def many(a, b, c, d):\n    pass\n")
        issues = check_code_metrics(filepath, config)
        assert len(issues) >= 1
        assert any(i.rule == "METRICS-PARAM-COUNT" for i in issues)

    def test_skips_self_cls_params(self, write_code):
        """self/cls 不计入参数数量"""
        config = GateConfig(max_parameters=2)
        filepath = write_code("class Foo:\n    def method(self, a, b):\n        pass\n")
        issues = check_code_metrics(filepath, config)
        # self 被跳过，只有 a,b = 2 个参数，刚好 <= 2
        assert not any(i.rule == "METRICS-PARAM-COUNT" for i in issues)


class TestNestingDepth:
    """嵌套深度 AST 分析"""

    def test_passes_flat_code(self, write_code, gate_config):
        filepath = write_code("def flat():\n    x = 1\n    y = 2\n    return x + y\n")
        issues = check_nesting_depth(filepath, gate_config)
        assert issues == []

    def test_catches_deep_nesting(self, write_code):
        config = GateConfig(max_nesting_depth=2)
        filepath = write_code("""
def deep():
    if True:
        for i in range(10):
            if i > 5:
                while True:
                    pass
""")
        issues = check_nesting_depth(filepath, config)
        assert len(issues) >= 1
        assert any(i.rule == "METRICS-NESTING" for i in issues)

    def test_guard_clauses_not_counted_deep(self, write_code, gate_config):
        """卫语句（if-return）不增加嵌套压力"""
        filepath = write_code("""
def guard(x):
    if x is None:
        return
    if x < 0:
        return
    return x * 2
""")
        issues = check_nesting_depth(filepath, gate_config)
        # 嵌套深度 = 1（只有 if 没有嵌套的 if/for/while）
        assert issues == []


# ════════════════════════════════════════════════════════════════════
# 安全检查
# ════════════════════════════════════════════════════════════════════

class TestSecuritySQL:
    """SQL 注入检测"""

    def test_catches_fstring_sql(self, write_code):
        filepath = write_code('''
def q(user):
    return f"SELECT * FROM users WHERE id = {user}"
''')
        issues = check_security(filepath)
        assert any("SQL" in i.rule for i in issues)

    def test_catches_execute_fstring(self, write_code):
        filepath = write_code('''
def q(cursor, name):
    cursor.execute(f"SELECT * FROM users WHERE name = {name}")
''')
        issues = check_security(filepath)
        assert any("SQL" in i.rule for i in issues)

    def test_passes_parameterized_query(self, write_code):
        filepath = write_code('''
def q(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
''')
        issues = check_security(filepath)
        assert not any("SQL" in i.rule for i in issues)


class TestSecuritySecrets:
    """硬编码密钥检测"""

    def test_catches_api_key(self, write_code):
        filepath = write_code('api_key = "sk-1234567890abcdef"')
        issues = check_security(filepath)
        assert any("HARDCODED" in i.rule for i in issues)

    def test_catches_password(self, write_code):
        filepath = write_code('password = "admin12345678"')
        issues = check_security(filepath)
        assert any("HARDCODED" in i.rule for i in issues)

    def test_passes_env_var(self, write_code):
        filepath = write_code('api_key = os.getenv("API_KEY")')
        issues = check_security(filepath)
        assert not any("HARDCODED" in i.rule for i in issues)


class TestSecurityCommandInjection:
    """命令注入检测"""

    def test_catches_os_system_fstring(self, write_code):
        filepath = write_code('import os\ndef run(f):\n    os.system(f"rm {f}")')
        issues = check_security(filepath)
        assert any("CMD" in i.rule for i in issues)

    def test_catches_subprocess_fstring(self, write_code):
        filepath = write_code('import subprocess\ndef run(c):\n    subprocess.run(f"echo {c}", shell=True)')
        issues = check_security(filepath)
        assert any("CMD" in i.rule for i in issues)

    def test_passes_safe_subprocess(self, write_code):
        filepath = write_code('import subprocess\nsubprocess.run(["ls", "-l"], shell=False)')
        issues = check_security(filepath)
        assert not any("CMD" in i.rule for i in issues)


class TestSecurityDeserialization:
    """不安全反序列化检测"""

    def test_catches_pickle_loads(self, write_code):
        filepath = write_code('import pickle\ndef load(d):\n    return pickle.loads(d)')
        issues = check_security(filepath)
        assert any("PICKLE" in i.rule for i in issues)

    def test_catches_yaml_load(self, write_code):
        filepath = write_code('import yaml\ndef load(d):\n    return yaml.load(d)')
        issues = check_security(filepath)
        assert any("YAML" in i.rule for i in issues)

    def test_passes_yaml_safe_load(self, write_code):
        filepath = write_code('import yaml\ndef load(d):\n    return yaml.safe_load(d)')
        issues = check_security(filepath)
        assert not any("YAML" in i.rule for i in issues)


class TestSecurityDangerousBuiltins:
    """eval/exec/compile 检测"""

    def test_catches_eval(self, write_code):
        filepath = write_code('def run(e):\n    return eval(e)')
        issues = check_security(filepath)
        assert any("DANGEROUS" in i.rule for i in issues)

    def test_catches_exec(self, write_code):
        filepath = write_code('def run(c):\n    exec(c)')
        issues = check_security(filepath)
        assert any("DANGEROUS" in i.rule for i in issues)


class TestSecurityBareExcept:
    """裸 except 检测"""

    def test_catches_bare_except(self, write_code):
        filepath = write_code('def bad():\n    try:\n        risky()\n    except:\n        pass')
        issues = check_security(filepath)
        assert any("BARE" in i.rule for i in issues)

    def test_passes_typed_except(self, write_code):
        filepath = write_code('def good():\n    try:\n        risky()\n    except ValueError:\n        pass')
        issues = check_security(filepath)
        assert not any("BARE" in i.rule for i in issues)


class TestSecurityXSS:
    """XSS 模式检测"""

    def test_catches_mark_safe(self, write_code):
        filepath = write_code('from django.utils.safestring import mark_safe\nresult = mark_safe(user_input)')
        issues = check_security(filepath)
        assert any("XSS" in i.rule for i in issues)


# ════════════════════════════════════════════════════════════════════
# JS Lint
# ════════════════════════════════════════════════════════════════════

class TestJSLint:
    """JS/TS ESLint 集成"""

    def test_skips_python_files(self):
        issues = check_js_lint("test.py")
        assert issues == []

    def test_skips_markdown_files(self):
        issues = check_js_lint("README.md")
        assert issues == []


# ════════════════════════════════════════════════════════════════════
# 汇总与格式化
# ════════════════════════════════════════════════════════════════════

class TestRunGate:
    """完整门控流程"""

    def test_passes_clean_code(self, write_code):
        filepath = write_code("def clean(x):\n    return x + 1\n")
        result = run_gate(filepath, complexity_threshold=15)
        assert result.passed is True
        assert result.blocker_count == 0

    def test_fails_complex_code(self, write_code):
        filepath = write_code("""
def messy(x):
    if x > 0:
        if x > 10:
            if x > 20:
                if x > 30:
                    if x > 40:
                        return x
    return 0
""")
        result = run_gate(filepath, complexity_threshold=3)
        assert result.passed is False
        assert result.blocker_count >= 1

    def test_fails_security_violation(self, write_code):
        filepath = write_code('password = "supersecret123"')
        result = run_gate(filepath)
        assert result.passed is False
        assert any("HARDCODED" in i.rule for i in result.issues)


class TestFormatGateResult:
    """报告格式化"""

    def test_pass_format(self):
        result = GateResult(passed=True, issues=[], blocker_count=0)
        formatted = format_gate_result(result)
        assert "PASSED" in formatted

    def test_fail_format_shows_blockers(self):
        result = GateResult(passed=False, issues=[
            GateIssue(file="test.py", line=1, rule="SEC-X", severity="blocker",
                      message="bad", evidence="x"),
            GateIssue(file="test.py", line=2, rule="STYLE-Y", severity="warning",
                      message="meh"),
        ], blocker_count=1, warning_count=1)
        formatted = format_gate_result(result)
        assert "FAILED" in formatted
        assert "blocker" in formatted.lower()
        assert "SEC-X" in formatted

    def test_pass_with_warnings(self):
        result = GateResult(passed=True, issues=[
            GateIssue(file="test.py", line=1, rule="WARN", severity="warning", message="ok"),
        ], warning_count=1)
        formatted = format_gate_result(result)
        assert "PASSED" in formatted
        assert "warning" in formatted.lower()


class TestGateConfig:
    """配置文件加载"""

    def test_defaults(self):
        config = GateConfig()
        assert config.cyclomatic_threshold == 15
        assert config.cognitive_threshold == 20
        assert config.max_function_lines == 80
        assert config.max_nesting_depth == 4
        assert config.max_parameters == 5
