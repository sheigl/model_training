# Story: GenerateQuickGuidelines Enhancement (Data-Driven)

## User Story
As a **Commander player seeking deckbuilding guidance**, I want **data-driven guidelines backed by EDHREC top cards and real game statistics**, so that **the advice reflects actual competitive play patterns, not just heuristics**.

## Context
This story was originally scoped to BUILD a new data-driven guidelines generator. It has been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_quick_guidelines.py`) ✅ COMPLETE
- `GenerateQuickGuidelines(BaseGenerator[dict])` — 510 lines
- **5 templates**: land_count, ramp_package, removal_suite, card_advantage, win_con_density
- **19 archetypes**: aristocrats, spellslinger, token_swarm, reanimator, combo, control, voltron, stax, landfall, graveyard_value, turbo_draw, midrange, enchantress, artifact, planeswalker, tribal_elves, tribal_goblins, tribal_zombies, tribal_dragons
- Archetype strategy summaries for context building
- Commander examples per archetype (from EDHREC data)
- Uses `MTGDataAccess.get_archetype_data()`, `get_commanders_enriched()`, `get_game_states()`

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a SIMPLIFIED `guidelines` category with only 1 template (`how_many_lands`)
- No TrainForge-style generator class exists

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/guidelines.py` with `GenerateQuickGuidelines(BaseGenerator[dict])`
- [ ] Port all 5 templates with full HARD REJECT validation rules
- [ ] Port all 19 archetypes with strategy summaries and commander examples
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Update templates.yaml with 5-template version

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Old CLI file is the REFERENCE IMPLEMENTATION (510 lines)
- Note: old CLI uses `MTGDataAccess.get_archetype_data()` which calls `mtg_archetypes.archetypes` collection; TrainForge MTGDataAccess doesn't have this method yet
- Archetype-specific context includes: strategy, commanders, key cards, avg CMC, color identity, deck stats
