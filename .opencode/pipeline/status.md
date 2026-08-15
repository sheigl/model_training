# Pipeline Status

## Current Feature: Story 051 — Raise generation max_tokens to 16k — COMPLETE ✅
## Last Step Completed: Document verified/reconciled CHANGELOG.md, AGENTS.md (433 tests), .opencode/context/implementation.md
## Next Action: None — feature shipped. No open follow-ups for this story (the Story 047 regenerate_answer follow-up was resolved by this change).
## Subagent Result Summary: Implement added GENERATION_MAX_TOKENS=16384 (query_model.py constant; base_generator.py:475 generation call + regenerate_answer() now pass it) + 2 regression tests; Code Review approved; Test passed; Docs reconciled. 433 total passing.

| Feature | Discovery + Planning | Implement | Review | Test | Document |
|---------|----------|-----------|--------|------|----------|
| Story 051 — Raise generation max_tokens | ⏳ Skipped (simple fix) | ✅ Complete | ✅ Approved | ✅ Passed | ✅ Complete |
| Story 047 — Raise validation max_tokens | ⏳ Skipped (simple fix) | ✅ Complete | ✅ Approved | ✅ Passed | ✅ Complete |
| Story 046 — Filter validator transport failures | ✅ Complete | ✅ Complete | ✅ Approved | ✅ Passed | ✅ Complete |

## Other tracked follow-ups (not part of Story 051):
- Thread the batch QA index through `validate_answer` for true per-QA sibling-correction dedupe (common.py note from Story 046).
