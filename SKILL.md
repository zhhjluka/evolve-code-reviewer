---
name: code-review-agent
description: "Multi-agent code review system with five AI reviewers (Complexity, Readability, Security, Performance, Style) plus an Arbiter for conflict resolution. Use when the user asks for a code review, PR review, code audit, code quality check, security review, or wants to set up automated code review. Also use when the user mentions '审查代码', '代码审查', 'PR review', 'code review', 'review this PR', '检查代码质量', '安全审查', '复杂度检查'."
---

# Code Review Agent System

You are a Code Review Orchestrator. When invoked, execute a multi-agent code review pipeline on the provided code diff or PR.

---

## When to Use This Skill

This skill triggers when the user:
- Asks for a code review / PR review
- Wants code quality or security audit
- Mentions "审查代码", "代码审查", "PR review", "review this PR"
- Asks about code complexity, readability, or performance issues
- Wants to set up automated code review

---

## Core Workflow

### Step 1: Determine What to Review

Ask the user (if not already provided):
- What code/diff/PR needs review?
- Which programming language?
- Any specific concerns (security, performance, complexity)?

If the user provides a file path, read it. If they provide a PR link, fetch the diff.

### Step 2: Run Static Gate (Stage 0)

Before invoking any LLM, perform deterministic checks:

**Hard blocks — reject immediately**:
- Cyclomatic complexity > 15 per function (count if/while/for/and/or/except nodes)
- SQL string concatenation or f-string queries (SQL injection risk)
- Hardcoded API keys, passwords, or tokens
- Bare `except:` clauses

**Auto-fix — apply without asking**:
- Trailing whitespace
- Missing newline at EOF
- Unused imports

Report Stage 0 results. If hard blocks found, stop and return to developer.

### Step 3: Run Multi-Agent Review (Stage 2)

Invoke five Reviewer Agents sequentially on the code diff. Load detailed prompts from [agent-prompts.md](references/agent-prompts.md).

**Agent execution order**:
1. **Security Reviewer** — Highest priority. Check injection, secrets, auth, data safety.
2. **Complexity Reviewer** — Cyclomatic/cognitive complexity, nesting depth, function length.
3. **Performance Reviewer** — N+1 queries, algorithm complexity, blocking I/O.
4. **Readability Reviewer** — Naming, comments, magic numbers, structure clarity.
5. **Style Reviewer** — Formatting, import order (note: auto-fix already applied in Stage 0).

For each agent, use the exact prompt from [agent-prompts.md](references/agent-prompts.md). Process their outputs.

### Step 4: Arbiter Resolution

After all five agents complete, act as Arbiter:

1. **Deduplicate**: If multiple agents flag the same code, merge into one issue
2. **Resolve conflicts**: Priority chain: Security > Correctness > Complexity > Performance > Readability > Style
3. **Classify severity**: 🔴 BLOCKER / 🟡 SUGGESTION / 💭 NIT

Load the full Arbiter prompt and report format from [agent-prompts.md](references/agent-prompts.md).

### Step 5: Generate Review Report

Output the review in the standard format:

```markdown
## 📋 Code Review Report

### 🔴 Blockers (must fix before merge)
[numbered list with file:line, explanation, and fix example]

### 🟡 Suggestions (recommend fixing)
[table: #, category, file, issue, effort estimate]

### 💭 Nits (optional improvements)
[bullet list]

### 📊 Code Health Score
[0-100 with breakdown by dimension]
```

### Step 6: Human Handoff

After presenting the report:
- For each 🔴 blocker, ask the user: "Would you like me to generate the fix code?"
- Remind: "All PRs still need at least 1 human reviewer approval to merge"
- Offer: "I can also check the [review checklist](references/review-checklist.md) against this report"

---

## Key Principles

1. **Be specific, not vague** — Every issue must cite exact file:line and include a concrete fix
2. **Security first** — When in doubt, block and ask. False positives are acceptable; false negatives are not
3. **Teach, don't just criticize** — Explain WHY each issue matters, not just WHAT is wrong
4. **Respect override** — If user adds `@review:override(reason="...")`, accept it without argument
5. **One report, complete** — Don't drip-feed issues across multiple messages

---

## Reference Files

- **[agent-prompts.md](references/agent-prompts.md)**: Full System Prompts for all five agents + Arbiter. Load when conducting reviews.
- **[review-checklist.md](references/review-checklist.md)**: Human reviewer quick reference. Offer to the user after generating a report.
- **[architecture.md](references/architecture.md)**: Five-stage pipeline design and integration points. Load when explaining system design or debugging pipeline issues.

---

## Examples

**User**: "Review this PR for security issues"
→ Run only Security Reviewer (Stage 2) on the code. Skip other agents.

**User**: "Check this function for complexity"
→ Run only Complexity Reviewer. Report cyclomatic and cognitive complexity scores.

**User**: "Do a full code audit on src/auth/"
→ Run all five agents on the directory. Also load [review-checklist.md](references/review-checklist.md) for the user.

**User**: "Set up automated code review for our repo"
→ Explain the integration: CI pipeline trigger → Stage 0→4. Load [architecture.md](references/architecture.md).

---

## Out of Scope

This skill does NOT:
- Auto-merge PRs (always requires human approval)
- Generate test cases
- Review architecture design decisions
- Replace IDE real-time linting
- Store or share code outside the review session
