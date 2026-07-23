# Pipeline Status

## Migration Complete ✅

All 27 synthetic data generators have been converted from old pymongo collection-passing pattern to `BaseGenerator[T] + MTGDataAccess` architecture.

| Phase | Generators | Discovery | Technical Planning | Implement | Code Review | Test | Document |
|-------|-----------|-----------|-------------------|-----------|-------------|------|----------|
| Pilot (2) | combo_queries, article_qa | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Phase 1 (7) | card_search, comparison, reverse_lookup, synergy, budget, color_identity, guidelines | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Phase 2 (8) | terminology, deckbuilding_theory, commander_building, rules_scenarios, archetypes, game_theory, meta_knowledge, commander_knowledge | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Phase 3 (5)** | rule_explanations, rule_interactions, glossary_with_examples, rule_edge_cases, rule_why_questions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Phase 4 (5)** | guide_qa, staple_analysis, color_staples, salt_questions, multi_card_usage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Test Results
- **219 tests pass** (0 failures, 0 skipped)
- Zero regressions across entire test suite

## Key Changes This Session
### Phase 3 - Rules-Grounded (5 generators)
- All use `MTGDataAccess.get_rules()` or `get_glossary()` instead of raw pymongo collections
- Preserved all filtering logic: SKIP_SECTIONS, COMPLEX_RULE_SECTIONS, PRINCIPLE_SECTIONS, INTERACTION_PAIRS
- Template selection preserved (templates_per_item=2 for rule_explanations and rule_interactions)

### Phase 4 - EDHREC-Grounded (5 generators + 3 new data_access methods)
- Added `MTGDataAccess.get_game_changers()`, `get_salty_cards(min_salt, limit)`, `get_top_cards_by_color(color, limit)`
- All use MTGDataAccess instead of raw pymongo collections or dict of collections
- Preserved all filtering: salt >= 1.2 threshold, game_changer=True, content length > 300, BATCH_SIZE=8

### main.py Updates
- All 10 generator instantiation blocks updated to keyword-arg constructor with `data_access=data_access`
- All call `.generate()` instead of `.generate_*()` methods
- Added missing import for `GenerateRuleWhyQuestions`

### Documentation
- CHANGELOG.md: Updated with Phase 3 and Phase 4 entries
- docs/ARCHITECTURE.md: Updated to reflect all 27 generators migrated, new data_access methods documented

---

# Pipeline Status — Generation Trace Logging

## Current Feature: Model Output Trace Logging
## Last Step Completed: Fixed trace callback logic — now fires for ALL outcomes (accepted, rejected, generation_error)
## Next Action: Ready for production testing
## Subagent Result Summary: Trace callback moved outside if(is_valid) block, added generation_error final_outcome for JSON parse and exception errors, added debug print on trace queue

| Feature | Discovery | Technical Planning | Implement | Code Review | Test | Document |
|---------|----------|-----------|-------------|------|----------|------|
| Generation Trace Logging | ✅ Complete (inline) | ✅ Complete (inline) | ✅ Complete | ✅ Approved | ✅ Passed | ✅ Complete |

### Design Decisions (approved by user)
- **Storage**: Separate collection `synthetic_metrics.generation_traces` (not embedded in Q&A docs)
- **Prompt capture**: Full prompt text stored
- **Mode**: CLI flag `--log-traces` / `--no-log-traces`, enabled by default
- **Schema**: GenerationTrace dataclass with generation + validation_rounds array + final_outcome
