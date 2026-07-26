# Story: GenerateReverseLookupQuestions Enhancement

## User Story
As a **player searching for cards by function**, I want **accurate reverse lookup answers listing specific cards that do what I need**, so that **I find the right card without knowing its name**.

## Context
This story was originally scoped to ENHANCE the reverse lookup generator. The enhancements have been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_reverse_lookup_questions.py`) ✅ COMPLETE
- `GenerateReverseLookupQuestions(BaseGenerator[dict])` — 494 lines
- **4 templates**: mechanic_search, tribal_search, utility_search, commander_search
- **4 lookup categories** with hardcoded lists:
  - mechanics: landfall, magecraft, proliferate, cascade, storm, 11 more
  - keywords: flying, trample, deathtouch, lifelink, 16 more
  - tribes: elf, goblin, zombie, spirit, 20 more
  - utility: protect commander, draw on creature death, sacrifice outlet, 12 more
- Rule section mapping for keyword references
- Uses `MTGDataAccess.get_cards_enriched()` and `get_cards_by_keyword_mechanic()`

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a SIMPLIFIED `reverse_lookup` category with only 1 template (`what_card_does_this`)
- No TrainForge-style generator class exists

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/reverse_lookup.py` with `GenerateReverseLookupQuestions(BaseGenerator[dict])`
- [ ] Port all 4 templates with full HARD REJECT validation rules
- [ ] Port lookup categories and rule section mappings
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Update templates.yaml with 4-template version

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Old CLI file is the REFERENCE IMPLEMENTATION (494 lines)
- Uses `Rule` model for rule section references
- Cards searched by keyword mechanic (`get_cards_by_keyword_mechanic`) and text regex
