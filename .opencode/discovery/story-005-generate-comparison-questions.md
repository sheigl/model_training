# Story: GenerateComparisonQuestions Enhancement

## User Story
As a **player choosing between similar cards**, I want **detailed mechanical comparisons with context-aware recommendations**, so that **I pick the right card for my specific deck and strategy**.

## Context
Current `GenerateComparisonQuestions` pairs cards by 8 regex patterns, 1 template, ignores card types (creature vs artifact critical), EDHREC, prices, legalities, rulings. Enhanced version uses 4 templates with rich joined data and HARD REJECT validation like combos/rules generators.

## Acceptance Criteria
- [ ] **Data Integration**: Full card data for BOTH cards including EDHREC rank/salt/tags, prices (USD), legalities, rulings, keywords, subtypes, supertypes
- [ ] **Template System**: 4 templates with distinct `task_instruction`:
  - `power_level`: "Compare these cards for competitive Commander. Which is stronger and in what metas?"
  - `mana_efficiency`: "Compare mana efficiency. Which gives better value per mana invested?"
  - `commander_suitability`: "Compare for a [commander] deck. Which fits the strategy and color identity better?"
  - `synergy_potential`: "Compare synergy with [archetype/mechanic]. Which enables more combos/interactions?"
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST correctly identify card types for BOTH cards
  - If types differ, MUST explain implications (summoning sickness, removal vulnerability, etc.)
  - Casting costs MUST be accurately compared (total mana, colored vs colorless)
  - Net mana production MUST be calculated correctly (cost X produces X = net zero)
  - ALL key abilities from oracle text MUST be mentioned for both cards
  - Context-dependent recommendation (not "X is always better")
  - NO markdown formatting
  - Answer length: 200-500 characters
  - Price comparison when relevant
- [ ] **Context Building**: Pass to LLM: both cards' full details, commander/archetype context, template instruction, EDHREC comparison (rank, salt, tags), price comparison
- [ ] **Target Count**: 2,000 validated examples
- [ ] **MongoDB Queries**:
  ```python
  # Find pairs by effect category (text regex + edhrecTags)
  # Join prices, legalities, rulings for both
  # Filter: both commander legal
  # Ensure diverse type combos (creature vs non-creature, etc.)
  # Pair cards with similar EDHREC rank (fair comparison)
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- `CARD_COMPARISON_INSTRUCTIONS` in constants.py has excellent rules - promote to HARD REJECT
- Card type difference is #1 error - MUST validate
- Net mana math: {3}→{C}{C}{C}=net 0, {2}→{C}{C}=net +1/turn
- Salt > 1.5 = controversial - mention if relevant
- Commander suitability needs CR 903.4 color identity check
- Synergy template should reference Commander Spellbook combo data