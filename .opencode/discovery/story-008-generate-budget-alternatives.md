# Story: GenerateBudgetAlternatives Enhancement

## User Story
As a **budget-conscious Commander player**, I want **specific cheaper alternatives with price comparisons and mechanical trade-offs**, so that **I can build competitive decks without expensive staples**.

## Context
Current `GenerateBudgetAlternatives` uses 4 hardcoded patterns (ramp, removal, card draw, tutors), finds expensive rare/mythic cards and cheaper uncommon/common by rarity proxy (not real price), 1 template. Enhanced version uses real USD prices from `cardPrices`, EDHREC inclusion %, legalities, rulings, 4 templates.

## Acceptance Criteria
- [ ] **Data Integration**: `mtg_json.cards` + `cardPrices` (real USD) + EDHREC inclusion % + `cardLegalities` + `cardRulings`
- [ ] **Template System**: 4 templates with distinct `task_instruction`:
  - `pauper_budget`: "Find the best Pauper-legal (common only) alternatives to [expensive card]."
  - `budget_optimized`: "Find the best cards under $5 that replace [expensive card]. Compare mechanical trade-offs."
  - `proxy_friendly`: "Find cards under $15 that are commonly proxied for [expensive card]. Explain play pattern differences."
  - `upgrade_path`: "Show the upgrade path from [budget card] to [expensive card]. What do you gain at each price tier?"
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST list 2-3 specific alternative cards with names
  - Each alternative MUST include USD price (from `cardPrices.usd`)
  - Pauper template: ALL cards MUST be common rarity AND Pauper legal
  - Budget template: ALL cards MUST be under $5 USD
  - Proxy template: ALL cards MUST be under $15 USD
  - Upgrade template: MUST show 3 tiers (budget → mid → premium) with prices
  - MUST explain mechanical trade-offs (what you lose/gain vs expensive card)
  - MUST mention EDHREC inclusion % for context on popularity
  - NO markdown formatting
  - Answer length: 200-500 characters
- [ ] **Context Building**: Pass to LLM: expensive card full details (name, cost, type, text, price, EDHREC rank, inclusion %, legalities, rulings), candidate alternatives with same details, template instruction
- [ ] **Target Count**: 2,000 validated examples
- [ ] **MongoDB Queries**:
  ```python
  # Expensive cards: price.usd > 20, commander legal, edhrecRank > 0
  # Pauper: rarity = common, legalities.pauper = legal, similar function (text regex)
  # Budget: price.usd < 5, commander legal, similar function, sort by edhrecRank
  # Proxy: price.usd 5-15, commander legal, similar function
  # Upgrade path: Find cards with same function at 3 price tiers
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- `cardPrices` collection has 1M+ docs with `usd`, `usd_foil`, `eur`, `tix` fields - use `usd` for budget
- EDHREC inclusion % = (num_decks_with_card / total_decks_for_commander) * 100 - approximate from `edhrecRank`
- Rarity is NOT a price proxy - use real USD prices
- Legalities: check `legalities.pauper`, `legalities.commander`
- Rulings important for explaining functional differences (e.g., "enters tapped" vs "enters untapped")
- Upgrade path template unique: starts from budget card, shows progression
- Common expensive cards to target: Mana Crypt, Mana Drain, Imperial Seal, Gaea's Cradle, The Tabernacle at Pendrell Vale, Lion's Eye Diamond, etc.