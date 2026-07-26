# Story: Port GenerateStapleAnalysis to TrainForge

## User Story
As a **TrainForge user**, I want **the staple analysis generator available in the TrainForge UI**, so that **I can generate staple card analysis Q&A data through the web interface**.

## Context
The `GenerateStapleAnalysis` generator is implemented in the old CLI (34 lines) with 1 template. It generates Q&A analyzing why specific cards are Commander staples. It uses `MTGDataAccess.get_game_changers()` to fetch game-changer card data.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/staple_analysis.py`
- [ ] Generator class extends `BaseGenerator[dict]` (TrainForge version) — data is raw dict
- [ ] Template ported: staple_analysis (1 template)
- [ ] Uses `MTGDataAccess.get_game_changers()` with limit parameter
- [ ] `build_prompt()` delegates to `build_staple_analysis_prompt()` from common.py
- [ ] Templates defined in `templates.yaml` under `staple_analysis` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 4 in the old CLI (2,000 examples in phase4 mode)
- The `build_staple_analysis_prompt()` helper in common.py also needs porting
- Category is "staple_analysis"
- Generator is compact (34 lines) — one of the simplest to port
- Data type is `dict` (raw game-changer data, no typed domain model yet)
