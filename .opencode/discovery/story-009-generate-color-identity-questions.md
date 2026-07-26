# Story: GenerateColorIdentityQuestions Enhancement

## User Story
As a **Commander player building a deck**, I want **accurate color identity legality answers with rule explanations**, so that **I know exactly what cards I can and cannot play in my commander's color identity**.

## Context
This story was originally scoped to ENHANCE the color identity generator. The enhancements have been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_color_identity_questions.py`) ✅ COMPLETE
- `GenerateColorIdentityQuestions(BaseGenerator[ColorIdentityContext])` — 686 lines
- **4 templates**: mono_color, two_color, three_color, five_color
- Uses ALL EDHREC commanders weighted by deck count popularity
- Full CR 903.4 color identity calculation
- Color pair/wedge/shard naming maps (Azorius, Dimir, etc.)
- Handles hybrid mana, phyrexian mana, colorless cards, color indicators
- Template-specific validation with HARD REJECT rules

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a COMPLETELY DIFFERENT `color_identity` category (`what_color_does_this` about color pie, not Commander legality)
- No TrainForge-style generator class exists

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/color_identity.py` with `GenerateColorIdentityQuestions(BaseGenerator[ColorIdentityContext])`
- [ ] Port all 4 templates with full HARD REJECT validation rules
- [ ] Port commander weighting logic (popular commanders appear more)
- [ ] Port color identity calculation (CR 903.4 including hybrid, phyrexian, etc.)
- [ ] Port edge case handling (Extort in reminder text, Devoid, DFCs)
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Update templates.yaml from color-pie topic to Commander legality topic

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Old CLI file is the REFERENCE IMPLEMENTATION (686 lines)
- **CRITICAL**: templates.yaml has the WRONG topic for this category — it describes color pie philosophy questions instead of Commander color identity legality questions. This must be corrected during porting.
- Uses `get_commanders_enriched()` and `get_cards_enriched()` for data
- `ColorIdentityContext` dataclass needs to be ported
