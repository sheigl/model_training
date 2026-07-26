# Story: Port GenerateCardSearchQueries to TrainForge

## User Story
As a **TrainForge user**, I want **the card search generator available in the TrainForge UI**, so that **I can generate card search Q&A data through the web interface**.

## Context
The `GenerateCardSearchQueries` generator is implemented in the old CLI (518 lines) with 5 templates and 20 search patterns. It needs to be ported to the TrainForge generator pattern.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/card_search.py`
- [ ] Generator class extends `BaseGenerator[CardWithMetadata]` (TrainForge version)
- [ ] All 5 templates ported: competitive, budget, commander_specific, thematic, beginner
- [ ] All 20 search patterns ported with MongoDB filter definitions
- [ ] Templates defined in `templates.yaml` under `card_search` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Uses enriched `MTGDataAccess.get_cards_enriched()` with typed returns
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High
