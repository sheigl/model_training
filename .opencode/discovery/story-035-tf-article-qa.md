# Story: Port GenerateArticleQa to TrainForge

## User Story
As a **TrainForge user**, I want **the article Q&A generator available in the TrainForge UI**, so that **I can generate Q&A data grounded in EDHREC articles through the web interface**.

## Context
The `GenerateArticleQa` generator is implemented in the old CLI (120 lines) with 1 template and 1 validation rule set. It generates Q&A pairs from EDHREC articles fetched via `MTGDataAccess.get_articles()`. It filters articles with sufficient content (>300 chars after HTML cleaning) and uses `clean_html()` to process article content.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/article_qa.py`
- [ ] Generator class extends `BaseGenerator[Article]` (TrainForge version)
- [ ] Template ported: article_qa (1 template)
- [ ] Validation rules ported (ARTICLE_QA_VALIDATION)
- [ ] Uses `MTGDataAccess.get_articles()` with limit parameter
- [ ] Filters articles with cleaned HTML content > 300 characters
- [ ] `build_prompt()` delegates to `build_article_qa_prompt()` with title and cleaned content (truncated to 2000 chars)
- [ ] `build_context()` ported for validation context
- [ ] `get_source_data()` ported to extract article title
- [ ] Templates defined in `templates.yaml` under `article_qa` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 4 in the old CLI (2,000 examples in phase4 mode)
- The `build_article_qa_prompt()` and `clean_html()` helpers in common.py also need porting
- Category is "article_qa"
- Generator does NOT require dry_run or trace_callback support in its constructor (unique among Phase 4 generators)
