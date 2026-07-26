# Story: Port GenerateComparisonQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the card comparison generator available in the TrainForge UI**, so that **I can generate card comparison Q&A data through the web interface**.

## Context
The `GenerateComparisonQuestions` generator is implemented in the old CLI (627 lines) with 4 templates and 10 effect categories. It needs to be ported to the TrainForge generator pattern.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/comparison.py`
- [ ] Generator class extends `BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]]`
- [ ] All 4 templates ported: power_level, mana_efficiency, commander_suitability, synergy_potential
- [ ] All 10 effect categories ported with MongoDB filter definitions
- [ ] Pair strategies ported (adjacent EDHREC rank, same CMC, same effect)
- [ ] Templates defined in `templates.yaml` under `comparison` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Uses enriched data access methods
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High
