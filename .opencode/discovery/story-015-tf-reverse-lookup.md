# Story: Port GenerateReverseLookupQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the reverse lookup generator available in the TrainForge UI**, so that **I can generate feature-to-card Q&A data through the web interface**.

## Context
The `GenerateReverseLookupQuestions` generator is implemented in the old CLI (494 lines) with 4 templates and 4 lookup categories. It needs to be ported to the TrainForge generator pattern.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/reverse_lookup.py`
- [ ] Generator class extends `BaseGenerator[dict]`
- [ ] All 4 templates ported: mechanic_search, tribal_search, utility_search, commander_search
- [ ] All lookup categories ported (mechanics, keywords, tribes, utility)
- [ ] Rule section mappings ported
- [ ] Templates defined in `templates.yaml` under `reverse_lookup` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High
