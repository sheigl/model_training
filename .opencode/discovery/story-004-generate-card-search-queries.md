# Story: GenerateCardSearchQueries Enhancement

## User Story
As a **player looking for cards by function**, I want **natural language search that returns the best cards with explanations**, so that **I can find cards for my deck without knowing exact card names**.

## Context
This story was originally scoped to ENHANCE the card search generator. The enhancements have been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_card_search_queries.py`) ✅ COMPLETE
- `GenerateCardSearchQueries(BaseGenerator[CardWithMetadata])` — 518 lines
- **5 templates**: competitive, budget, commander_specific, thematic, beginner
- **20 search patterns**: Green Ramp, Zombie Tokens, Treasure Tokens, White Removal, Blue Card Draw, ETB Effects, Black Removal, Red Burn, Counterspells, Board Wipes, Tutors, Reanimation, Protection, Sacrifice Outlets, Artifact Ramp, Graveyard Hate, Politics/Group Hug, Landfall, Proliferate, Blink/Flicker
- Uses `MTGDataAccess.get_cards_enriched()` for data
- Rich validation per template type (detailed HARD REJECT rules)
- Template-specific validation checklists
- 15 common commanders for commander_specific template

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a SIMPLIFIED `card_search` category with only 1 template (`find_cards_with_effect`)
- `MTGDomain.get_generators()` returns empty list — no generator class exists
- No TrainForge-style generator class for CardSearchQueries

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/card_search.py` with `GenerateCardSearchQueries(BaseGenerator[CardWithMetadata])`
- [ ] Port all 5 templates with full HARD REJECT validation rules
- [ ] Port all 20 search patterns (MongoDB filter definitions)
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Ensure templates.yaml has matching template definitions (update from simplified 1-template to 5-template version)
- [ ] Import and use typed domain models (CardWithMetadata from ported domain_models)
- [ ] Use enriched MTGDataAccess methods (get_cards_enriched with joins)

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- The old CLI file is the REFERENCE IMPLEMENTATION (518 lines)
- Templates.yaml currently has a very basic version — needs updating
- TrainForge generator will differ in constructor (uses `DomainPlugin` + `generation_model`/`validation_model` instead of `models` dict)
