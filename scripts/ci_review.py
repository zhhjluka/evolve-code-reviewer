#!/usr/bin/env python3
"""
GitHub Actions CI 审查脚本。

在 CI 流水线中被调用：
1. 获取 PR 变更的文件列表
2. 过滤排除规则
3. 对有映射的改动用 cra review（门控 + 进化），无映射的只做 gate
4. 生成审查报告，输出到 GITHUB_STEP_SUMMARY + PR comment

用法:
  python scripts/ci_review.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(os.getenv("GITHUB_WORKSPACE", Path(__file__).resolve().parent.parent))

# ─── 工具函数 ──────────────────────────────────────────────────────

def load_config() -> dict:
    """加载 .code-review.yaml"""
    config_path = REPO_ROOT / ".code-review.yaml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def get_changed_files() -> list[str]:
    """获取 PR 变更的 Python 文件列表"""
    # GitHub Actions 中，base ref 在 GITHUB_BASE_REF 环境变量中
    base_ref = os.getenv("GITHUB_BASE_REF", "main")

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
            capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError:
        # fallback: 和上一个 commit 比较
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )

    return [f.strip() for f in result.stdout.split("\n") if f.strip().endswith(".py")]


def should_exclude(filepath: str, exclude_patterns: list[str]) -> bool:
    """检查文件是否应该被排除"""
    from fnmatch import fnmatch
    for pattern in exclude_patterns:
        if fnmatch(filepath, pattern):
            return True
    return False


def run_gate(filepath: str, threshold: int) -> tuple[bool, str]:
    """运行静态门控"""
    result = subprocess.run(
        [sys.executable, "-m", "cra", "gate", str(REPO_ROOT / filepath), "--threshold", str(threshold)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return result.returncode == 0, result.stdout


def run_evolve(filepath: str, testpath: str, iterations: int, output: str, timeout: int) -> tuple[bool, str]:
    """运行代码进化"""
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "cra", "evolve",
                str(REPO_ROOT / filepath),
                "--test", str(REPO_ROOT / testpath),
                "--iterations", str(iterations),
                "--output", str(output),
            ],
            capture_output=True, text=True,
            timeout=timeout * 60,
            cwd=REPO_ROOT,
        )
        return result.returncode == 0, result.stdout
    except subprocess.TimeoutExpired:
        return False, f"⏰ Evolution timed out after {timeout} minutes"


def post_pr_comment(body: str):
    """通过 GitHub API 贴 PR comment"""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("⚠️  GITHUB_TOKEN not set, skipping PR comment")
        return

    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        return

    with open(event_path) as f:
        event = json.load(f)

    # 确定是 PR 还是 push
    if "pull_request" in event:
        issue_url = event["pull_request"]["_links"]["comments"]["href"]
    else:
        print("Not a PR event, skipping comment")
        return

    import urllib.request
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(issue_url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    urllib.request.urlopen(req)


# ─── 主流程 ─────────────────────────────────────────────────────────

def main():
    config = load_config()

    gate_cfg = config.get("gate", {})
    evolve_cfg = config.get("evolve", {})
    file_mapping = config.get("file_mapping", {})
    exclude_patterns = config.get("exclude", {}).get("paths", [])

    complexity_threshold = gate_cfg.get("complexity_threshold", 15)
    evolve_enabled = evolve_cfg.get("enabled", True)
    evolve_iterations = evolve_cfg.get("iterations", 100)
    evolve_timeout = evolve_cfg.get("timeout_minutes", 10)

    # 1. 获取变更文件
    changed = get_changed_files()
    if not changed:
        print("✅ No Python files changed.")
        return

    # 2. 过滤
    to_review = [f for f in changed if not should_exclude(f, exclude_patterns)]
    print(f"Changed Python files: {len(changed)}, after exclude: {len(to_review)}")

    # 3. 逐文件审查
    gate_failures = 0
    evolve_results = []
    report_lines = [
        "## 🤖 Code Review Agent Report",
        "",
        f"**审查文件数**: {len(to_review)} | **复杂度阈值**: {complexity_threshold}",
        "",
    ]

    for filepath in to_review:
        print(f"\n{'='*60}")
        print(f"Reviewing: {filepath}")

        # Stage 0: 静态门控
        gate_ok, gate_output = run_gate(filepath, complexity_threshold)

        if not gate_ok:
            gate_failures += 1
            report_lines.append(f"### 🔴 {filepath} — Stage 0 FAILED")
            report_lines.append("```")
            report_lines.append(gate_output.strip())
            report_lines.append("```")
            report_lines.append("")
            continue

        report_lines.append(f"### ✅ {filepath} — Stage 0 PASSED")

        # Stage 2: 代码进化（如果有测试映射）
        if evolve_enabled and filepath in file_mapping:
            test_path = file_mapping[filepath]
            if (REPO_ROOT / test_path).exists():
                output_file = str(REPO_ROOT / f"{filepath}.evolved.py")
                print(f"  Evolving: {filepath} (test: {test_path})")

                ok, output = run_evolve(filepath, test_path, evolve_iterations, output_file, evolve_timeout)
                if ok:
                    report_lines.append(f"  📊 进化完成 → `{output_file}`")
                    # 提取关键指标
                    for line in output.split("\n"):
                        if "Complexity:" in line or "Perf:" in line or "Lines:" in line:
                            report_lines.append(f"  {line.strip()}")
                    evolve_results.append((filepath, True))
                else:
                    report_lines.append(f"  ⚠️ 进化失败")
                    evolve_results.append((filepath, False))
            else:
                report_lines.append(f"  ⚠️ 测试文件 `{test_path}` 不存在，跳过进化")
        else:
            report_lines.append("  ℹ️  无测试映射，仅门控")
            if not evolve_enabled:
                report_lines.append("  ℹ️  进化已禁用 (evolve.enabled=false)")

        report_lines.append("")

    # 4. 汇总
    report_lines.append("---")
    report_lines.append(f"**结果**: {len(to_review)} 文件审查完成")
    if gate_failures > 0:
        report_lines.append(f"- 🔴 {gate_failures} 个文件门控未通过")
    if evolve_results:
        evolved = sum(1 for _, ok in evolve_results if ok)
        report_lines.append(f"- 📊 {evolved}/{len(evolve_results)} 个文件进化成功")
    report_lines.append("")

    if gate_failures > 0:
        report_lines.append("> ⚠️ 请修复以上 🔴 项后再合并。")

    report = "\n".join(report_lines)

    # 5. 输出
    print("\n" + "=" * 60)
    print(report)

    # 写入 GitHub Step Summary
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(report)

    # 贴 PR comment
    post_pr_comment(report)

    # 6. 退出码：有门控失败 → 阻塞 CI
    if gate_failures > 0:
        print(f"\n❌ {gate_failures} gate failure(s) — blocking merge")
        sys.exit(1)


if __name__ == "__main__":
    main()
