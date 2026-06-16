"""TDD: Evolver 模块测试 — 测量函数 + 代码提取/替换

注意: evolve_code 本身调用 OpenEvolve + LLM API，不在此测试。
"""
import pytest
from pathlib import Path
from cra.evolver import (
    _extract_block,
    _replace_block,
    _measure_complexity,
    _measure_complexity_detail,
    _measure_lines,
    _measure_performance,
    EvolutionResult,
    EvolutionReport,
    format_evolution_report,
)


class TestExtractBlock:
    """EVOLVE-BLOCK 标记提取/替换"""

    def test_extract_single_block(self):
        src = """
import stuff

# EVOLVE-BLOCK-START
def target():
    return 42
# EVOLVE-BLOCK-END

def other():
    pass
"""
        block = _extract_block(src)
        assert "def target():" in block
        assert "def other():" not in block
        assert "import stuff" not in block

    def test_extract_multiple_blocks(self):
        src = """
# EVOLVE-BLOCK-START
def first():
    return 1
# EVOLVE-BLOCK-END

middle code

# EVOLVE-BLOCK-START
def second():
    return 2
# EVOLVE-BLOCK-END
"""
        block = _extract_block(src)
        assert "def first():" in block
        assert "def second():" in block
        assert "middle code" not in block

    def test_no_block_returns_empty(self):
        src = "def simple():\n    return 1\n"
        assert _extract_block(src) == ""

    def test_replace_block(self):
        src = """
PREFIX

# EVOLVE-BLOCK-START
old code
# EVOLVE-BLOCK-END

SUFFIX
"""
        new_code = "\nnew code\n"
        result = _replace_block(src, new_code)
        assert "PREFIX" in result
        assert "old code" not in result
        assert "new code" in result
        assert "SUFFIX" in result


class TestMeasureComplexity:
    """复杂度测量"""

    def test_simple_function(self, write_code):
        filepath = write_code("def simple(x):\n    return x + 1\n")
        complexity = _measure_complexity(Path(filepath).read_text())
        assert complexity == 1.0  # cyclomatic complexity = 1

    def test_if_statement(self, write_code):
        filepath = write_code("def has_if(x):\n    if x > 0:\n        return 1\n    return 0\n")
        complexity = _measure_complexity(Path(filepath).read_text())
        assert complexity == 2.0  # base 1 + 1 if = 2

    def test_nested_ifs(self, write_code):
        filepath = write_code("""
def nested(x, y):
    if x > 0:
        if y > 0:
            return x + y
    return 0
""")
        complexity = _measure_complexity(Path(filepath).read_text())
        assert complexity == 3.0  # base 1 + 2 ifs = 3


class TestMeasureComplexityDetail:
    """详细复杂度报告"""

    def test_reports_per_function(self, write_code):
        filepath = write_code("""
def add(a, b):
    return a + b

def max_of_two(a, b):
    if a > b:
        return a
    return b
""")
        detail = _measure_complexity_detail(Path(filepath).read_text())
        assert detail["max"] == 2.0
        assert detail["avg"] == 1.5
        assert len(detail["functions"]) == 2
        names = [f["name"] for f in detail["functions"]]
        assert "add" in names
        assert "max_of_two" in names


class TestMeasureLines:
    """行数统计"""

    def test_counts_effective_lines(self):
        code = """
# comment line

def foo():
    "docstring"
    x = 1
    return x

"""
        lines = _measure_lines(code)
        # def foo(): + x = 1 + return x = 3 (docstring is not a comment, it stays)
        assert lines >= 2


class TestEvolutionResult:
    """数据结构"""

    def test_success_result(self):
        result = EvolutionResult(
            success=True, original_complexity=20, evolved_complexity=8,
            original_lines=105, evolved_lines=72,
            original_perf={"median_ms": 3.0, "mean_ms": 3.2, "p95_ms": 4.0},
            evolved_perf={"median_ms": 2.0, "mean_ms": 2.1, "p95_ms": 2.5},
            elapsed_s=287, estimated_cost_usd=0.85,
        )
        assert result.success is True
        assert result.original_complexity == 20
        assert result.evolved_complexity == 8

    def test_failure_result(self):
        result = EvolutionResult(
            success=False, original_complexity=15, evolved_complexity=0,
            error="Something went wrong",
        )
        assert result.success is False
        assert "wrong" in result.error


class TestFormatEvolutionReport:
    """报告格式化"""

    def test_formats_success_report(self):
        result = EvolutionResult(
            success=True, original_complexity=20, evolved_complexity=8,
            original_complexity_detail={"max": 20, "avg": 12.5, "functions": []},
            evolved_complexity_detail={"max": 8, "avg": 4.2, "functions": []},
            original_lines=105, evolved_lines=72,
            original_perf={"median_ms": 3.42, "mean_ms": 3.5, "p95_ms": 4.0},
            evolved_perf={"median_ms": 2.15, "mean_ms": 2.2, "p95_ms": 2.8},
            elapsed_s=287, estimated_cost_usd=0.85,
        )
        report = EvolutionReport(results=[result], total_time_s=287)
        formatted = format_evolution_report(report)
        assert "20.0" in formatted
        assert "8.0" in formatted
        assert "105" in formatted
        assert "72" in formatted
        assert "37.1%" in formatted  # perf improvement
        assert "$0.85" in formatted

    def test_formats_failure_report(self):
        result = EvolutionResult(
            success=False, original_complexity=15, evolved_complexity=0,
            error="API rate limit exceeded",
        )
        report = EvolutionReport(results=[result], total_time_s=30)
        formatted = format_evolution_report(report)
        assert "FAILED" in formatted
        assert "rate limit" in formatted
