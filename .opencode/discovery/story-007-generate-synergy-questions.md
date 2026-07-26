# Story: GenerateSynergyQuestions Enhancement

## User Story
As a **Magic player building around a key card**, I want **specific synergy explanations with mechanical reasoning**, so that **I understand WHY cards work together and can discover new interactions**.

## Context
This story was originally scoped to ENHANCE the synergy generator. The enhancements have been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_synergy_questions.py`) ✅ COMPLETE
- `GenerateSynergyQuestions(BaseGenerator[CardWithMetadata])` — 584 lines
- **4 templates**: combo_piece, value_engine, tribal_synergy, mechanic_synergy
- Data from Commander Spellbook combos + EDHREC tags + card keywords
- Full HARD REJECT validation per template with detailed checklists

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a SIMPLIFIED `synergy` category with only 1 template (`what_synergizes_with`)
- No TrainForge-style generator class exists

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/synergy.py` with `GenerateSynergyQuestions(BaseGenerator[CardWithMetadata])`
- [ ] Port all 4 templates with full HARD REJECT validation rules
- [ ] Port combo data lookup (via enriched MTGDataAccess.get_combos_enriched)
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Update templates.yaml with 4-template version

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Old CLI file is the REFERENCE IMPLEMENTATION (584 lines)
- Combines Commander Spellbook data with EDHREC tags for richer synergy discovery
- Distinguishes between "card is engine", "card is payoff", "card is enabler"
