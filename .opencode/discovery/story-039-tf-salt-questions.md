# Story: Port GenerateSaltQuestions to TrainForge

## User Story
As a **TrainForge user**, I want **the salt questions generator available in the TrainForge UI**, so that **I can generate controversial/salty card analysis Q&A data through the web interface**.

## Context
The `GenerateSaltQuestions` generator is implemented in the old CLI (38 lines) with 1 template. It generates Q&A about controversial or "salty" Commander cards. It uses `MTGDataAccess.get_salty_cards()` with a minimum salt rating of 1.2 and batches cards in groups of 8.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/salt_questions.py`
- [ ] Generator class extends `BaseGenerator[list[dict]]` (TrainForge version) — list of salty card dicts
- [ ] Template ported: salt_analysis (1 template)
- [ ] BATCH_SIZE = 8 (cards per batch)
- [ ] Uses `MTGDataAccess.get_salty_cards()` with `min_salt=1.2` and limit parameter
- [ ] Batches cards into groups of 8 for richer context in prompts
- [ ] `build_prompt()` delegates to `build_salt_prompt()` from common.py
- [ ] Templates defined in `templates.yaml` under `salt_analysis` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 4 in the old CLI (1,000 examples in phase4 mode)
- The `build_salt_prompt()` helper in common.py also needs porting
- Category is "salt_analysis"
- Generator batches multiple salty cards together for richer multi-card analysis
- Data type is `list[dict]` — untyped dict data from the salt collection
