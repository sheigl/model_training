# Changelog

### Bug fixes and test coverage for data-driven MTG generators — 2026-07-24

- Fixed `color_staples.py` to split each color's cards into 3 sub-batches of 10 for manageable prompt sizes
- Fixed `multi_card_usage.py` to filter out combos without descriptions
- Fixed `staple_analysis.py` to use explicit `None` check for `edhrecRank` fallback instead of `or` coalescing
- Added 5 test files (`test_staple_analysis.py`, `test_salt_questions.py`, `test_color_staples.py`, `test_multi_card_usage.py`, `test_guide_qa.py`) with 59 unit tests covering source category, batch structure, prompt building, and context metadata

### Article Q&A and Rule Interactions generators ported — 2026-07-24

- Ported `generate_article_qa.py` from old CLI to `ArticleQAGenerator` (`article_qa.py`): fetches articles, strips HTML, filters by content length > 200 chars, formats prompts with `{title}`, `{content}`, `{tags}` placeholders
- Ported `generate_rule_interactions.py` from old CLI to `RuleInteractionsGenerator` (`rule_interactions.py`): 37 `INTERACTION_PAIRS` defining section-to-section rule interactions, groups rules by section prefix, yields (rule1, rule2) tuple batches
- Added 29 unit tests across both generators covering data batching, prompt building, context metadata, and HTML cleaning
- Registered both generators in MTG domain plugin and generators `__init__.py`
