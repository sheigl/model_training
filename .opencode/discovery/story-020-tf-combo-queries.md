# Story: Port GenerateComboQueries to TrainForge

## User Story
As a **TrainForge user**, I want **the combo query generator available in the TrainForge UI**, so that **I can generate combo Q&A data through the web interface**.

## Context
The `GenerateComboQueries` generator is implemented in the old CLI (264 lines) with 4 templates and 4 validation rule sets. It generates combo query Q&A pairs from Commander Spellbook combos. This generator uses `MTGDataAccess.get_combos_enriched()` to fetch enriched combo data.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/combo_queries.py`
- [ ] Generator class extends `BaseGenerator[ComboWithCards]` (TrainForge version)
- [ ] All 4 templates ported: how_does_it_work, what_do_i_need, why_does_this_work, what_is_the_result
- [ ] All 4 validation rule sets ported (COMBO_HOW_VALIDATION, COMBO_WHAT_VALIDATION, COMBO_WHY_VALIDATION, COMBO_RESULT_VALIDATION)
- [ ] Uses `MTGDataAccess.get_combos_enriched()` with typed returns
- [ ] `build_prompt()` includes card details, combo description, numbered steps, and combo result
- [ ] Templates defined in `templates.yaml` under `combo_query` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- The old CLI uses `get_combos_enriched(limit=fetch_limit)` — TrainForge version should do the same
- `build_context()` is also implemented for validation — ensure this is ported
- `get_source_data()` extracts card dicts and combo dict for trace tracking
