# Story: GenerateColorIdentityQuestions Enhancement

## User Story
As a **Commander player building a deck**, I want **accurate color identity legality answers with rule explanations**, so that **I know exactly what cards I can and cannot play in my commander's color identity**.

## Context
Current `GenerateColorIdentityQuestions` samples 500 cards and 100 commanders, has bugs (undefined variables `card_name`, `commander_name`, `card_colors`, `commander_colors`, `is_legal`), 1 template. Enhanced version uses ALL EDHREC commanders weighted by deck count, full card legalities, CR 903.4, 4 templates.

## Acceptance Criteria
- [ ] **Data Integration**: `mtg_json.cards` (full color identity, mana cost, color indicator) + `edhrec.commanders` (ALL commanders with deck counts, color identity) + `cardLegalities` + CR 903.4 rules
- [ ] **Template System**: 4 templates with distinct `task_instruction`:
  - `mono_color`: "Explain color identity rules for mono-colored commanders. Can [card] be played in [commander]?"
  - `two_color`: "Explain color identity for two-color commanders. Is [card] legal in [commander]?"
  - `three_color`: "Explain color identity for three-color (wedge/shard) commanders. Why is [card] legal/illegal in [commander]?"
  - `five_color`: "Explain color identity for five-color commanders. What restrictions still apply to [card] in [commander]?"
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST correctly determine legality (YES/NO) per CR 903.4
  - MUST explain color identity calculation: mana symbols in cost + color indicator + color-defining ability
  - MUST mention commander's color identity explicitly
  - MUST explain WHY legal/illegal (which mana symbol violates identity)
  - For legal cards: MUST mention any color identity nuances (hybrid, phyrexian, colorless)
  - For illegal cards: MUST specify which color symbol is not in commander's identity
  - NO markdown formatting
  - Answer length: 150-400 characters
  - NO rule number references (explain conversationally)
- [ ] **Context Building**: Pass to LLM: card full details (mana cost, color identity, color indicator, text), commander full details (name, color identity, deck count), legality determination, template instruction
- [ ] **Target Count**: 2,000 validated examples
- [ ] **MongoDB Queries**:
  ```python
  # All EDHREC commanders with num_decks > 0, weighted by num_decks
  # Cards: all commander-legal cards with colorIdentity, manaCost, colorIndicator
  # Pair cards with commanders ensuring diverse color identity combos
  # Include edge cases: hybrid mana, phyrexian mana, colorless, color indicators
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- CR 903.4: Color identity = mana symbols in cost + color indicator + characteristic-defining abilities
- Hybrid mana: counts as BOTH colors for identity (e.g., {W/U} = white AND blue)
- Phyrexian mana: counts as its color (e.g., {W/P} = white)
- Colorless cards (no colored symbols, no indicator) = colorless identity = legal in any deck
- Color indicator (e.g., on back face of DFCs, or cards like Dryad Arbor) sets identity
- EDHREC `commanders` collection has `color_identity` array and `num_decks` for weighting
- Weighted sampling: popular commanders (Atraxa, Edgar Markov, Urza) should appear more often
- Edge cases to cover: Extort (hybrid in reminder text only - doesn't count), Devoid (colorless identity despite colored cost), Transformed DFCs