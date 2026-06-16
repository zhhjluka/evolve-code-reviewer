# Code Review Agent (CRA)

AI-powered code review with automatic code optimization using **OpenEvolve**.

> 不只告诉你"代码写得不好"，更直接给你一个功能等价但质量更好的版本。

---

## 快速开始

```bash
# 1. 安装
cd code-review-agent
pip install -e ".[dev]"

# 2. 设置 LLM API Key（任选一个 provider）
# ── Google Gemini (便宜，推荐) ──
export GEMINI_API_KEY="your-key"

# ── OpenAI GPT ──
export OPENAI_API_KEY="sk-..."

# ── DeepSeek (国内推荐) ──
export DEEPSEEK_API_KEY="sk-..."

# ── 本地 Ollama (免费，不泄露代码) ──
export OLLAMA_API_KEY="ollama"      # 值无所谓，但必须设置

# 3. 跑静态检查 — 秒级，不调 LLM
cra gate examples/sample_bad.py

# 4. 完整审查 — 先门控，通过后自动进化代码
cra review examples/sample_bad.py --test examples/test_sample_bad.py

# 5. 保存进化后的代码到文件
cra evolve examples/sample_bad.py -t examples/test_sample_bad.py -o sample_optimized.py
cra review examples/sample_bad.py -t examples/test_sample_bad.py -o sample_optimized.py
```

---

## 三个命令

### `cra gate` — 静态门控（Stage 0）

纯规则引擎，不调 LLM。2 秒内返回结果。**有 🔴 阻断就合并不了。**

```bash
cra gate examples/sample_bad.py              # 默认阈值=15
cra gate src/main.py --threshold 10          # 更严格的复杂度要求
```

检查项：

| 检查项 | 规则 | 示例 |
|--------|------|------|
| 圈复杂度 | > 15 → 🔴 阻断 | 上帝函数、深层嵌套 |
| SQL 注入 | f-string/拼接含 SQL 关键字 → 🔴 阻断 | `f"SELECT * FROM {table}"` |
| 硬编码密钥 | 匹配 password/token/api_key 等模式 → 🔴 阻断 | `password = "admin123"` |
| 裸 except | `except:` → 🔴 阻断 | 吞掉所有异常 |

### `cra evolve` — 代码进化（Stage 2 核心）

**调用 OpenEvolve + LLM**，在功能正确的前提下自动进化代码。

```bash
cra evolve examples/sample_bad.py \
    --test examples/test_sample_bad.py        # pytest 测试 ← 必须提供

cra evolve src/my_code.py \
    --test tests/test_my_code.py \
    --iterations 100                          # 进化 100 代（默认 200）

cra evolve src/my_code.py \
    --test tests/test_my_code.py \
    --output src/my_code_optimized.py         # 保存进化后代码到文件
```

工作原理：

```
你的代码 + pytest测试
      │
      ▼
OpenEvolve 进化搜索（200 代）
  ├── MAP-Elites 维持多样性
  ├── LLM Ensemble 生成候选代码
  └── 每代评估：功能测试(硬门控) + 圈复杂度 + 性能 + 行数
      │
      ▼
输出：功能相同但质量更好的代码 + diff
```

**前置条件**：代码中的待进化函数必须用 `EVOLVE-BLOCK` 标记包裹：

```python
# 这部分不会变
import numpy as np

# EVOLVE-BLOCK-START
def process_orders(orders):
    # ← 只有这里面的代码会被 OpenEvolve 进化
    ...
# EVOLVE-BLOCK-END

# 这部分也不会变
def main():
    ...
```

**硬门控**：进化出的任何代码变体都必须通过你的 pytest 测试，不通过直接淘汰。

### `cra review` — 完整审查

Gate → Evolve 一气呵成。

```bash
# 完整审查
cra review examples/sample_bad.py \
    --test examples/test_sample_bad.py

# 只跑门控，不进化
cra review examples/sample_bad.py \
    --test examples/test_sample_bad.py \
    --skip-evolve

# 完整审查，更严格的门控阈值
cra review src/main.py \
    --test tests/test_main.py \
    --threshold 10 \
    --iterations 100
```

流程：

```
cra review →
  ├── Stage 0: Static Gate (2s)
  │     ├── 复杂度检查 → 🔴 阻断？直接退出
  │     ├── 安全检查   → 🔴 阻断？直接退出
  │     └── 通过 → 进入 Stage 2
  │
  └── Stage 2: Code Evolution (几分钟)
        ├── OpenEvolve 进化搜索 200 代
        ├── 每代：功能测试 → 复杂度 → 性能 → 产物反馈
        └── 输出：进化后代码 + 前后对比报告
```

---

## 写自己的进化样本

### 1. 写待进化代码

```python
# my_module.py

# EVOLVE-BLOCK-START
def badly_written_function(data: list[int]) -> list[int]:
    """高复杂度、低性能的实现"""
    result = []
    for i in range(len(data)):
        for j in range(i + 1, len(data)):
            if data[i] > data[j]:
                # 嵌套循环 + 复杂条件 = 圈复杂度高
                if data[i] % 2 == 0 and data[j] % 2 == 1:
                    result.append(data[i] - data[j])
                elif data[i] % 2 == 1 and data[j] % 2 == 0:
                    result.append(data[i] + data[j])
    return result
# EVOLVE-BLOCK-END
```

### 2. 写功能正确性测试

OpenEvolve 用这些测试来验证进化后的代码是否还"做一样的事"。**测试越全面，进化结果越可靠。**

```python
# test_my_module.py
import pytest
from my_module import badly_written_function

def test_empty():
    assert badly_written_function([]) == []

def test_single():
    assert badly_written_function([1]) == []

def test_sorted_input():
    assert badly_written_function([1, 2, 3]) == []

def test_known_output():
    result = badly_written_function([4, 2, 6, 1])
    # 基于需求文档计算出的预期输出
    assert sorted(result) == sorted([3, 5, 7])

def test_large_input():
    """验证边界情况和大数据量"""
    data = list(range(100))
    result = badly_written_function(data)
    assert isinstance(result, list)
    # 不抛异常就过了（性能则由 benchmark 测量）
```

### 3. 运行进化

```bash
cra evolve my_module.py --test test_my_module.py --iterations 200
```

---

## 完整示例：run 一遍

```bash
# 1. 看看样本代码有多"坏"
cra gate examples/sample_bad.py
# → 🔴 process_orders: 圈复杂度 20 (阈值 15)

# 2. 确保测试全部通过（OpenEvolve 的前提）
pytest examples/test_sample_bad.py -v
# → 28 passed

# 3. 开始进化（保存结果到文件）
cra review examples/sample_bad.py \
    --test examples/test_sample_bad.py \
    --iterations 200 \
    --output examples/sample_optimized.py

# 输出示例:
# ═══════════════════════════════════════════════
#   📊 Code Evolution Report
# ═══════════════════════════════════════════════
#
# --- Result #1 ---
#   Complexity: 20.0 → 8.0   (⬇️ 12.0)
#   Lines:      105   → 72   (⬇️ 33)
#   Perf:       3.42ms → 2.15ms (⬆️ faster 37.1%)
#
# Total time: 287.3s
```

---

## 环境要求

| 依赖 | 用途 | 安装方式 |
|------|------|---------|
| Python 3.10+ | 运行环境 | - |
| `openevolve` | 代码进化引擎 | `pip install openevolve`（已含在 pyproject.toml） |
| LLM API Key | LLM 调用 | 见下方 LLM 配置 |
| `radon` | 复杂度检查 | `pip install radon`（已含在 [dev]） |
| `pytest` | 功能正确性测试 | `pip install pytest`（已含在 [dev]） |

**LLM 配置**：自动检测环境变量中的 API Key，按优先级选择 provider。可通过环境变量覆盖默认模型和端点。

```bash
# ── 方式 1: 设置 API Key，自动检测 provider ──
# 系统按优先级检测: DEEPSEEK_API_KEY > OPENAI_API_KEY > GEMINI_API_KEY > OLLAMA_API_KEY

export GEMINI_API_KEY="your-key"      # → 自动用 gemini-2.5-flash + gemini-2.5-pro
export OPENAI_API_KEY="sk-..."        # → 自动用 gpt-4o-mini + gpt-4o
export DEEPSEEK_API_KEY="sk-..."      # → 自动用 deepseek-chat + deepseek-reasoner
export OLLAMA_API_KEY="ollama"        # → 自动用 llama3.2 (需先 ollama pull llama3.2)

# ── 方式 2: 手动指定（覆盖自动检测）──
export CRA_MODEL="deepseek-chat"              # 主模型
export CRA_MODEL_SECONDARY="deepseek-chat"    # 辅助模型（可用同一模型）
export CRA_API_KEY="$DEEPSEEK_API_KEY"
export CRA_API_BASE="https://api.deepseek.com"

# ── Gemini 示例（默认，推荐）──
export GEMINI_API_KEY="your-key"
# 主模型: gemini-2.5-flash (便宜快速)  辅助模型: gemini-2.5-pro (强推理)

# ── GPT 示例 ──
export OPENAI_API_KEY="sk-..."
# 主模型: gpt-4o-mini (便宜)  辅助模型: gpt-4o (强推理)

# ── DeepSeek 示例（国内推荐）──
export DEEPSEEK_API_KEY="sk-..."
# 主模型: deepseek-chat  辅助模型: deepseek-reasoner

# ── Ollama 示例（免费，不泄露代码）──
ollama pull llama3.2
export OLLAMA_API_KEY="ollama"
# 主模型: llama3.2  辅助模型: llama3.2 (均本地运行)

# ── 高级：手动覆盖所有参数 ──
export CRA_PROVIDER="deepseek"
export CRA_MODEL="deepseek-chat"
export CRA_MODEL_SECONDARY="deepseek-chat"
export CRA_TEMPERATURE="0.7"
```

---

## 项目结构

```
code-review-agent/
├── pyproject.toml              # 项目配置
├── SKILL.md                    # WorkBuddy Skill (对话式 AI 审查)
├── README.md                   # 本文件
├── references/                 # Agent Prompt + 架构文档
│   ├── agent-prompts.md        # 5个审查 Agent 的 System Prompt
│   ├── review-checklist.md     # 人工审查员检查清单
│   └── architecture.md         # 五阶段流水线架构
├── src/cra/                    # 源代码
│   ├── cli.py                  # CLI 入口 (typer)
│   ├── gate.py                 # 静态门控 (radon + 正则)
│   └── evolver.py              # 代码进化引擎 (OpenEvolve)
├── .github/workflows/
│   └── code-review.yml         # GitHub Actions CI 配置
├── scripts/
│   └── ci_review.py            # CI 审查脚本
├── .code-review.yaml           # 仓库配置（文件→测试映射）
└── examples/                   # 示例
    ├── sample_bad.py           # 高复杂度样本代码
    ├── test_sample_bad.py      # 28 个功能测试
    └── conftest.py             # pytest 配置
```

---

## GitHub CI/CD 集成

每次 PR 提交自动运行门控 + 代码进化。

### 1. 复制 CI 文件到你的仓库

```bash
# 将以下文件复制到你的项目仓库根目录:
cp .github/workflows/code-review.yml 你的仓库/.github/workflows/
cp scripts/ci_review.py              你的仓库/scripts/
cp .code-review.yaml                 你的仓库/.code-review.yaml
```

### 2. 配置 `.code-review.yaml`

最重要的配置是 **`file_mapping`**——告诉 CI 哪些文件有对应测试，可以触发进化：

```yaml
file_mapping:
  "src/payment/processor.py": "tests/test_payment_processor.py"
  "src/order/handler.py": "tests/test_order_handler.py"
  # 有映射 → 门控 + 进化（OpenEvolve 需要测试验证正确性）
  # 无映射 → 只跑门控（复杂度 + 安全 + Lint）
```

完整配置示例见项目根目录的 `.code-review.yaml`。

### 3. 设置 GitHub Secrets

仓库 → Settings → Secrets and variables → Actions，添加：

| Secret | 说明 |
|--------|------|
| `GEMINI_API_KEY` | Gemini（推荐） |
| 或 `OPENAI_API_KEY` | OpenAI |
| 或 `DEEPSEEK_API_KEY` | DeepSeek（国内推荐） |

至少设一个。CI 自动检测可用的 provider。

### 4. 效果

之后每次开 PR 或 push 新代码：

```
PR 触发
   │
   ▼
获取变更的 Python 文件 → 过滤排除规则
   │
   ├── Stage 0: Static Gate（每个文件 2s）
   │   ├── 🔴 复杂度超标 / 安全漏洞 → 阻断 CI，阻止合并
   │   └── ✅ 通过
   │
   └── Stage 2: 有测试映射? → OpenEvolve 进化（3-5 min）
       └── 产出 file.evolved.py → 上传为 artifact
   │
   ▼
审查报告 → PR Comment + GitHub Step Summary
```

**设计原则**：
- 无测试映射 = 只做门控，不强求每个文件有测试
- 门控阻断 = CI 失败，PR 不可合并
- 进化失败 ≠ CI 失败（进化是 bonus，不是 gate）
- 进化产物 `.evolved.py` 作为 artifact 可下载，不自动覆盖代码

### 5. 成本预估

| 场景 | 花费 |
|------|------|
| 改 1 个文件，有测试，200 代进化 | $0.5-3 |
| 改 5 个文件，全部只做门控 | $0（不调 LLM） |
| 改 3 个文件，2 个触发进化 | $1-6 |

工作日 20 PR 估算：月费 $20-120。

---

## 常见问题

**Q: OpenEvolve 进化需要多长时间？**  
A: 取决于迭代次数和问题复杂度。200 代通常 3-5 分钟。可先用 `--iterations 50` 快速试跑。

**Q: 没有测试怎么办？**  
A: 必须要有。没有测试 = OpenEvolve 不知道"正确的行为"是什么。可以用 LLM 根据函数签名和注释先生成测试，再人工 review。

**Q: 如何保存进化后的代码？**  
A: 加 `--output` / `-o` 参数：
```bash
cra evolve sample.py -t test_sample.py -o sample_optimized.py
cra review sample.py -t test_sample.py -o sample_optimized.py
```
不加的话会打印 diff 到终端，并提示你用 `--output` 保存。

**Q: 进化后的代码能直接合入吗？**  
A: 不行。OpenEvolve 产出的是**建议**。需要人工审查 diff 后决定是否采纳。功能测试通过不代表没有逻辑错误——测试覆盖不到的边界情况还是需要人看。

**Q: 为什么用 Gemini 而不是 GPT？**  
A: 默认用 Gemini 是因为便宜+快。你可以随时切到 GPT 或 DeepSeek——设环境变量即可，不需要改代码。运行 `cra evolve` 时终端会打印当前使用的 provider 和模型名。

**Q: 成本高吗？**  
A: 200 代 × 各 provider 价格：
- Gemini Flash: ~$1-3/次
- GPT-4o-mini: ~$2-5/次
- DeepSeek: ~$0.5-1/次
- Ollama: 免费

可减少迭代数（`--iterations 50`）或用 Ollama 降至几乎免费。

**Q: Ollama 上用什么模型？**  
A: `ollama pull llama3.2` 或 `qwen2.5-coder`（代码任务更强）。然后 `export OLLAMA_API_KEY=ollama` 即可。

**Q: 能混合用不同 provider 吗？**  
A: 可以。设 `CRA_MODEL=gpt-4o-mini CRA_MODEL_SECONDARY=deepseek-chat`，主模型用 GPT，辅助模型用 DeepSeek。
