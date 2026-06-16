# Evolve Code Reviewer v1.0

> 智能代码审查 + OpenEvolve 自动进化 — 不只告诉你代码有问题，更自动修复。

| |  |
|---|---|
| **版本** | 1.0.0 |
| **测试** | 124 tests ✅ |
| **Python** | 3.10+ |
| **许可** | MIT |

---

## 快速开始

```bash
# 安装
pip install -e ".[dev]"

# 配置 LLM（任选一个）
export GEMINI_API_KEY="..."    # Gemini（推荐，便宜）
export DEEPSEEK_API_KEY="..."  # DeepSeek（国内推荐）
export OPENAI_API_KEY="sk-..." # OpenAI

# 静态检查（不调 LLM，秒级）
cra gate examples/sample_bad.py

# 代码进化（OpenEvolve 自动优化）
cra evolve examples/sample_bad.py -t examples/test_sample_bad.py -o optimized.py

# 完整审查（门控 + Agent + 进化）
cra review examples/sample_bad.py -t examples/test_sample_bad.py -o optimized.py
```

---

## 命令一览

| 命令 | 功能 | LLM | 耗时 |
|------|------|-----|------|
| `cra gate` | 静态门控（复杂度/安全/lint） | ❌ | <2s |
| `cra evolve` | OpenEvolve 代码进化 | ✅ | 3-5min |
| `cra review` | Gate → Evolve 完整流程 | ✅ | 3-5min |
| `cra bench` | 进化基准测试（保存 JSON 指标） | ✅ | 3-5min |
| `cra diff` | 原始 vs 进化后对比 | ❌ | <1s |

---

## 系统架构

```
PR 提交
  │
  ▼
Stage 0: 静态门控（<2s，纯规则）
  ├── 19 条安全规则（SQL注入/命令注入/密钥/反序列化/XSS）
  ├── 5 项复杂度度量（圈/认知/嵌套/行数/参数）
  └── 🔴 阻断 → PR 不可合并
  │
  ▼
审查 Agent（5 个并行 LLM 调用）
  ├── Security Reviewer  → 🔴 安全问题（需人工判断）
  ├── Complexity Reviewer → 🤖 复杂度问题（可自动优化）
  ├── Performance Reviewer→ 🤖 性能问题（可自动优化）
  ├── Readability Reviewer→ 🤖 可读性问题（可自动优化）
  └── Style Reviewer      → 🤖 风格问题（自动修复）
  │
  ▼
问题分类器 → auto_fixable / needs_human
  │
  ├── needs_human → 传统修复建议
  └── auto_fixable → OpenEvolve 进化引擎
       ├── MAP-Elites 网格探索
       ├── LLM Ensemble 生成候选
       ├── 功能测试硬门控
       └── 复杂度 + 性能 + 可读性评估
  │
  ▼
Arbiter 仲裁 → 去重 → 冲突解决 → 统一报告
  ├── 🔴 阻断项（含进化后代码 diff）
  ├── 🟡 建议项
  └── 💭 优化建议
```

---

## 静态门控规则

### 复杂度（5 项）

| 规则 | 默认阈值 | 级别 |
|------|---------|------|
| `COMPLEXITY-CYCLOMATIC` 圈复杂度 | >15 | 🔴 |
| `COMPLEXITY-COGNITIVE` 认知复杂度 | >20 | 🔴 |
| `METRICS-NESTING` 嵌套深度 | >4 | 🟡/🔴 |
| `METRICS-FUNC-LENGTH` 函数行数 | >80 | 🟡/🔴 |
| `METRICS-PARAM-COUNT` 参数数量 | >5 | 🟡 |

### 安全（12+ 条）

| 类别 | 规则 ID | 检测 |
|------|---------|------|
| SQL 注入 | `SEC-SQL-FSTRING` / `SEC-SQL-EXECUTE` | f-string/拼接 SQL |
| 命令注入 | `SEC-CMD-INJECT` | os.system/subprocess f-string/拼接 |
| 硬编码密钥 | `SEC-HARDCODED-KEY` / `SEC-PRIVATE-KEY` | API key/password/私钥 |
| 路径遍历 | `SEC-PATH-TRAVERSAL` | 用户输入在文件路径中 |
| 反序列化 | `SEC-DESERIALIZE-PICKLE` / `SEC-DESERIALIZE-YAML` | pickle/yaml.load |
| 危险内置 | `SEC-DANGEROUS-BUILTIN` | eval/exec/compile |
| 裸 except | `SEC-BARE-EXCEPT` | `except:` 无类型 |
| XSS | `SEC-XSS-UNSAFE` | mark_safe/safe=True |

---

## EVOLVE-BLOCK 标记

OpenEvolve 只进化标记区域的代码：

```python
# 不受影响
import numpy as np

# EVOLVE-BLOCK-START
def poorly_written(data):
    """高复杂度、低性能 — OpenEvolve 会自动优化"""
    result = []
    for i in range(len(data)):
        for j in range(i + 1, len(data)):
            if data[i] > data[j]:
                result.append(data[i] - data[j])
    return result
# EVOLVE-BLOCK-END

# 不受影响
def main():
    ...
```

**你的 pytest 测试定义了"正确行为"** — OpenEvolve 进化出的所有代码变体都必须通过测试，不通过直接淘汰。

---

## GitHub CI/CD

### 配置（3 步）

```bash
# 1. 复制 CI 文件
cp .github/workflows/code-review.yml 你的仓库/.github/workflows/
cp scripts/ci_review.py              你的仓库/scripts/
cp .code-review.yaml                 你的仓库/

# 2. 编辑 .code-review.yaml，填入文件→测试映射
# 3. GitHub Secrets 设 LLM API Key
```

### `.code-review.yaml`

```yaml
gate:
  complexity_threshold: 15
  cognitive_threshold: 20
  max_function_lines: 80
  max_nesting_depth: 4
  max_parameters: 5

file_mapping:
  "src/payment/processor.py": "tests/test_processor.py"
  # 有映射 → 门控 + OpenEvolve 进化
  # 无映射 → 仅门控

evolve:
  enabled: true
  iterations: 100       # CI 中建议 50-100
  timeout_minutes: 10
```

### 效果

每次 PR 自动运行：静态门控（不调 LLM）→ 有测试映射的文件自动进化 → 审查报告贴到 PR comment。

- 门控阻断 = CI 失败
- 进化失败 ≠ CI 失败（进化是 bonus）
- 进化产物作为 Artifact 可下载

---

## LLM 配置

系统自动检测可用的 provider：

```bash
# 优先级: DEEPSEEK > OPENAI > GEMINI > OLLAMA

# Gemini
export GEMINI_API_KEY="..."   # gemini-2.5-flash + gemini-2.5-pro

# DeepSeek
export DEEPSEEK_API_KEY="..." # deepseek-chat + deepseek-reasoner

# GPT
export OPENAI_API_KEY="sk-..."# gpt-4o-mini + gpt-4o

# 本地
export OLLAMA_API_KEY="x"     # llama3.2（需 ollama pull llama3.2）
```

手动覆盖：

```bash
export CRA_MODEL="deepseek-chat"
export CRA_MODEL_SECONDARY="deepseek-chat"
export CRA_API_BASE="https://api.deepseek.com"
```

---

## 项目结构

```
evolve-code-reviewer/
├── src/cra/
│   ├── cli.py              # CLI 入口 (typer)
│   ├── gate.py             # 静态门控（19条规则，v0.3）
│   ├── evolver.py           # OpenEvolve 进化引擎
│   ├── bench.py             # 基准测试 + JSON 指标
│   ├── arbiter.py           # 去重 + 冲突解决 + 报告
│   ├── feedback.py          # 反馈收集 + 统计
│   └── agents/
│       ├── types.py         # ReviewIssue, IssueCategory
│       ├── base.py          # ReviewAgent 基类
│       └── ensemble.py      # 多 Agent 并行调度
├── tests/                   # 124 tests
│   ├── test_gate.py         # 37 门控测试
│   ├── test_evolver.py      # 13 进化器测试
│   ├── test_bench.py        #  8 基准测试
│   ├── test_agents.py       # 19 Agent 测试
│   └── test_pipeline.py     #  6 集成测试
├── examples/                # 41 功能测试
├── .github/workflows/       # CI 配置
├── .code-review.yaml        # 仓库配置
└── SKILL.md                 # WorkBuddy 对话式入口
```

---

## 成本估算

| Provider | 单次进化（200代） |
|----------|-----------------|
| Gemini Flash | ~$1-3 |
| DeepSeek | ~$0.5-1 |
| GPT-4o-mini | ~$2-5 |
| Ollama 本地 | $0 |

静态门控不调 LLM，成本为 0。

---

## FAQ

**Q: 必须写测试吗？**  
A: OpenEvolve 进化必须有测试。无测试 → 只做静态门控。可用 LLM 辅助生成测试。

**Q: 进化后的代码安全吗？**  
A: 功能测试是硬门控。但测试覆盖不到的场景仍需人工审查 diff。

**Q: 支持哪些语言？**  
A: Python（完整支持）+ JS/TS（ESLint 门控）。

**Q: 能跳过进化吗？**  
A: `cra review --skip-evolve` 或设 `evolve.enabled: false`。

---

> **TDD**: 所有功能测试先行。`python -m pytest tests/ examples/` — 124 tests, all green.
