# Story: GenerateSynergyQuestions Enhancement

## User Story
As a **Magic player building around a key card**, I want **specific synergy explanations with mechanical reasoning**, so that **I understand WHY cards work together and can discover new interactions**.

## Context
Current `GenerateSynergyQuestions` uses Commander Spellbook combos only (top 200 cards by combo count) and finds synergy cards from those combos. It ignores EDHREC tags, keywords, rulings, and has only 1 generic template. The enhanced version uses 4 templates with rich data from combos, EDHREC, keywords, and rulings.

## Acceptance Criteria
- [ ] **Data Integration**: `commander_spellbook.variants` (combos) + `mtg_json.cards` (EDHREC tags, keywords) + `cardRulings` + `keywords` collection
- [ ] **Template System**: 4 templates with distinct `task_instruction`:
  - `combo_piece`: "Explain how [card] functions as a combo piece. What combos does it enable and what does it need?"
  - `value_engine`: "Explain how [card] generates ongoing value. What cards amplify its value engine?"
  - `tribal_synergy`: "Explain how [card] synergizes with [creature type] tribal strategies. What tribal payoffs and enablers work with it?"
  - `mechanic_synergy`: "Explain how [card] synergizes with the [mechanic/keyword] mechanic. What cards with [mechanic] work well with it?"
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST name 2-3 specific synergy cards
  - Each synergy MUST explain the MECHANICAL interaction (not just "they work well")
  - Combo template: MUST reference specific Commander Spellbook combo by name or card names
  - Value engine template: MUST explain the value loop (trigger → effect → repeat condition)
  - Tribal template: MUST reference creature type and tribal payoffs (lords, anthem, etc.)
  - Mechanic template: MUST reference keyword by name and explain interaction
  - NO vague statements like "good synergy" or "works well together"
  - NO markdown formatting
  - Answer length: 200-500 characters
- [ ] **Context Building**: Pass to LLM: target card full details, relevant combos (from Spellbook), EDHREC tags, keywords on card, rulings, top synergy cards with details, template instruction
- [ ] **Target Count**: 3,000 validated examples
- [ ] **MongoDB Queries**:
  ```python
  # Combo piece: Find combos using card, extract other pieces, get their details
  # Value engine: Find cards with same EDHREC tags (value, card-advantage, ramp)
  # Tribal: Find cards sharing creature type + tribal EDHREC tags
  # Mechanic: Find cards sharing keywords from keywords collection
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- Commander Spellbook `variants` collection has `uses` (cards in combo) and `produces` (results)
- EDHREC `tags` on cards indicate archetype: "aristocrats", "blink", "tokens", "spellslinger", "landfall", "energy", "proliferate", "graveyard", "artifact", "enchantment", "planeswalker", "tribal-elves", "tribal-goblins", "tribal-zombies", etc.
- Keywords collection provides canonical mechanic names for mechanic_synergy template
- Rulings critical for explaining HOW the interaction works (layers, timing, replacement effects)
- For combo_piece: distinguish between "card is the engine" vs "card is the payoff" vs "card is the enabler"