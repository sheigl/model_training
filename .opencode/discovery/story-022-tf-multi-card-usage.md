# Story: Port GenerateMultiCardUsage to TrainForge

## User Story
As a **TrainForge user**, I want **the multi-card usage generator available in the TrainForge UI**, so that **I can generate multi-card interaction Q&A data through the web interface**.

## Context
The `GenerateMultiCardUsage` generator is implemented in the old CLI (39 lines) with 1 template and outputs Q&A about how two cards work together. It uses `MTGDataAccess.get_combos_enriched()` to fetch combos and pulls card names from combo `uses` field.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/multi_card_usage.py`
- [ ] Generator class extends `BaseGenerator[ComboWithCards]` (TrainForge version)
- [ ] Template ported: multi_card (1 template)
- [ ] Uses `MTGDataAccess.get_combos_enriched()` with filters (`{"status": "OK"}`)
- [ ] Filters for combos with at least 2 card names and a description
- [ ] `build_prompt()` extracts first 2 card names from combo's `uses` field and calls `build_multi_card_usage_prompt()`
- [ ] Templates defined in `templates.yaml` under `multi_card_usage` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Minimal generator (39 lines) — straightforward to port
- Uses `build_multi_card_usage_prompt()` from common.py — TrainForge equivalent may need porting too
- Data source is combo `uses` cards, not combo `cards` field (unlike GenerateComboQueries)
