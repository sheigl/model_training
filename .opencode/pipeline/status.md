# Pipeline Status

## Current Feature: MTG AI Pipeline — Three Prompt Improvements
## Last Step Completed: Document updated CHANGELOG.md and docs/ARCHITECTURE.md
## Next Action: Complete — all pipeline steps done

| Feature | Discovery + Planning | Implement | Code Review | Test | Document |
|---------|----------|-------------|------|----------|----------|
| Prompt Improvements (trigger ordering, vague outcomes, sibling feedback) | ✅ Complete | ✅ Complete | ✅ Approved | ✅ Passed | ✅ Complete |

## Final Summary

All three prompt improvements implemented, reviewed, tested, and documented:

1. **Trigger ordering** (`constants.py`): New `REQUIREMENTS_BASE` item at index 3 with LIFO/ETB/static-ability rules. Targets #1 failure mode (~50% of rejections).
2. **Vague outcome language** (`constants.py`): Expanded banned phrases at index 5. Targets ~20% of rejections.
3. **Sibling feedback** (`query_model.py`, `common.py`, `base_generator.py`, `generate_quick_guidelines.py`): Hoisted accumulator architecture — Q2/Q3 see Q1's corrections during regeneration.

### Test results: 229 passed, 20 pre-existing failures, 0 regressions, 5 behavioral tests pass
### Documentation: CHANGELOG.md + docs/ARCHITECTURE.md updated