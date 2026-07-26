# Story: GenerateBudgetAlternatives Enhancement

## User Story
As a **budget-conscious Commander player**, I want **specific cheaper alternatives with price comparisons and mechanical trade-offs**, so that **I can build competitive decks without expensive staples**.

## Context
This story was originally scoped to ENHANCE the budget alternatives generator. The enhancements have been IMPLEMENTED in the old CLI. What remains is porting to the TrainForge framework.

### Old CLI Implementation (`training_data/generate_synthetic_data/generate_budget_alternatives.py`) ✅ COMPLETE
- `GenerateBudgetAlternatives(BaseGenerator[BudgetContext])` — 365 lines
- **4 templates**: pauper_budget, budget_optimized, proxy_friendly, upgrade_path
- **8 budget categories**: Fast Mana, Tutors, Card Draw Engines, Removal, Protection, Win Conditions, Counterspells, Board Wipes
- Uses `MTGDataAccess.get_cards_enriched()` and `get_budget_alternatives()`
- Template-specific validation with HARD REJECT rules
- BudgetContext dataclass for typed data flow

### TrainForge Status (`trainforge/domains/mtg/`) ❌ NOT STARTED
- `templates.yaml` has a SIMPLIFIED `budget` category with only 1 template (`cheaper_alternative`)
- No TrainForge-style generator class exists

## Acceptance Criteria (TrainForge Port)
- [ ] Create `trainforge/domains/mtg/generators/budget.py` with `GenerateBudgetAlternatives(BaseGenerator[dict])`
- [ ] Port all 4 templates with full HARD REJECT validation rules
- [ ] Port all 8 budget categories with MongoDB filter definitions
- [ ] Register the generator in `MTGDomain.get_generators()`
- [ ] Update templates.yaml with 4-template version

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Old CLI file is the REFERENCE IMPLEMENTATION (365 lines)
- Uses both `get_cards_enriched()` and `get_budget_alternatives()` data access methods
- The `get_budget_alternatives()` analytics method in old CLI data_access.py is more sophisticated than anything in TrainForge's data source
