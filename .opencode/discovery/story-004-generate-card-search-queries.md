# Story: GenerateCardSearchQueries Enhancement

## User Story
As a **player looking for cards by function**, I want **natural language search that returns the best cards with explanations**, so that **I can find cards for my deck without knowing exact card names**.

## Context
Current `GenerateCardSearchQueries` uses 7 hardcoded regex patterns on card text only, 1 template, and ignores EDHREC rank, prices, legalities, keywords, and rulings. Enhanced version uses 5 templates with rich data from cards + EDHREC + prices + legalities + keywords.

## Acceptance Criteria
- [ ] **Data Integration**: `mtg_json.cards` joined with EDHREC rank/salt/tags + `cardPrices` (USD) + `cardLegalities` + `keywords` collection + `cardRulings`
- [ ] **Template System**: 5 templates with distinct `task_instruction`:
  - `competitive`: "Find the most competitive cards for [function] in Commander. Rank by EDHREC inclusion and win rate."
  - `budget`: "Find the best budget cards for [function] under $5. Prioritize price-to-performance."
  - `commander_specific`: "Find cards for [function] that work specifically with [commander]'s strategy and color identity."
  - `thematic`: "Find cards for [function] that fit a [theme] theme (tribal, mechanic, flavor)."
  - `beginner`: "Find simple, easy-to-understand cards for [function] suitable for new Commander players."
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST list 3-5 specific cards with names
  - Each card MUST include WHY it's good for the function (mechanical explanation)
  - Competitive template: MUST reference EDHREC rank/inclusion % for each card
  - Budget template: MUST state USD price for each card (validate < $5)
  - Commander-specific: ALL cards MUST be legal in commander's color identity
  - Thematic: MUST explain thematic fit (creature type, mechanic, flavor)
  - Beginner: MUST avoid complex interactions, prioritize simple text
  - NO markdown formatting
  - Answer length: 200-500 characters
- [ ] **Context Building**: Pass to LLM: function description, top 15 candidate cards (full details: name, cost, type, text, EDHREC rank, price, legalities, keywords, rulings), commander context (if applicable), theme keywords, template instruction
- [ ] **Target Count**: 3,000 validated examples
- [ ] **MongoDB Queries**:
  ```python
  # Competitive: edhrecRank > 0, commander legal, sort by rank asc, limit 15
  # Budget: price.usd < 5, commander legal, edhrecRank > 0, sort by rank asc
  # Commander-specific: colorIdentity subset of commander, edhrecTags match commander tags
  # Thematic: keywords/subtypes match theme, commander legal
  # Beginner: simple text (low word count), common/uncommon, commander legal
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- EDHREC `edhrecRank` lower = more popular (rank 1 = most played)
- `edhrecTags` indicate archetype: "ramp", "card-draw", "removal", "board-wipe", "counterspell", "tutor", "combo-piece", "wincon", "protection", "graveyard", "tokens", "aristocrats", "blink", "landfall", "spellslinger", "voltron", "group-hug", "stax", "superfriends"
- `keywords` collection provides canonical mechanic names for thematic searches
- `cardPrices.usd` for budget validation
- `cardLegalities.commander` must be "legal"
- Rulings important for explaining complex interactions in competitive template