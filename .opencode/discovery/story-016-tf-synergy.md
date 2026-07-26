# Story: Port GenerateSynergyQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the synergy discovery generator available in the TrainForge UI**, so that **I can generate card synergy Q&A data through the web interface**.

## Context
The `GenerateSynergyQuestions` generator is implemented in the old CLI (584 lines) with 4 templates. It needs to be ported to the TrainForge generator pattern.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/synergy.py`
- [ ] Generator class extends `BaseGenerator[CardWithMetadata]`
- [ ] All 4 templates ported: combo_piece, value_engine, tribal_synergy, mechanic_synergy
- [ ] Combo data lookup preserved (via enriched get_combos_enriched)
- [ ] EDHREC tag-based synergy matching preserved
- [ ] Templates defined in `templates.yaml` under `synergy` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High
