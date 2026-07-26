# Story: GenerateComparisonQuestions Enhancement

## User Story
As a **player choosing between similar cards**, I want **detailed mechanical comparisons with context-aware recommendations**, so that **I pick the right card for my specific deck and strategy**.

## Context
This story was originally scoped to ENHANCE the comparison generator. The enhancements have been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_comparison_questions.py`) ✅ COMPLETE
- `GenerateComparisonQuestions(BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]])` — 627 lines
- **4 templates**: power_level, mana_efficiency, commander_suitability, synergy_potential
- **10 effect categories**: Fast Mana, Green Ramp, Removal, Card Draw, Counterspells, Board Wipes, Tutors, Reanimation, Protection, Token Generation
- **3 pair strategies**: adjacent EDHREC rank, same CMC different colors, same effect different colors
- **10 example commanders**, **15 synergy themes** for context variation
- Full HARD REJECT validation per template type

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a SIMPLIFIED `comparison` category with only 1 template (`which_is_better`)
- No TrainForge-style generator class exists

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/comparison.py` with `GenerateComparisonQuestions(BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]])`
- [ ] Port all 4 templates with full HARD REJECT validation rules
- [ ] Port all 10 effect categories with MongoDB filter definitions
- [ ] Port pair strategies (adjacent rank, same CMC, same effect)
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Update templates.yaml with 4-template version

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Old CLI file is the REFERENCE IMPLEMENTATION (627 lines)
- The `build_card_detail()` function in old CLI `common.py` may need porting too
- TrainForge validator uses `notation_legend` + `system_message` from templates.yaml instead of per-generator constants
