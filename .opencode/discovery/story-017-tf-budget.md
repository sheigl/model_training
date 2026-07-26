# Story: Port GenerateBudgetAlternatives to TrainForge

## User Story
As a **TrainForge user**, I want **the budget alternatives generator available in the TrainForge UI**, so that **I can generate budget-friendly card replacement Q&A data through the web interface**.

## Context
The `GenerateBudgetAlternatives` generator is implemented in the old CLI (365 lines) with 4 templates and 8 budget categories. It needs to be ported to the TrainForge generator pattern.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/budget.py`
- [ ] Generator class extends `BaseGenerator[dict]`
- [ ] All 4 templates ported: pauper_budget, budget_optimized, proxy_friendly, upgrade_path
- [ ] All 8 budget categories ported (Fast Mana, Tutors, Card Draw, Removal, Protection, Win Cons, Counterspells, Board Wipes)
- [ ] Relies on enriched get_budget_alternatives() data access method
- [ ] Templates defined in `templates.yaml` under `budget` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High
