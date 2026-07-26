# Implementation State

## Changes Made — 2026-07-24

### Bug Fixes
1. **color_staples.py**: Restored 3-sub-batch pattern — `get_data_batches()` now
   splits each color's cards into batches of 10 (up to 3 sub-batches per color).
2. **multi_card_usage.py**: Added `and c.description` filter to exclude combos
   without descriptions from data batches.
3. **staple_analysis.py**: Replaced `or` coalescing with explicit `None` check
   for `edhrecRank`/`edhrec_rank` fallback to avoid masking valid `0` values.

### New Test Files
4. **test_staple_analysis.py** — 11 tests: source category, data batches (3 cards
   = 3 batches), prompt with card name, edhrec_rank fallback, context metadata.
5. **test_salt_questions.py** — 11 tests: source category, batching (10 cards / 8
   per batch = 2 batches), prompt with salt theme, context with avg salt.
6. **test_color_staples.py** — 15 tests: source category, 30 cards × 6 colors =
   18 batches (3 sub-batches of 10 each), edge cases (empty colors, <10 cards),
   prompt with color name, context metadata.
7. **test_multi_card_usage.py** — 12 tests: source category, filters (≥2 cards +
   description), prompt includes all card names, context with card count.
8. **test_guide_qa.py** — 14 tests: source category, filters (content >300 chars),
   prompt with guide title and chapters, context metadata.

### New Generators (ported from old CLI)
9. **article_qa.py** — `ArticleQAGenerator(BaseGenerator[Article])`: fetches
   articles via `ds.get_articles(limit=100)`, strips HTML, filters content > 200
   chars, formats prompts with `{title}`, `{content}`, `{tags}` placeholders.
   Category: `article_qa`.
10. **rule_interactions.py** — `RuleInteractionsGenerator(BaseGenerator[tuple[dict, dict]])`:
    37 `INTERACTION_PAIRS` ported from old CLI, groups rules by section prefix,
    yields (rule1, rule2) tuples. Category: `rule_interactions`.

### New Test Files
11. **test_article_qa.py** — 13 tests: source category, content length filtering,
    HTML cleaning (tags stripped, entities decoded), limit=100 call, empty/short
    edge cases, prompt formatting, context metadata.
12. **test_rule_interactions.py** — 16 tests: `_extract_section` helper, source
    category, 37 pairs constant, pair building, short text filtering, limit=500
    call, empty/no-match edge cases, prompt with rules/task, context metadata.

Total: 29 new tests (88 total across all recent additions). All passing. Zero
regressions (166 MTG tests pass).
