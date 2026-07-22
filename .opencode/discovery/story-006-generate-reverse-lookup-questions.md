# Story: GenerateReverseLookupQuestions Enhancement

## User Story
As a **player searching for cards by function**, I want **accurate reverse lookup answers listing specific cards that do what I need**, so that **I find the right card without knowing its name**.

## Context
Current `GenerateReverseLookupQuestions` uses 18 hardcoded regex patterns on card text only, ignores EDHREC, prices, legalities, keywords. Enhanced version uses keywords collection for mechanic taxonomy, EDHREC for popularity, 4 templates.

## Acceptance Criteria
- [ ] **Data Integration**: `mtg_json.cards` joined with `keywords` collection + EDHREC fields + `cardPrices` + `cardLegalities` + `cardRulings`
- [ ] **Template System**: 4 templates with distinct `task_instruction`:
  - `mechanic_search`: "Find cards with the [mechanic/keyword] ability. List the best options for Commander."
  - `tribal_search`: "Find cards that support the [creature type] tribal archetype in Commander."
  - `utility_search`: "Find utility cards that [function] for a [color/archetype] Commander deck."
  - `commander_search`: "Find cards with [function] legal in [commander]'s color identity."
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST list 3-5 specific cards with names
  - Each card MUST include mana cost, type, and 1-sentence why it matches
  - Mechanic template: Cards MUST have the keyword (validate against `keywords` collection)
  - Tribal template: Cards MUST reference creature type in text or be that type
  - Utility template: Cards MUST be Commander legal, match color identity if specified
  - Commander template: ALL cards MUST be legal in commander's color identity (CR 903.4)
  - Cards SHOULD be ordered by EDHREC rank/popularity
  - NO markdown formatting
  - Answer length: 150-400 characters
- [ ] **Context Building**: Pass to LLM: matching cards with full details, template instruction, search intent, commander context if applicable
- [ ] **Target Count**: 3,000 validated examples
- [ ] **MongoDB Queries**:
  ```python
  # Mechanic: Join cards with keywords collection, filter by keyword
  # Tribal: Regex on subtypes + text mentioning creature type, filter by edhrecTags
  # Utility: Text regex + color identity filter + edhrecTags for archetype
  # Commander: Color identity subset check (CR 903.4) + function regex
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- `keywords` collection provides canonical mechanic names (flash, ward, proliferate, etc.)
- EDHREC `tags` crucial: "ramp", "removal", "card-draw", "board-wipe", "counterspell", "tutor", "graveyard-hate", "protection", "haste-enabler", "flying-enabler", "copy-effect", "mana-doubler", "combat-trick"
- Tribal: check both `subtypes` array and oracle text for creature type mentions
- Price data enables "budget" sub-queries
- Rulings important for complex keywords (layers, replacement effects)