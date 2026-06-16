"""TDD: Bench 模块测试 — JSON 序列化 + 性能计算"""
import json
import tempfile
from pathlib import Path

import pytest
from cra.bench import _result_to_dict, _calc_perf_change, save_bench
from cra.evolver import EvolutionResult


class TestResultToDict:
    """EvolutionResult → JSON 序列化"""

    @pytest.fixture
    def success_result(self):
        return EvolutionResult(
            success=True,
            original_complexity=20,
            evolved_complexity=8,
            original_complexity_detail={"max": 20, "avg": 12.5, "functions": [
                {"name": "foo", "complexity": 20, "line": 10}
            ]},
            evolved_complexity_detail={"max": 8, "avg": 4.2, "functions": [
                {"name": "foo_v2", "complexity": 8, "line": 10}
            ]},
            original_lines=105, evolved_lines=72,
            original_perf={"median_ms": 3.0, "mean_ms": 3.2, "p95_ms": 4.0},
            evolved_perf={"median_ms": 2.0, "mean_ms": 2.1, "p95_ms": 2.5},
            diff="--- a/file\n+++ b/file\n-line\n+new_line",
            elapsed_s=120, estimated_cost_usd=0.50,
        )

    def test_serializable(self, success_result):
        d = _result_to_dict(success_result)
        json_str = json.dumps(d)
        assert "success" in json_str
        assert "20" in json_str
        assert "8" in json_str

    def test_diff_truncated(self):
        long_diff = "x" * 10000
        result = EvolutionResult(
            success=True, original_complexity=1, evolved_complexity=1,
            diff=long_diff,
        )
        d = _result_to_dict(result)
        assert len(d["diff"]) <= 5000

    def test_failure_result(self):
        result = EvolutionResult(
            success=False, original_complexity=0, evolved_complexity=0,
            error="API error",
        )
        d = _result_to_dict(result)
        assert d["success"] is False
        assert d["error"] == "API error"


class TestPerfChange:
    """性能变化百分比计算"""

    def test_positive_improvement(self):
        result = EvolutionResult(
            success=True, original_complexity=1, evolved_complexity=1,
            original_perf={"median_ms": 10.0},
            evolved_perf={"median_ms": 6.0},
        )
        change = _calc_perf_change(result)
        assert change == -40.0  # 40% faster

    def test_no_change(self):
        result = EvolutionResult(
            success=True, original_complexity=1, evolved_complexity=1,
            original_perf={"median_ms": 5.0},
            evolved_perf={"median_ms": 5.0},
        )
        change = _calc_perf_change(result)
        assert change == 0.0

    def test_failure_returns_none(self):
        result = EvolutionResult(
            success=False, original_complexity=0, evolved_complexity=0,
        )
        assert _calc_perf_change(result) is None

    def test_missing_perf_returns_none(self):
        result = EvolutionResult(
            success=True, original_complexity=1, evolved_complexity=1,
        )
        assert _calc_perf_change(result) is None


class TestSaveBench:
    """JSON 保存"""

    def test_saves_to_file(self):
        bench_data = {
            "bench_id": "20260616_test",
            "name": "test_func",
            "source": "test.py",
            "test": "test_test.py",
            "iterations": 50,
            "summary": {"success": True},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = save_bench(bench_data, tmpdir)
            assert filepath.exists()
            content = json.loads(filepath.read_text())
            assert content["bench_id"] == "20260616_test"
            assert content["summary"]["success"] is True
