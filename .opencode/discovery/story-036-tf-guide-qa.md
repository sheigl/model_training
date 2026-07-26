# Story: Port GenerateGuideQa to TrainForge

## User Story
As a **TrainForge user**, I want **the guide Q&A generator available in the TrainForge UI**, so that **I can generate Q&A data grounded in EDHREC guides through the web interface**.

## Context
The `GenerateGuideQa` generator is implemented in the old CLI (47 lines) with 1 template. It generates Q&A pairs from EDHREC guides fetched via `MTGDataAccess.get_guides()`. It concatenates guide chapter content, applies HTML cleaning, and filters guides with sufficient content.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/guide_qa.py`
- [ ] Generator class extends `BaseGenerator[Guide]` (TrainForge version)
- [ ] Template ported: guide_qa (1 template)
- [ ] Uses `MTGDataAccess.get_guides()` with limit parameter
- [ ] Concatenates chapter contents and applies `clean_html()`
- [ ] Filters guides with cleaned content > 300 characters
- [ ] Shuffles guides randomly before yielding
- [ ] `build_prompt()` delegates to `build_guide_qa_prompt()` with title and cleaned content (truncated to 2000 chars)
- [ ] Templates defined in `templates.yaml` under `guide_qa` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 4 in the old CLI (2,000 examples in phase4 mode)
- The `build_guide_qa_prompt()` and `clean_html()` helpers in common.py also need porting
- Category is "guide_qa"
- Generator is compact (47 lines) — one of the simplest to port
