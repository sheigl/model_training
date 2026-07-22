# Story: GenerateQuickGuidelines Enhancement (Data-Driven)

## User Story
As a **Commander player seeking deckbuilding guidance**, I want **data-driven guidelines backed by EDHREC top cards and real game statistics**, so that **the advice reflects actual competitive play patterns, not just heuristics**.

## Context
Current `GenerateQuickGuidelines` uses 15 hardcoded guidelines with LLM variations - ZERO data grounding. This NEW data-driven version uses EDHREC top cards by archetype + game stats to generate guidelines reflecting real deckbuilding patterns.

## Acceptance Criteria
- [ ] **Data Integration**: `edhrec.articles`/`guides` (archetype definitions) + `mtg_json.cards` (EDHREC top cards by archetype tags) + `mtg_training` (game stats: win rates, avg game length, card draw per turn, etc.)
- [ ] **Template System**: 5 templates with distinct `task_instruction`:
  - `land_count`: "Based on EDHREC data for [archetype] decks, what's the optimal land count and why?"
  - `ramp_package`: "What ramp cards do top [archetype] decks run? How many ramp sources and what types?"
  - `removal_suite`: "What removal do successful [archetype] decks play? How many pieces and what types?"
  - `card_advantage`: "How do winning [archetype] decks generate card advantage? What are the top engines?"
  - `win_con_density`: "How many win conditions do competitive [archetype] decks run? What are they?"
- [ ] **Validation Criteria** (HARD REJECT rules):
  - Answer MUST cite specific cards from EDHREC top cards for that archetype
  - Answer MUST include quantitative data (e.g., "37 lands", "8-10 ramp", "35% run Rhystic Study")
  - Answer MUST reference archetype by name
  - Land count: MUST give specific number range (not "it depends")
  - Ramp: MUST distinguish land ramp vs artifact ramp vs ritual
  - Removal: MUST categorize (creature, artifact/enchantment, board wipe, counterspell)
  - Card advantage: MUST distinguish draw, impulse draw, graveyard recursion, monarch
  - Win con: MUST name 2-3 specific cards/combos
  - NO generic advice without data backing
  - NO markdown formatting
  - Answer length: 200-500 characters
- [ ] **Context Building**: Pass to LLM: archetype name, top 20 EDHREC cards for archetype (with deck counts), relevant game stats from mtg_training, template instruction
- [ ] **Target Count**: 2,000 validated examples (400 per template × 5 templates)
- [ ] **MongoDB Queries**:
  ```python
  # Archetypes from edhrec.articles/guides tags
  # Top cards per archetype: cards with matching edhrecTags, sort by edhrecRank
  # Game stats: mtg_training collection with win rates by archetype, avg lands, avg ramp, etc.
  # If mtg_training lacks stats, derive from EDHREC decklists (avg lands, ramp count, etc.)
  ```

## Dependencies
- Story 001: Shared Base Generator Class
- Story 002: Unified Data Access Layer
- Story 003: Extended Data Models

## Priority: High
## Story Points: 13

## Notes
- EDHREC archetype tags: "aristocrats", "blink", "control", "combo", "aggro", "midrange", "landfall", "spellslinger", "tokens", "voltron", "group-hug", "stax", "superfriends", "tribal-elves", "tribal-goblins", etc.
- `mtg_training` database may have game simulation stats - if not, compute from EDHREC decklist data
- Key metrics to derive: avg land count, avg ramp count, avg removal count, avg card draw count, win con count, avg CMC, color distribution
- Guidelines MUST be archetype-specific, not generic "Commander" advice
- Example data-driven answer: "Cedh control decks (Atraxa, Tivit) run 30-32 lands with 12+ ramp (Mana Crypt, Jeweled Lotus, Sol Ring, 5+ mana rocks). They run 8-10 removal (Swords, Path, Cyclonic Rift) and 6-8 card advantage (Rhystic Study, Mystic Remora, Necropotence). Win cons: 2-3 (Thassa's Oracle + Consultation, Dockside loops)."
- This REPLACES the 15 hardcoded guidelines entirely