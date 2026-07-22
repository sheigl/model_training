# Story: Unified Data Access Layer

## User Story
As a **synthetic data generator developer**, I want a **single unified data access class** that provides typed access to all MongoDB collections with pre-built joins (cards+EDHREC+prices+legalities+rulings, combos+cards+rulings, commanders+tags, etc.), so that **generators don't write raw MongoDB queries and can access rich, joined data through clean Python methods**.

## Context
Currently, each generator writes its own raw `pymongo` queries with hardcoded collection names, field projections, and manual joins. This leads to:
- Inconsistent field mappings (e.g., `colorIdentity` vs `colors` vs `color_identity`)
- Missed join opportunities (cards never joined with EDHREC tags, prices, legalities, rulings)
- 21 of 23 generators only query `cards` collection, ignoring 258K rulings, 1M+ prices, 108K legalities, keywords, etc.
- No type safety or IDE autocomplete for MongoDB documents

## Acceptance Criteria
- [ ] Class `MTGDataAccess` in `training_data/generate_synthetic_data/data_access.py`
- [ ] Single MongoDB client connection managed internally (connection pooling)
- [ ] Typed dataclasses/Pydantic models for all returned data (from Story 3)
- [ ] Pre-built join methods returning enriched objects:

### Core Join Methods
- [ ] `get_cards_enriched(filters, limit)` → Cards with EDHREC rank/salt/tags + prices + legalities + rulings + keywords
- [ ] `get_combos_enriched(filters, limit)` → Combos with full card details + rulings for each piece
- [ ] `get_commanders_enriched(filters, limit)` → Commanders with EDHREC tags, salt, deck counts, color identity
- [ ] `get_cards_by_keyword_mechanic(keyword, limit)` → Cards with specific keyword/mechanic (from keywords collection)
- [ ] `get_cards_by_archetype(archetype, limit)` → Cards tagged with EDHREC archetype
- [ ] `get_price_history(card_name)` → Price data from cardPrices collection
- [ ] `get_rulings_for_card(card_name)` → All rulings from cardRulings collection (258K docs)
- [ ] `get_legalities_for_card(card_name)` → Legalities from cardLegalities collection (108K docs)

### Aggregation/Analytics Methods
- [ ] `get_top_cards_by_edhrec_rank(color_identity, limit)` → Top EDHREC cards for color identity
- [ ] `get_budget_alternatives(expensive_card, max_price, limit)` → Cheaper cards with similar effects
- [ ] `get_synergy_partners(card_name, limit)` → Cards appearing in combos with given card
- [ ] `get_commander_staples(color_identity, min_decks, limit)` → Cards in >X% of decks for color identity
- [ ] `get_format_legalities(format_name, limit)` → Cards legal in specific format

### Utility Methods
- [ ] `calculate_color_identity(mana_cost, text, color_indicator)` → Compute color identity per CR 903.4
- [ ] `get_card_by_name(name)` → Single card with all enrichments
- [ ] `search_cards_text(regex, filters, limit)` → Full-text regex search with filters

## MongoDB Collections Used
| Database | Collection | Documents | Key Fields |
|----------|------------|-----------|------------|
| mtg_json | cards | ~108K | name, text, type, manaCost, colors, colorIdentity, subtypes, supertypes, rarity, legalities, edhrecRank, edhrecSalt, edhrecTags, keywords |
| mtg_json | cardRulings | ~258K | uuid, date, text |
| mtg_json | cardPrices | ~1M+ | uuid, paper, foil, usd, usd_foil, eur, eur_foil, tix |
| mtg_json | cardLegalities | ~108K | uuid, format, legality |
| mtg_json | keywords | ~200 | keyword, description, reminderText |
| mtg_json | sets | ~300 | code, name, releaseDate, type |
| commander_spellbook | variants | ~76K | uses[], produces[], description, status |
| edhrec | articles | ~500 | title, content, tags, author |
| edhrec | guides | ~26 | title, guide (chapters) |
| edhrec | commanders | ~2K | name, color_identity, tags, num_decks, salt |
| mtg_rules | rules | ~3K | rule_number, section, text, category |
| mtg_rules | glossary | ~200 | term, definition |
| mtg_archetypes | archetypes | ~50 | name, description, key_cards, strategy |

## Template Definitions
N/A - This is a data access layer, not a generator.

## Validation Criteria
- [ ] All methods return typed Pydantic models (not raw dicts)
- [ ] Methods handle missing collections gracefully (return empty list, log warning)
- [ ] Connection pooling configured (maxPoolSize=50)
- [ ] Query timeout default 30s, configurable
- [ ] Indexes verified on startup (create if missing)
- [ ] Context manager support (`with MTGDataAccess() as db:`)

## Dependencies
- Story 3 (Extended Data Models) - provides the Pydantic models returned by this layer

## Priority: High
## Story Points: 13

## Notes
- This is the SINGLE SOURCE OF TRUTH for all MongoDB access in the generation pipeline
- Generators should NEVER import `pymongo` directly after this is complete
- Join methods should use MongoDB aggregation pipelines for efficiency
- Consider caching frequently accessed data (commanders, keywords) in memory
- EDHREC data (tags, salt, rank) is in `mtg_json.cards` as embedded fields, not separate collections