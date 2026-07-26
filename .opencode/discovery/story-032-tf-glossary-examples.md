# Story: Port GenerateGlossaryWithExamples to TrainForge

## User Story
As a **TrainForge user**, I want **the glossary with examples generator available in the TrainForge UI**, so that **I can generate glossary Q&A with in-game examples through the web interface**.

## Context
The `GenerateGlossaryWithExamples` generator is implemented in the old CLI (66 lines) with 1 template. It generates Q&A from glossary terms fetched via `MTGDataAccess.get_glossary()`, using definitions with concrete in-game examples.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/glossary_with_examples.py`
- [ ] Generator class extends `BaseGenerator[GlossaryTerm]` (TrainForge version)
- [ ] Template ported: glossary_example (1 template)
- [ ] Uses `MTGDataAccess.get_glossary()` to fetch glossary terms
- [ ] Filters for terms with definition > 30 characters
- [ ] Shuffles terms randomly before yielding
- [ ] `build_prompt()` delegates to `build_glossary_with_examples_prompt()` from common.py
- [ ] Templates defined in `templates.yaml` under `glossary_with_examples` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 3 in the old CLI (1,500 examples in phase3 mode)
- The `build_glossary_with_examples_prompt()` helper in common.py also needs porting
- Category is "glossary_with_examples"
