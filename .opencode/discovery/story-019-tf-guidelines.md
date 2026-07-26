# Story: Port GenerateQuickGuidelines to TrainForge

## User Story
As a **TrainForge user**, I want **the data-driven deckbuilding guidelines generator available in the TrainForge UI**, so that **I can generate archetype-specific deckbuilding Q&A data through the web interface**.

## Context
The `GenerateQuickGuidelines` generator is implemented in the old CLI (510 lines) with 5 templates and 19 archetypes. It needs to be ported to the TrainForge generator pattern.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/guidelines.py`
- [ ] Generator class extends `BaseGenerator[dict]`
- [ ] All 5 templates ported: land_count, ramp_package, removal_suite, card_advantage, win_con_density
- [ ] All 19 archetypes ported with strategy summaries
- [ ] Commander examples per archetype ported
- [ ] Uses enriched get_archetype_data(), get_commanders_enriched(), get_game_states()
- [ ] Templates defined in `templates.yaml` under `guidelines` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- The old CLI has hardcoded archetype strategies, commander examples, and strategy summaries — these should be ported as-is
- Future version could make these data-driven from EDHREC/MTG data
- Note: old CLI's `get_archetype_data()` method on `MTGDataAccess` calls `mtg_archetypes.archetypes` collection — this method must exist in the enriched TrainForge data source
