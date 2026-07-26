# Implementation Context

## Recent Changes

### 2026-07-24: Ported 9 more MTG generators from old CLI to TrainForge

- **card_search_queries.py**: `GenerateCardSearchQueries(CardWithMetadata)` — 20 search patterns (Green Ramp, Zombie Tokens, Treasure Tokens, etc.). Fetches via `get_cards_enriched()`.
- **comparison_questions.py**: `GenerateComparisonQuestions(tuple[CardWithMetadata, CardWithMetadata])` — 10 comparison categories, 3 pairing strategies (adjacent rank, same CMC, different colors). Fetches via `get_cards_enriched()`.
- **reverse_lookup_questions.py**: `GenerateReverseLookupQuestions(dict)` — 23 effect description patterns. Fetches via `search_cards_text()`.
- **synergy_questions.py**: `GenerateSynergyQuestions(CardWithMetadata)` — fetches top-ranked cards then finds synergy partners via `get_synergy_partners()`.
- **commander_building.py**: `GenerateCommanderBuilding(CommanderWithTags)` — 12 archetypes with keywords and fallback key cards. Fetches via `get_commanders_enriched()`.
- **combo_queries.py**: `ComboQueriesGenerator(ComboWithCards)` — combo_query category. Fetches via `get_combos_enriched()`. Prompt includes card details, combo description, produces.
- **budget_alternatives.py**: `BudgetAlternativesGenerator(tuple[CardWithMetadata, list[CardWithMetadata]])` — budget category. Fetches expensive cards via `get_cards_enriched()` + alternatives via `get_budget_alternatives()`.
- **color_identity_questions.py**: `ColorIdentityQuestionsGenerator(dict)` — color_identity category. Fetches commanders via `get_commanders_enriched()` + cards via `get_cards_enriched()`. Includes mana cost CI calculation, hybrid mana, 903.4 rule.
- **quick_guidelines.py**: `QuickGuidelinesGenerator(dict)` — guidelines category. Fetches cards with EDHREC rank via `get_cards_enriched()`. Derives card roles (removal, ramp, draw, etc.) from oracle text.
- All 4 use enriched `MTGDataAccess` via `self.domain.get_data_source()`.
- All registered in `generators/__init__.py` and `domains/mtg/__init__.py`.
- 155 core tests pass, all 4 files compile clean.

### Before (2026-07-24): 21 generators registered

See CHANGELOG.md for full history.
