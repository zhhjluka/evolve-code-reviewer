"""
CLI 入口 — 代码审查 + 自动进化

用法:
  # 运行静态门控 (Stage 0)
  cra gate examples/sample_bad.py

  # 运行代码进化 (Stage 2 - 核心)
  cra evolve examples/sample_bad.py --test examples/test_sample_bad.py

  # 完整审查 (Stage 0 → Evolve)
  cra review examples/sample_bad.py --test examples/test_sample_bad.py
"""

import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .gate import run_gate, format_gate_result
from .evolver import (
    EvolutionInput,
    EvolutionResult,
    EvolutionReport,
    evolve_code,
    _detect_provider,
    _PRESET_MODELS,
    build_llm_config,
)

app = typer.Typer(help="Code Review Agent — AI-powered code review with auto-evolution")
console = Console()


@app.command()
def gate(
    source: str = typer.Argument(..., help="Source file to check"),
    threshold: int = typer.Option(15, "--threshold", "-t", help="Cyclomatic complexity threshold"),
):
    """Stage 0: Run static gate checks (complexity, security, lint)."""
    path = Path(source)
    if not path.exists():
        console.print(f"[red]File not found: {source}[/red]")
        raise typer.Exit(1)

    result = run_gate(str(path), threshold)

    console.print(format_gate_result(result))

    if not result.passed:
        console.print(f"\n[bold red]{result.blocker_count} blocker(s) found[/bold red]")
        raise typer.Exit(1)


@app.command()
def evolve(
    source: str = typer.Argument(..., help="Source file with EVOLVE-BLOCK markers"),
    test: str = typer.Option(..., "--test", "-t", help="pytest test file for functional correctness"),
    iterations: int = typer.Option(200, "--iterations", "-n", help="OpenEvolve max iterations"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save evolved code to file"),
):
    """
    Stage 2: Evolve code using OpenEvolve.

    Takes a source file with EVOLVE-BLOCK markers and a pytest test file.
    OpenEvolve searches for functionally equivalent code with lower complexity,
    better performance, and improved readability.
    """
    source_path = Path(source).resolve()
    test_path = Path(test).resolve()

    if not source_path.exists():
        console.print(f"[red]Source file not found: {source}[/red]")
        raise typer.Exit(1)
    if not test_path.exists():
        console.print(f"[red]Test file not found: {test}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Evolving: {source_path.name}[/bold]")
    console.print(f"Tests:    {test_path.name}")
    console.print(f"Iterations: {iterations}")

    # 显示 LLM provider 和模型
    provider = _detect_provider()
    models = _PRESET_MODELS[provider]
    console.print(f"LLM:      [cyan]{provider}[/cyan] ({models[0]} + {models[1]})")
    console.print()

    input = EvolutionInput(
        source_file=str(source_path),
        test_file=str(test_path),
        block_name=source_path.stem,
        max_iterations=iterations,
    )

    start = time.time()
    result = evolve_code(input)
    elapsed = time.time() - start

    report = EvolutionReport(results=[result], total_time_s=elapsed)
    console.print(format_evolution_report(report))

    if result.success and result.diff:
        console.print("[bold]Diff:[/bold]")
        console.print(result.diff[:3000])
        if len(result.diff) > 3000:
            console.print(f"\n[dim]... (diff truncated, full length: {len(result.diff)} chars)[/dim]")

    # ─── 输出进化后代码 ───
    if result.success and result.evolved_code:
        if output:
            out_path = Path(output).resolve()
            out_path.write_text(result.evolved_code)
            console.print(f"\n[bold green]💾 Evolved code saved to: {out_path}[/bold green]")
        else:
            console.print(f"\n[bold yellow]💡 Tip: use --output/-o to save evolved code to a file[/bold yellow]")

    if not result.success:
        console.print(f"\n[bold red]Evolution failed: {result.error}[/bold red]")
        raise typer.Exit(1)


@app.command()
def review(
    source: str = typer.Argument(..., help="Source file to review"),
    test: str = typer.Option(..., "--test", "-t", help="pytest test file"),
    threshold: int = typer.Option(15, "--threshold", help="Complexity threshold"),
    iterations: int = typer.Option(200, "--iterations", "-n", help="OpenEvolve iterations"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save evolved code to file"),
    skip_evolve: bool = typer.Option(False, "--skip-evolve", help="Skip OpenEvolve, gate only"),
):
    """
    Full review: Stage 0 (gate) → Stage 2 (evolve).

    First runs static gate checks. If passed, runs OpenEvolve to
    automatically optimize high-complexity code.
    """
    source_path = Path(source).resolve()
    test_path = Path(test).resolve()

    # ─── Stage 0: Static Gate ───
    console.print("[bold cyan]━━━ Stage 0: Static Gate ━━━[/bold cyan]")
    gate_result = run_gate(str(source_path), threshold)
    console.print(format_gate_result(gate_result))
    console.print()

    if not gate_result.passed:
        console.print(f"[bold red]{gate_result.blocker_count} blocker(s) — fix before proceeding[/bold red]")
        console.print("[yellow]Tip: Run 'cra evolve' after fixing blockers.[/yellow]")
        raise typer.Exit(1)

    if skip_evolve:
        console.print("[green]Static gate passed. Skipping evolution (--skip-evolve).[/green]")
        return

    # ─── Stage 2: Code Evolution ───
    console.print("[bold cyan]━━━ Stage 2: Code Evolution ━━━[/bold cyan]")
    console.print(f"Source: {source_path.name}")
    console.print(f"Tests:  {test_path.name}")

    provider = _detect_provider()
    models = _PRESET_MODELS[provider]
    console.print(f"LLM:    [cyan]{provider}[/cyan] ({models[0]} + {models[1]})")
    console.print()

    start = time.time()
    result = evolve_code(EvolutionInput(
        source_file=str(source_path),
        test_file=str(test_path),
        max_iterations=iterations,
    ))
    elapsed = time.time() - start

    report = EvolutionReport(results=[result], total_time_s=elapsed)
    console.print(format_evolution_report(report))

    if result.success:
        console.print("[bold green]✅ Evolution complete![/bold green]")

        if output:
            out_path = Path(output).resolve()
            out_path.write_text(result.evolved_code)
            console.print(f"[bold green]💾 Evolved code saved to: {out_path}[/bold green]")
        else:
            console.print("[bold yellow]💡 Tip: use --output/-o to save evolved code to a file[/bold yellow]")
    else:
        console.print(f"[bold red]❌ Evolution failed: {result.error}[/bold red]")
        raise typer.Exit(1)


@app.command()
def bench(
    source: str = typer.Argument(..., help="Source file with EVOLVE-BLOCK markers"),
    test: str = typer.Option(..., "--test", "-t", help="pytest test file"),
    iterations: int = typer.Option(200, "--iterations", "-n", help="OpenEvolve iterations"),
    output_dir: str = typer.Option("bench_results", "--output-dir", "-d", help="Bench results directory"),
):
    """
    Run evolution benchmark and save detailed metrics as JSON.

    Outputs a JSON file in --output-dir with:
    - Before/after complexity (max + avg + per-function)
    - Before/after performance (median/mean/p95)
    - Before/after line count
    - Diff, elapsed time, and cost estimate
    """
    from .bench import run_bench, save_bench

    console.print(f"[bold]Benchmarking: {Path(source).name}[/bold]")
    console.print(f"Tests:         {Path(test).name}")
    console.print(f"Iterations:    {iterations}")
    provider = _detect_provider()
    models = _PRESET_MODELS[provider]
    console.print(f"LLM:           [cyan]{provider}[/cyan] ({models[0]} + {models[1]})")
    console.print()

    bench_data = run_bench(source, test, iterations)
    filepath = save_bench(bench_data, output_dir)

    s = bench_data["summary"]
    console.print("[bold green]✅ Benchmark complete![/bold green]")
    console.print(f"   Success:       {'✅' if s['success'] else '❌'}")
    if s["success"]:
        console.print(f"   Complexity:    {s['complexity_change']:+.1f}")
        console.print(f"   Lines:         {s['lines_change']:+d}")
        if s["perf_change_pct"] is not None:
            console.print(f"   Perf:          {s['perf_change_pct']:+.1f}%")
        console.print(f"   Cost:          ~${s['estimated_cost_usd']:.2f}")
    console.print(f"   Time:          {s['elapsed_s']:.1f}s")
    console.print(f"\n📄 Results saved to: {filepath}")


@app.command()
def diff(
    source: str = typer.Argument(..., help="Original file"),
    evolved: str = typer.Argument(..., help="Evolved file (from --output)"),
):
    """
    Show a side-by-side diff between original and evolved code.
    """
    from difflib import unified_diff

    src_path = Path(source).resolve()
    evo_path = Path(evolved).resolve()

    if not src_path.exists():
        console.print(f"[red]Original file not found: {source}[/red]")
        raise typer.Exit(1)
    if not evo_path.exists():
        console.print(f"[red]Evolved file not found: {evolved}[/red]")
        raise typer.Exit(1)

    src_lines = src_path.read_text().splitlines()
    evo_lines = evo_path.read_text().splitlines()

    diff_output = "\n".join(unified_diff(
        src_lines, evo_lines,
        fromfile=f"a/{src_path.name}",
        tofile=f"b/{evo_path.name}",
        lineterm="",
    ))

    if diff_output:
        console.print("[bold]Diff:[/bold]")
        console.print(diff_output)
    else:
        console.print("[yellow]No differences found.[/yellow]")


if __name__ == "__main__":
    app()
