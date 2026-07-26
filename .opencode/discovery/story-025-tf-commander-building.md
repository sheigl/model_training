# Story: Port GenerateCommanderBuilding to TrainForge

## User Story
As a **TrainForge user**, I want **the Commander building generator available in the TrainForge UI**, so that **I can generate Commander archetype deckbuilding Q&A data through the web interface**.

## Context
The `GenerateCommanderBuilding` generator is implemented in the old CLI (604 lines) with 2 templates and 12 archetypes. This is the most complex Phase 2 generator — it enriches prompts with real commander data from EDHREC, key cards, archetype data, articles, and guides via `MTGDataAccess`. It uses a custom `CommanderBuildingBatch` dataclass.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/commander_building.py`
- [ ] Generator class extends `BaseGenerator[CommanderBuildingBatch]` (TrainForge version)
- [ ] Port `CommanderBuildingBatch` dataclass with all fields: archetype_name, archetype_description, example_commanders, key_cards, win_conditions, weaknesses, relevant_articles, relevant_guides
- [ ] All 2 templates ported: general_advice, example_driven
- [ ] All 12 archetypes ported (sacrifice/aristocrats, spellslinger, token swarm, reanimator, combo, control, voltron, stax/prison, landfall, graveyard value, turbo draw, midrange goodstuff)
- [ ] Port ARCHETYPE_KEYWORD_MAP, ARCHETYPE_DB_MAP, ARCHETYPE_KEY_CARDS mappings
- [ ] Both validation rule sets ported (COMMANDER_GENERAL_VALIDATION, COMMANDER_EXAMPLE_VALIDATION)
- [ ] Uses enriched data access methods: `get_commanders_enriched()`, `get_archetype_data()`, `get_articles()`, `get_guides()`, `get_cards_enriched()`
- [ ] Lazy loading pattern with `_ensure_data_loaded()` preserved
- [ ] Commander fetching by oracle text keyword matching
- [ ] Article/guide relevance scoring preserved
- [ ] `build_prompt()` includes commanders, key cards, archetype details, articles, and guides as XML blocks
- [ ] `build_context()` and `get_source_data()` ported
- [ ] Templates defined in `templates.yaml` under `commander_building` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- This is the most complex Phase 2 generator due to its multi-source data enrichment
- Uses a custom `CommanderBuildingBatch` dataclass — needs porting to TrainForge domain models
- Part of Phase 2 in the old CLI (3,000 examples in phase2 mode)
- The old CLI uses lazy caching (`_commander_cache`, `_key_card_cache`) — preserve this pattern
