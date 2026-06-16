# Review Checklist — Code Review Agent

Quick reference for the human reviewer. Use this when reviewing the AI-generated report to ensure nothing is missed.

---

## 🔴 Blocker Checklist (MUST pass to merge)

- [ ] **No SQL/command injection**: All user inputs use parameterized queries or proper sanitization
- [ ] **No hardcoded secrets**: No API keys, passwords, tokens in source code
- [ ] **Auth on new endpoints**: Every new route has authentication middleware
- [ ] **No data loss risk**: Migrations are reversible, deletes have confirmation
- [ ] **Error handling**: Critical paths have proper error handling, no bare `except:`
- [ ] **Breaking changes**: API contracts are backward-compatible or versioned
- [ ] **Cyclomatic complexity ≤ 15**: No function exceeds the threshold without justification
- [ ] **Cognitive complexity ≤ 20**: No function is cognitively overwhelming

---

## 🟡 Suggestion Checklist (SHOULD fix)

- [ ] **Input validation**: All external inputs are validated at the boundary
- [ ] **Clear naming**: Variables/functions/classes are self-explanatory
- [ ] **Tests for new behavior**: Important paths have test coverage
- [ ] **No N+1 queries**: Database calls are batched or eager-loaded
- [ ] **No duplicate code**: Common logic is extracted into shared utilities
- [ ] **Proper logging**: Errors are logged with sufficient context for debugging
- [ ] **Magic values explained**: All magic numbers/strings are named constants

---

## 💭 Nit Checklist (NICE to have)

- [ ] **Code formatting**: Consistent with team style guide (auto-fixed where possible)
- [ ] **Documentation**: Public APIs have docstrings
- [ ] **Import organization**: Imports are sorted and grouped correctly
- [ ] **Type hints**: Complex function signatures have type annotations

---

## Agent-by-Agent Priority Reference

| Priority | Agent | What It Catches | Human Should Verify |
|----------|-------|-----------------|---------------------|
| 1 | Security | Injection, secrets, auth bypass | Business logic security |
| 2 | Complexity | High cyclomatic/cognitive complexity | Whether the refactor is worth it |
| 3 | Performance | N+1 queries, O(n²) algorithms | Actual performance impact at scale |
| 4 | Readability | Bad naming, magic numbers, poor comments | Domain-specific naming conventions |
| 5 | Style | Formatting, import order | Team-specific conventions |

---

## When to Override the AI

The AI may flag false positives in these cases. Human reviewer should override:

1. **Framework boilerplate**: Route registration, config classes, and DI wiring are inherently complex but don't need refactoring
2. **Algorithm implementations**: Well-known algorithms with published pseudocode may have high cyclomatic complexity by nature
3. **Performance-critical sections**: Sometimes readable code is sacrificed for performance — document WHY in comments
4. **Domain constraints**: The AI doesn't know your business rules; it may flag something as "overly complex" when it actually needs that complexity

**Override mechanism**: Add `@review:override(reason="...")` annotation above the flagged code.
