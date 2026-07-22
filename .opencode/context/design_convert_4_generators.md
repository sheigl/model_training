# Design: Convert 4 Topic-Based Generators to BaseGenerator[str]

## Overview
Convert the final 4 old-pattern generators (`GenerateMetaKnowledge`, `GenerateCommanderKnowledge`, `GenerateTerminologyQuestions`, `GenerateArchetypes`) to the `BaseGenerator[str]` pattern, achieving full consistency across all topic-based generators.

## User Story Reference
The user story describes converting 4 remaining topic-based generators to use the BaseGenerator pattern. These are the last generators using the old constructor signature and generator-specific methods (e.g., `.generate_meta_knowledge()` instead of `.generate()`).

## Architecture Decisions

### 1. All 4 generators use `BaseGenerator[str]`
**Decision**: The generic type parameter is `str` — the topic/situation/archetype/term name string.
**Rationale**: Follows the exact same pattern as the 4 already-converted topic generators (deckbuilding_theory, game_theory, commander_building, rules_scenarios). The `str` parameter is the single-item data batch — a topic name that gets looked up against a class-level list to find its context.

### 2. Two templates per generator for quality variation
**Decision**: Each generator defines 2 templates with distinct intents (weighted equally).
**Rationale**: This is the established pattern for topic-based generators. Two templates provide diversity in generated Q&A without over-engineering. Templates typically are:
- `general_advice`: Broad knowledge questions
- `domain_specific`: Concrete examples, scenarios, or deep dives

### 3. Preserve all original data exactly
**Decision**: All topics/terms/archetypes must be preserved as class-level constants.
**Rationale**: Ensures backward compatibility — same training data coverage as before. No topics can be lost or altered.

### 4. No `data_access` needed
**Decision**: These are topic-based generators with hardcoded data; they don't need `MTGDataAccess`.
**Rationale**: The data is embedded in the class as constants (topics, terms, archetypes). No MongoDB queries needed.

### 5. `GenerateTerminologyQuestions` changes behavior (improvement)
**Decision**: The old pattern creates Q&A pairs directly (question = "What is X?", answer = definition) with no LLM generation. The new pattern uses LLM generation via templates, producing varied questions and richer answers with examples.
**Rationale**: This is a quality improvement — LLM-generated terminology Q&A will have varied question phrasing and more detailed answers. The old pattern was essentially a "template copy" that wasted a generator slot.

### 6. `GenerateCommanderKnowledge` breaks monolithic topic into sub-topics
**Decision**: The old pattern generates 20 Q&A pairs in a single LLM call about "Commander rules." The new pattern breaks this into ~8 Commander sub-topics cycled through with 2 templates each.
**Rationale**: The old `build_commander_prompt()` produces 20 Q&A at once, which is inconsistent with the per-topic pattern. Breaking into sub-topics allows focused generation, better validation, and template variation.

---

## Files to Create/Modify

### Modified Files

| File | Changes | Reason |
|------|---------|--------|
| `generate_meta_knowledge.py` | Complete rewrite to `BaseGenerator[str]` | Convert to new pattern |
| `generate_commander_knowledge.py` | Complete rewrite to `BaseGenerator[str]` | Convert to new pattern |
| `generate_terminology_questions.py` | Complete rewrite to `BaseGenerator[str]` | Convert to new pattern |
| `generate_archetypes.py` | Complete rewrite to `BaseGenerator[str]` | Convert to new pattern |
| `main.py` | Update 4 generator instantiation blocks | Use BaseGenerator constructor + `.generate()` |

### New Files

| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `test_generate_meta_knowledge.py` | Unit tests for GenerateMetaKnowledge | Templates, data batches, prompts, context |
| `test_generate_commander_knowledge.py` | Unit tests for GenerateCommanderKnowledge | Templates, data batches, prompts, context |
| `test_generate_terminology_questions.py` | Unit tests for GenerateTerminologyQuestions | Templates, data batches, prompts, context |
| `test_generate_archetypes.py` | Unit tests for GenerateArchetypes | Templates, data batches, prompts, context |

---

## Task Breakdown (Ordered by Dependency)

### Task 1: Convert GenerateMetaKnowledge
- **Files**: `generate_meta_knowledge.py`
- **Description**: Rewrite class to extend `BaseGenerator[str]`
- **Acceptance Criteria**: Class inherits `BaseGenerator[str]`, defines TEMPLATES, implements all abstract methods, no old imports

### Task 2: Convert GenerateCommanderKnowledge
- **Files**: `generate_commander_knowledge.py`
- **Description**: Rewrite class to extend `BaseGenerator[str]`, break monolithic topic into sub-topics
- **Acceptance Criteria**: Class inherits `BaseGenerator[str]`, 6-8 Commander sub-topics, 2 templates, all abstract methods implemented

### Task 3: Convert GenerateTerminologyQuestions
- **Files**: `generate_terminology_questions.py`
- **Description**: Rewrite class to extend `BaseGenerator[str]`, change from direct QA creation to LLM generation
- **Acceptance Criteria**: Class inherits `BaseGenerator[str]`, 20 terms preserved, 2 templates, LLM generation

### Task 4: Convert GenerateArchetypes
- **Files**: `generate_archetypes.py`
- **Description**: Rewrite class to extend `BaseGenerator[str]`, remove pymongo/ScryfallMongo dependencies
- **Acceptance Criteria**: Class inherits `BaseGenerator[str]`, 10 archetypes preserved, 2 templates, no raw pymongo

### Task 5: Update main.py
- **Files**: `main.py`
- **Description**: Update 4 generator instantiation blocks to use new constructor pattern
- **Acceptance Criteria**: All 4 use keyword args, call `.generate()`, support `dry_run`

### Task 6: Write unit tests
- **Files**: `test_generate_meta_knowledge.py`, `test_generate_commander_knowledge.py`, `test_generate_terminology_questions.py`, `test_generate_archetypes.py`
- **Description**: Comprehensive tests for all 4 converted generators
- **Acceptance Criteria**: Tests pass, cover templates/data batches/prompts/context/source_category

---

## Generator Designs

### 1. GenerateMetaKnowledge

**Data type**: `str` (topic name)

**Class-level data** (preserved from old code):
```python
TOPICS = [
    (
        "cEDH viability and what separates competitive from casual",
        "cEDH decks win on turns 3-5, use fast mana (Mana Crypt, Chrome Mox), run tutors, counterspells, and win through established combo lines. Power level 9-10."
    ),
    (
        "Commander power level scale (1-10)",
        "The 1-10 power level scale: 1-3 precon/kitchen table, 4-6 focused casual, 7-8 optimized synergy, 9 high power, 10 cEDH. How to self-assess your deck."
    ),
    # ... all 9 topics preserved exactly
]
```

**Templates** (2):
| Template ID | Intent | Validation Focus |
|-------------|--------|------------------|
| `general_advice` | Broad meta knowledge Q&A | Actionable advice, 3-5 sentences, specific knowledge |
| `meta_deep_dive` | Deep competitive analysis | Specific card/strategy references, power level reasoning |

**Prompt building**: Uses existing `build_meta_knowledge_prompt(topic, context)` from common.py, wrapped in the standard MTG_NOTATION_LEGEND + `<task>` block.

**Source category**: `"meta_knowledge"`

**Validation context**:
```
Category: meta_knowledge
Template: {template_id}
Topic: {topic}
Context: {context}
```

---

### 2. GenerateCommanderKnowledge

**Data type**: `str` (sub-topic name)

**Class-level data** (NEW — broken from monolithic topic):
```python
COMMANDER_SUBTOPICS = [
    (
        "deck construction rules",
        "100-card singleton, exactly 100 cards including commander, no sideboard, commander determines color identity, basics only from outside game."
    ),
    (
        "commander tax",
        "Each time commander is cast from command zone, costs {2} more. Tax is cumulative. Applies to all spell-based commanders."
    ),
    (
        "commander damage",
        "21 combat damage from a single commander to a player loses that game. Commander must be commanded by the player who dealt it. Resets if commander changes zones."
    ),
    (
        "command zone",
        "Commander starts in command zone. Goes to command zone from any zone (owner's choice for graveyard/exile). Not cast from library, hand, or battlefield."
    ),
    (
        "color identity restrictions",
        "Cards in deck must only use mana symbols in commander's color identity. Hybrid, Phyrexian, color indicators all count. Basic lands only from outside."
    ),
    (
        "multiplayer rules",
        "Typically 4 players. Last player standing wins. Political deals, archenemy dynamics, kingmaking considerations. Turn order matters for threat assessment."
    ),
    (
        "partner and background commanders",
        "Partner allows 2 commanders if both have 'Partner'. Background enchantment commanders pair with a creature that has 'Choose a Background'. Both count for color identity."
    ),
    (
        "companion and wish effects",
        "Companion restrictions apply from outside the game. Wish effects can only get cards from outside in casual. Commander's Handbook / Rule 903.9 governs this."
    ),
]
```

**Templates** (2):
| Template ID | Intent | Validation Focus |
|-------------|--------|------------------|
| `general_advice` | Commander rules explanation | Accurate rules, conversational tone, no rule numbers |
| `example_driven` | Commander rules with examples | Concrete scenarios, card name references, specific interactions |

**Prompt building**: New inline prompt (old `build_commander_prompt()` was monolithic — generates 20 Q&A at once). Uses MTG_NOTATION_LEGEND + task instruction with topic context.

**Source category**: `"commander_rules"`

**Validation context**:
```
Category: commander_rules
Template: {template_id}
Topic: {topic}
Context: {context}
```

---

### 3. GenerateTerminologyQuestions

**Data type**: `str` (term name)

**Class-level data** (preserved from old code):
```python
TERMINOLOGY = [
    (
        "CEDH",
        "CEDH stands for Competitive EDH (Elder Dragon Highlander/Commander). It's Commander played at the highest power level with optimized decks, fast combos, and competitive mindset."
    ),
    (
        "pillow fort",
        "A 'pillow fort' is a defensive strategy that uses enchantments and effects to discourage opponents from attacking you, like Ghostly Prison, Propaganda, and Sphere of Safety."
    ),
    # ... all 20 terms preserved exactly
]
```

**Templates** (2):
| Template ID | Intent | Validation Focus |
|-------------|--------|------------------|
| `definition_focused` | What does this term mean? | Accurate definition, correct MTG context, proper terminology |
| `practical_application` | How does this work in practice? | Concrete examples, in-game scenarios, card references |

**Prompt building**: New inline prompt (no existing builder for terminology). Format:
```
You are a Magic: The Gathering expert. Generate 3 Q&A pairs about this MTG term.

Term: {term}
Definition: {definition}

Question styles to use:
- "What does '{term}' mean in Magic?"
- "How does {term} work in Commander?"
- "Give me an example of {term} in a game."

Output JSON array. Keep answers 2-4 sentences.
{OUTPUT_FORMAT}
```

**Source category**: `"terminology"`

**Note**: The old pattern created Q&A pairs directly without LLM generation (question = "What is X?", answer = definition). The new pattern uses LLM generation for varied, higher-quality output.

**Validation context**:
```
Category: terminology
Template: {template_id}
Term: {term}
Definition: {definition}
```

---

### 4. GenerateArchetypes

**Data type**: `str` (archetype name)

**Class-level data** (preserved from old code):
```python
ARCHETYPES = [
    ("Aggro", "A strategy focused on dealing quick damage with low-cost creatures."),
    ("Control", "A strategy that counters threats and wins through card advantage."),
    ("Combo", "A strategy that assembles specific card combinations to win instantly."),
    ("Midrange", "A strategy that plays efficient threats and disrupts opponents."),
    ("Stax", "A control strategy using resource denial and lock pieces."),
    ("Voltron", "A strategy that equips one commander to deal lethal commander damage."),
    ("Tokens", "A strategy that swarms the board with creature tokens."),
    ("Reanimator", "A strategy that puts powerful creatures into play from the graveyard."),
    ("Storm", "A strategy that casts many spells in one turn to win with a storm payoff."),
    ("Pillow Fort", "A defensive strategy that prevents opponents from attacking you."),
]
```

**Templates** (2):
| Template ID | Intent | Validation Focus |
|-------------|--------|------------------|
| `general_advice` | Archetype strategy Q&A | How it works, strengths/weaknesses, strategic depth |
| `example_driven` | Archetype with card examples | Specific card examples, key pieces, deck construction tips |

**Prompt building**: Uses existing `build_archetype_prompt(archetype, context)` from common.py, wrapped in MTG_NOTATION_LEGEND + `<task>` block.

**Source category**: `"archetype"`

**Validation context**:
```
Category: archetype
Template: {template_id}
Archetype: {archetype}
Context: {context}
```

---

## main.py Integration Changes

### Current (old pattern):
```python
# Meta Knowledge
if args.meta_knowledge > 0:
    GenerateMetaKnowledge(
        save_item,
        models,
        args.validation_pct,
        target_count=args.meta_knowledge,
        metrics=make_metrics("GenerateMetaKnowledge")
    ).generate_meta_knowledge()

# Commander Knowledge
if args.commander > 0:
    GenerateCommanderKnowledge(
        save_item,
        models,
        args.validation_pct,
        target_count=args.commander,
        metrics=make_metrics("GenerateCommanderKnowledge")
    ).generate_commander_knowledge()

# Terminology
if args.terminology > 0:
    GenerateTerminologyQuestions(
        save_item,
        models,
        args.validation_pct,
        target_count=args.terminology,
        metrics=make_metrics("GenerateTerminologyQuestions")
    ).generate_terminology_questions()

# Archetypes
if args.archetypes > 0:
    GenerateArchetypes(
        cards,
        archetypes,
        save_item,
        models,
        args.validation_pct,
        target_count=args.archetypes,
        metrics=make_metrics("GenerateArchetypes")
    ).generate_archetypes()
```

### New (BaseGenerator pattern):
```python
# Meta Knowledge
if args.meta_knowledge > 0:
    GenerateMetaKnowledge(
        models=models,
        validation_pct=args.validation_pct,
        target_count=args.meta_knowledge,
        save_item=save_item,
        metrics=make_metrics("GenerateMetaKnowledge"),
        dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
    ).generate()

# Commander Knowledge
if args.commander > 0:
    GenerateCommanderKnowledge(
        models=models,
        validation_pct=args.validation_pct,
        target_count=args.commander,
        save_item=save_item,
        metrics=make_metrics("GenerateCommanderKnowledge"),
        dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
    ).generate()

# Terminology
if args.terminology > 0:
    GenerateTerminologyQuestions(
        models=models,
        validation_pct=args.validation_pct,
        target_count=args.terminology,
        save_item=save_item,
        metrics=make_metrics("GenerateTerminologyQuestions"),
        dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
    ).generate()

# Archetypes
if args.archetypes > 0:
    GenerateArchetypes(
        models=models,
        validation_pct=args.validation_pct,
        target_count=args.archetypes,
        save_item=save_item,
        metrics=make_metrics("GenerateArchetypes"),
        dry_run=args.dry_run if hasattr(args, 'dry_run') else False,
    ).generate()
```

---

## Testing Strategy

### Test File Structure
Each test file follows the established pattern from `test_base_generator.py` and `test_generate_quick_guidelines.py`:

```python
"""Unit tests for Generate{GeneratorName}."""

import json
from unittest.mock import MagicMock, Mock, patch
from typing import Iterator

import pytest

from training_data.generate_synthetic_data.models import (
    Model, ModelType, ModelProvider, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics,
)
from training_data.generate_synthetic_data.query_model import QueryModel
from training_data.generate_synthetic_data.generate_{module} import Generate{ClassName}
```

### Test Coverage Per Generator (6 tests each)

1. **`test_templates_defined`**: Verify TEMPLATES class variable has 2 templates with correct IDs
2. **`test_data_batches_yields_all_items`**: Verify get_data_batches() cycles through all topics/terms/archetypes
3. **`test_source_category`**: Verify get_source_category() returns correct category string
4. **`test_build_prompt_includes_context`**: Verify build_prompt() includes topic context and MTG_NOTATION_LEGEND
5. **`test_build_context_returns_metadata`**: Verify build_context() returns category, template_id, and domain label
6. **`test_dry_run_generation`**: Verify dry_run=True doesn't call save_item, generated_count increments

### Shared Test Fixtures (in conftest.py)
The existing `conftest.py` already mocks `ollama`, `anthropic`, `openai`, `pymongo` — sufficient for all 4 generators.

---

## Potential Risks

1. **Risk**: Terminology generator behavior change (direct QA → LLM-generated QA)
   **Mitigation**: The new behavior produces higher quality training data. Old behavior was essentially a "copy" with no LLM variation. Document in CHANGELOG.

2. **Risk**: Commander Knowledge sub-topic breakdown changes data coverage
   **Mitigation**: Cover all original Commander rules concepts in the sub-topics. The old monolithic prompt covered: singleton, commander zone, tax, damage, color identity, multiplayer, partner, background, companion. All represented in 8 sub-topics.

3. **Risk**: main.py import changes break backward compatibility
   **Mitigation**: The old import `from .generate_archetypes import *` still works — class name `GenerateArchetypes` is preserved. Only the constructor signature changes.

4. **Risk**: `validation_pct` type change (old code used `int`, base class uses `float`)
   **Mitigation**: `float` is backward compatible — `1` and `1.0` are interchangeable in Python.

---

## Handoff to Implementer

**Design Document**: (inline above)
**User Story**: Convert 4 topic-based generators to BaseGenerator[str]
**Estimated Complexity**: Low — follows exact pattern of 4 already-converted generators
**Key Files**: `generate_meta_knowledge.py`, `generate_commander_knowledge.py`, `generate_terminology_questions.py`, `generate_archetypes.py`, `main.py`
**Start With**: Task 1 (GenerateMetaKnowledge) — simplest, uses existing prompt builder
**Acceptance Criteria**: All 4 generators inherit BaseGenerator[str], define TEMPLATES, implement all abstract methods, main.py updated, all existing + new tests pass
