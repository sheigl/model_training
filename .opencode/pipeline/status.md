# Pipeline Status

## Current Feature: Story 047 — Raise validation max_tokens — COMPLETE ✅
## Last Step Completed: Document updated AGENTS.md, CHANGELOG.md, .opencode/context/implementation.md
## Next Action: None — feature shipped. Tracked follow-ups: (1) thread batch QA index through validate_answer for true per-QA sibling-correction dedupe (common.py note); (2) `regenerate_answer` still uses 8192 default — if a reasoning model is ever used for regeneration, it shares the same truncation risk (code review note).
## Subagent Result Summary: Implement changed query_model.py (VALIDATION_MAX_TOKENS=16384 on both validation entry points) + 2 regression tests; Code Review approved; Test passed 394/8 (baseline unchanged); Docs updated.

| Feature | Discovery + Planning | Implement | Review | Test | Document |
|---------|----------|-----------|--------|------|----------|
| Story 047 — Raise validation max_tokens | ⏳ Skipped (simple fix) | ✅ Complete | ✅ Approved | ✅ Passed (394 / 8 pre-existing) | ✅ Complete |
| Story 046 — Filter validator transport failures | ✅ Complete | ✅ Complete | ✅ Approved | ✅ Passed | ✅ Complete |
