"""
Bench — 进化基准测试，将结果持久化为 JSON 供分析。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .evolver import (
    EvolutionInput,
    EvolutionReport,
    EvolutionResult,
    evolve_code,
)


def run_bench(
    source: str,
    test: str,
    iterations: int = 200,
    name: Optional[str] = None,
) -> dict:
    """
    运行一次完整的进化基准测试，返回结构化 JSON 数据。

    输出格式:
    {
      "bench_id": "2026-06-16_001",
      "name": "sample_bad",
      "source": "examples/sample_bad.py",
      "test": "examples/test_sample_bad.py",
      "iterations": 200,
      "result": { ... EvolutionResult as dict ... },
      "config": { ... OpenEvolve config ... },
      "timestamp": "2026-06-16T12:00:00"
    }
    """
    input = EvolutionInput(
        source_file=str(Path(source).resolve()),
        test_file=str(Path(test).resolve()),
        block_name=name or Path(source).stem,
        max_iterations=iterations,
    )

    start = time.time()
    result = evolve_code(input)
    elapsed = time.time() - start

    bench_data = {
        "bench_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "name": name or Path(source).stem,
        "source": source,
        "test": test,
        "iterations": iterations,
        "timestamp": datetime.now().isoformat(),
        "result": _result_to_dict(result),
        "summary": {
            "success": result.success,
            "complexity_change": (
                result.evolved_complexity - result.original_complexity
                if result.success else 0
            ),
            "lines_change": (
                result.evolved_lines - result.original_lines
                if result.success else 0
            ),
            "perf_change_pct": _calc_perf_change(result),
            "elapsed_s": elapsed,
            "estimated_cost_usd": result.estimated_cost_usd,
        },
    }

    return bench_data


def save_bench(bench_data: dict, output_dir: str = "bench_results") -> Path:
    """保存基准测试结果到 JSON 文件"""
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)

    filename = f"{bench_data['bench_id']}_{bench_data['name']}.json"
    filepath = out_dir / filename

    with open(filepath, "w") as f:
        json.dump(bench_data, f, indent=2, ensure_ascii=False, default=str)

    return filepath


def _result_to_dict(result: EvolutionResult) -> dict:
    """将 EvolutionResult 转为可序列化的 dict"""
    return {
        "success": result.success,
        "original_complexity": result.original_complexity,
        "evolved_complexity": result.evolved_complexity,
        "original_complexity_detail": result.original_complexity_detail,
        "evolved_complexity_detail": result.evolved_complexity_detail,
        "original_lines": result.original_lines,
        "evolved_lines": result.evolved_lines,
        "original_perf": result.original_perf,
        "evolved_perf": result.evolved_perf,
        "diff": result.diff[:5000] if len(result.diff) > 5000 else result.diff,  # 截断
        "elapsed_s": result.elapsed_s,
        "estimated_cost_usd": result.estimated_cost_usd,
        "error": result.error,
    }


def _calc_perf_change(result: EvolutionResult) -> Optional[float]:
    """计算性能变化百分比（负数 = 更快）"""
    if not result.success or not result.original_perf or not result.evolved_perf:
        return None
    orig = result.original_perf.get("median_ms", 0)
    evo = result.evolved_perf.get("median_ms", 0)
    if orig <= 0 or evo <= 0:
        return None
    return ((evo - orig) / orig) * 100
