"""
Code Evolver — 基于 OpenEvolve 的代码自动进化引擎。

核心流程：
1. 接收"可自动优化"的代码问题（高复杂度、性能差、可读性差）
2. 调用 OpenEvolve 对目标代码进行进化搜索
3. 功能正确性测试作为硬门控
4. 输出进化后代码 + 前后对比

LLM 配置（通过环境变量）：
  CRA_MODEL              主模型名 (default: gemini-2.5-flash)
  CRA_MODEL_SECONDARY     辅助模型名 (default: gemini-2.5-pro)
  CRA_API_KEY             API Key（自动从 *_API_KEY 获取或手动设置）
  CRA_API_BASE            API Base URL（自动推断或手动设置）

内置预设：
  gemini → GEMINI_API_KEY, base=https://generativelanguage.googleapis.com/v1beta/openai/
  gpt    → OPENAI_API_KEY, base=https://api.openai.com/v1
  deepseek → DEEPSEEK_API_KEY, base=https://api.deepseek.com
  ollama → OLLAMA_API_KEY (可为空), base=http://localhost:11434/v1

这是整个系统的差异化核心：不只告诉你"代码写得不好"，
更直接给你一个功能等价但质量更好的版本。
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class EvolutionInput:
    """一次进化任务的输入"""
    source_file: str        # 含 EVOLVE-BLOCK 标记的源文件路径
    test_file: str          # pytest 功能正确性测试文件路径
    block_name: str         # 要进化的函数名（用于日志标识）
    max_iterations: int = 200


@dataclass
class EvolutionResult:
    """一次进化任务的输出"""
    success: bool
    original_complexity: float
    evolved_complexity: float
    original_lines: int
    evolved_lines: int
    original_perf_ms: float     # 原始代码平均执行时间 (ms)
    evolved_perf_ms: float      # 进化后代码平均执行时间 (ms)
    diff: str = ""
    evolved_code: str = ""
    error: str = ""


@dataclass
class EvolutionReport:
    """完整进化报告"""
    results: list[EvolutionResult] = field(default_factory=list)
    total_time_s: float = 0.0


def _extract_block(source: str, marker_start: str = "# EVOLVE-BLOCK-START",
                   marker_end: str = "# EVOLVE-BLOCK-END") -> str:
    """从源文件中提取 EVOLVE-BLOCK 标记之间的代码"""
    lines = source.split("\n")
    in_block = False
    block_lines = []
    for line in lines:
        if marker_start in line:
            in_block = True
            continue
        if marker_end in line:
            in_block = False
            continue
        if in_block:
            block_lines.append(line)
    return "\n".join(block_lines)


def _replace_block(source: str, new_code: str,
                   marker_start: str = "# EVOLVE-BLOCK-START",
                   marker_end: str = "# EVOLVE-BLOCK-END") -> str:
    """将进化后的代码替换回源文件中的 EVOLVE-BLOCK 区域"""
    lines = source.split("\n")
    result = []
    in_block = False
    replaced = False
    for line in lines:
        if marker_start in line:
            result.append(line)
            result.append(new_code)
            in_block = True
            continue
        if marker_end in line:
            in_block = False
            replaced = False
            result.append(line)
            continue
        if not in_block:
            result.append(line)
    return "\n".join(result)


def _measure_complexity(source: str) -> float:
    """测量代码的圈复杂度（取所有函数的最大值）"""
    try:
        import radon.complexity as rcomp
        from radon.visitors import ComplexityVisitor
    except ImportError:
        return -1.0

    visitor = ComplexityVisitor.from_code(source)
    if not visitor.functions:
        return 1.0
    return max(f.complexity for f in visitor.functions)


def _measure_lines(source: str) -> int:
    """计算代码行数（去除空行和注释行）"""
    lines = [l for l in source.split("\n") if l.strip() and not l.strip().startswith("#")]
    return len(lines)


def _measure_performance(test_file: str, iterations: int = 100) -> float:
    """运行 pytest benchmark 测量执行时间（毫秒）"""
    start = time.perf_counter()
    for _ in range(iterations):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-q", "--no-header", "--tb=no"],
            capture_output=True, text=True,
            cwd=str(Path(test_file).parent),
        )
    elapsed = time.perf_counter() - start
    return (elapsed / iterations) * 1000  # ms per run


def _run_functional_tests(test_file: str) -> tuple[bool, str]:
    """运行功能正确性测试，返回 (通过/失败, 输出)"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd=str(Path(test_file).parent),
    )
    return result.returncode == 0, result.stdout + result.stderr


# ─── LLM 配置 ────────────────────────────────────────────────────────

# 内置 provider 预设
_LLM_PRESETS = {
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    "gpt": {
        "api_key_env": "OPENAI_API_KEY",
        "api_base": "https://api.openai.com/v1",
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_base": "https://api.deepseek.com",
    },
    "ollama": {
        "api_key_env": "OLLAMA_API_KEY",
        "api_base": "http://localhost:11434/v1",
    },
}

# 推荐模型（主模型: 便宜快速 / 辅助模型: 更强推理）
_PRESET_MODELS = {
    "gemini": ("gemini-2.5-flash", "gemini-2.5-pro"),
    "gpt": ("gpt-4o-mini", "gpt-4o"),
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
    "ollama": ("llama3.2", "llama3.2"),
}


def _detect_provider() -> str:
    """从环境变量自动检测 LLM provider"""
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OLLAMA_API_KEY") is not None:  # 可以为空字符串
        return "ollama"
    return "gemini"  # fallback


def build_llm_config() -> dict:
    """
    构建 OpenEvolve LLM 配置。

    优先级: CRA_MODEL / CRA_API_KEY / CRA_API_BASE 环境变量 > provider 预设。
    """
    provider = os.getenv("CRA_PROVIDER") or _detect_provider()
    primary = os.getenv("CRA_MODEL") or _PRESET_MODELS[provider][0]
    secondary = os.getenv("CRA_MODEL_SECONDARY") or _PRESET_MODELS[provider][1]

    # API key: CRA_API_KEY > provider 特定 > 通用
    api_key = (
        os.getenv("CRA_API_KEY") or
        os.getenv(_LLM_PRESETS[provider]["api_key_env"]) or
        os.getenv("OPENAI_API_KEY", "")
    )

    api_base = os.getenv("CRA_API_BASE") or _LLM_PRESETS[provider]["api_base"]
    temperature = float(os.getenv("CRA_TEMPERATURE", "0.7"))

    # 写入环境变量供 OpenEvolve/litellm 使用
    os.environ["OPENAI_API_KEY"] = api_key

    return {
        "models": [
            {"name": primary, "weight": 0.6},
            {"name": secondary, "weight": 0.4},
        ],
        "temperature": temperature,
        "api_base": api_base,
    }


def evolve_code(input: EvolutionInput) -> EvolutionResult:
    """
    对目标代码运行 OpenEvolve 进化搜索。

    评估器设计：
    - 功能正确性：硬门控（不通过直接淘汰）
    - 圈复杂度：越低越好
    - 性能：越快越好
    - 产物侧信道：错误信息、profiling 数据反馈给 LLM
    """
    source_path = Path(input.source_file)
    test_path = Path(input.test_file)

    if not source_path.exists():
        return EvolutionResult(
            success=False,
            original_complexity=0, evolved_complexity=0,
            original_lines=0, evolved_lines=0,
            original_perf_ms=0.0, evolved_perf_ms=0.0,
            error=f"Source file not found: {input.source_file}"
        )

    # 读取原始代码
    original_source = source_path.read_text()
    block_code = _extract_block(original_source)

    # 测量原始指标
    original_complexity = _measure_complexity(original_source)
    original_lines = _measure_lines(original_source)
    original_perf = _measure_performance(str(test_path))

    # 创建临时工作目录
    work_dir = Path(tempfile.mkdtemp(prefix="cra_evolve_"))
    evolved_file = work_dir / source_path.name

    # 复制测试文件到工作目录
    test_dest = work_dir / test_path.name
    shutil.copy(test_path, test_dest)

    # 如果有 conftest.py，也复制
    conftest = test_path.parent / "conftest.py"
    if conftest.exists():
        shutil.copy(conftest, work_dir / "conftest.py")

    try:
        # 保存初始程序
        initial_code = original_source
        evolved_file.write_text(initial_code)

        # ─── 评估函数（供 OpenEvolve 调用）───
        def evaluate(program_file: str):
            """OpenEvolve 评估器"""
            from openevolve import EvaluationResult as EvalResult

            code = Path(program_file).read_text()

            # 硬门控：功能正确性测试
            passed, output = _run_functional_tests(str(test_dest))
            if not passed:
                return EvalResult(
                    metrics={"complexity": -999.0, "performance": 0.0, "lines": 999},
                    artifacts={"stderr": output[-500:], "test_failed": True},
                )

            # 测量指标
            complexity = _measure_complexity(code)
            lines = _measure_lines(code)
            perf = _measure_performance(str(test_dest), iterations=10)

            return EvalResult(
                metrics={
                    "complexity": -complexity,  # 负值（MAP-Elites 做最大化）
                    "performance": -perf,       # 负值（越小越好）
                    "lines": lines,
                },
                artifacts={
                    "profiling_data": f"perf={perf:.2f}ms, complexity={complexity}",
                    "test_output": output[-300:],
                },
            )

        # ─── 运行 OpenEvolve ───
        from openevolve import OpenEvolve

        llm_config = build_llm_config()
        evolver = OpenEvolve(
            initial_program_path=str(evolved_file),
            evaluation_file=str(test_dest),
            config={
                "max_iterations": input.max_iterations,
                "random_seed": 42,
                "llm": llm_config,
                "database": {
                    "population_size": 60,
                    "num_islands": 4,
                    "exploitation_ratio": 0.7,
                    "feature_dimensions": ["complexity", "performance", "lines"],
                    "feature_bins": {
                        "complexity": 10,
                        "performance": 10,
                        "lines": 5,
                    },
                    "migration_interval": 10,
                },
                "evaluator": {
                    "enable_artifacts": True,
                    "cascade_evaluation": False,
                },
                "prompt": {
                    "num_top_programs": 3,
                    "num_diverse_programs": 2,
                    "include_artifacts": True,
                },
            }
        )

        import asyncio
        best_program = asyncio.run(evolver.run())

        # 读取进化后的代码
        evolved_source = Path(str(best_program)).read_text() if best_program else initial_code

        # 测量进化后指标
        evolved_complexity = _measure_complexity(evolved_source)
        evolved_lines = _measure_lines(evolved_source)
        evolved_perf = _measure_performance(str(test_dest), iterations=10)

        # 生成 diff
        import difflib
        diff = "\n".join(difflib.unified_diff(
            original_source.splitlines(),
            evolved_source.splitlines(),
            fromfile=f"a/{input.source_file}",
            tofile=f"b/{input.source_file}",
            lineterm="",
        ))

        return EvolutionResult(
            success=True,
            original_complexity=original_complexity,
            evolved_complexity=evolved_complexity,
            original_lines=original_lines,
            evolved_lines=evolved_lines,
            original_perf_ms=original_perf,
            evolved_perf_ms=evolved_perf,
            diff=diff,
            evolved_code=evolved_source,
        )

    except Exception as e:
        return EvolutionResult(
            success=False,
            original_complexity=original_complexity,
            evolved_complexity=0,
            original_lines=original_lines,
            evolved_lines=0,
            original_perf_ms=original_perf,
            evolved_perf_ms=0.0,
            error=f"Evolution failed: {str(e)}",
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def format_evolution_report(report: EvolutionReport) -> str:
    """格式化进化报告为可读文本"""
    lines = ["=" * 60, "  📊 Code Evolution Report", "=" * 60, ""]

    for i, result in enumerate(report.results, 1):
        lines.append(f"--- Result #{i} ---")
        if not result.success:
            lines.append(f"  ❌ FAILED: {result.error}")
            lines.append("")
            continue

        # 复杂度变化
        comp_delta = result.evolved_complexity - result.original_complexity
        comp_arrow = "⬆️" if comp_delta > 0 else "⬇️"
        lines.append(f"  Complexity: {result.original_complexity:.1f} → {result.evolved_complexity:.1f} ({comp_arrow} {abs(comp_delta):.1f})")

        # 行数变化
        line_delta = result.evolved_lines - result.original_lines
        line_arrow = "⬆️" if line_delta > 0 else "⬇️"
        lines.append(f"  Lines:      {result.original_lines} → {result.evolved_lines} ({line_arrow} {abs(line_delta)})")

        # 性能变化
        if result.original_perf_ms > 0 and result.evolved_perf_ms > 0:
            perf_change = ((result.evolved_perf_ms - result.original_perf_ms) / result.original_perf_ms) * 100
            perf_arrow = "⬆️ faster" if perf_change < 0 else "⬇️ slower"
            lines.append(f"  Perf:       {result.original_perf_ms:.2f}ms → {result.evolved_perf_ms:.2f}ms ({perf_arrow} {abs(perf_change):.1f}%)")

        lines.append("")

    lines.append(f"Total time: {report.total_time_s:.1f}s")
    return "\n".join(lines)
