# Architecture Reference — Code Review Agent System

This document describes the five-stage review pipeline. Read when implementing or debugging the pipeline flow.

---

## Pipeline Overview

```
PR Created → Stage 0 → Stage 1 → Stage 2 → Stage 3 → Stage 4 → Merge Ready
                ↑                   ↑                 ↑
          Static Gate         Multi-Agent        Human Decision
          (<2 min)            Review (3-5 min)   + Feedback Loop
```

---

## Stage 0: Static Gate

**Duration**: < 2 min  
**Blocks merge**: YES  
**LLM required**: NO

Checklist (all must pass):
- Cyclomatic complexity ≤ 15 (per function)
- No SQL string concatenation/interpolation
- No hardcoded API keys or secrets
- ruff/eslint passes (auto-fix applied where possible)
- mypy/pyright type checks pass

Output: PASS → Stage 1 | FAIL → return to developer with fix suggestions

---

## Stage 1: Diff Analysis

**Duration**: < 1 min  
**LLM required**: NO

What it does:
1. Parse git diff into structured chunks (by file, function, class)
2. Classify each change: addition / modification / deletion / refactor
3. Identify related files (e.g., interface change → find callers)
4. Extract change context (function signature changes, import changes)

Output: Structured change manifest → Stage 2

---

## Stage 2: Multi-Agent Review

**Duration**: 3-5 min (parallel execution)  
**LLM required**: YES (5 agents + 1 arbiter)

Five agents run in parallel:
- Complexity Reviewer → agent-prompts.md#complexity
- Readability Reviewer → agent-prompts.md#readability
- Security Reviewer → agent-prompts.md#security
- Performance Reviewer → agent-prompts.md#performance
- Style Reviewer → auto-fix (ruff/eslint) or simple rules

Arbiter then:
1. Deduplicates overlapping issues
2. Resolves conflicts using priority: Security > Correctness > Complexity > Performance > Readability > Style
3. Generates unified report → Stage 3

---

## Stage 3: Report Generation

**Duration**: < 1 min

Outputs:
- PR comment (organized by file/line)
- Summary issue (trackable improvement tasks)
- Slack/Feishu notification

Report format: See Arbiter prompt in agent-prompts.md

---

## Stage 4: Human Decision + Feedback

Human reviewer actions for each AI finding:
- ✅ Accept → apply suggested patch
- ✏️ Modify → accept with edits
- ❌ Reject → record reason
- 💬 Ask → request clarification from AI

All actions feed into the feedback loop:
- Accept/Reject/Modify → OpenEvolve → optimize prompts
- Reject reasons → Knowledge base → update anti-patterns
- Accepted patches → Knowledge base → update best practices

Merge requirements:
- Zero 🔴 blockers
- All 🟡 suggestions have disposition (accepted or logged as tech debt)
- At least 1 human reviewer approves

---

## Priority Chain (Conflict Resolution)

```
Security > Correctness > Complexity > Performance > Readability > Style
```

When two agents' recommendations conflict, the higher-priority agent's recommendation wins. The lower-priority concern should still be noted in the report as a trade-off acknowledgment.

Example: Security requires input validation (+5 lines), but Complexity flags function as too long (>80 lines). Result: Security requirement stands. Suggest extracting validation logic into a separate function.

---

## Integration Points

| Trigger | Action |
|---------|--------|
| PR opened | Full pipeline (Stage 0→4) |
| PR updated (new commits) | Full pipeline re-run |
| Comment `/review` | Selective re-run of specified agents |
| Comment `/review security` | Security agent only |
| Scheduled (weekly) | OpenEvolve prompt optimization |
