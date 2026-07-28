from __future__ import annotations

import logging
import random
import re
from typing import Any, Callable
from dataclasses import dataclass

import yaml

from .query_model import QueryModel
from .models import Card, Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics, GenerationTrace
from . import constants
from .constants import *


logger = logging.getLogger(__name__)


# =============================================================================
# SCAFFOLDING CACHE — shared prompt blocks loaded from the MongoDB TemplateStore
# =============================================================================
# Populated once at startup by ``init_scaffolding(store)``. Each ``build_*_prompt``
# function reads scaffolding via ``_get_scaffold(key, fallback)`` which checks
# the cache first, then falls back to the ``constants.py`` import. With
# ``template_store=None`` (the default) the cache stays empty and every
# generator behaves byte-identically to the current hardcoded behavior.

_SCAFFOLDING_CACHE: dict[str, str | list[str]] = {}

# Map of scaffolding cache key → (template_id, expected_type) for the shared
# namespace docs produced by ``seed_templates.extract_shared_blocks``.
_SCAFFOLDING_KEYS: list[tuple[str, str, type]] = [
    ("SYSTEM_MESSAGE", "system_message", str),
    ("MTG_NOTATION_LEGEND", "notation_legend", str),
    ("OUTPUT_FORMAT", "output_format", str),
    ("CARD_COMPARISON_INSTRUCTIONS", "card_comparison_instructions", str),
    ("REQUIREMENTS_BASE", "requirements_base", list),
]

# Mapping from internal cache keys to the corresponding YAML key names in
# ``templates/shared.yaml`` under the ``scaffolding:`` section.
_CACHE_KEY_TO_YAML_KEY: dict[str, str] = {
    "SYSTEM_MESSAGE": "system_message",
    "MTG_NOTATION_LEGEND": "notation_legend",
    "OUTPUT_FORMAT": "output_format",
    "CARD_COMPARISON_INSTRUCTIONS": "card_comparison_instructions",
    "REQUIREMENTS_BASE": "requirements_base",
}


def init_scaffolding(
    yaml_loader: "YamlTemplateLoader | None" = None,
    store: "TemplateStore | None" = None,
) -> None:
    """Populate the scaffolding cache. YAML path takes precedence.

    Called once at startup in ``main.py``. When *yaml_loader* is provided the
    cache is populated from ``templates/shared.yaml``; otherwise when *store*
    is provided the legacy MongoDB path is used. With both ``None`` this is a
    no-op and every ``build_*_prompt`` function falls back to the
    ``constants.py`` imports (current hardcoded behavior).
    """
    if yaml_loader is not None:
        _populate_from_yaml(yaml_loader)
    elif store is not None:
        _populate_from_store(store)


def _populate_from_yaml(loader: "YamlTemplateLoader") -> None:
    """Load scaffolding blocks from ``templates/shared.yaml`` via the YAML loader."""
    scaffold_data = loader.get_scaffolding()
    if scaffold_data is None or not isinstance(scaffold_data, dict):
        return
    for cache_key, yaml_key in _CACHE_KEY_TO_YAML_KEY.items():
        content = scaffold_data.get(yaml_key)
        if content is not None:
            _SCAFFOLDING_CACHE[cache_key] = content  # type: ignore[assignment]


def _populate_from_store(store: "TemplateStore") -> None:
    """Legacy MongoDB path — unchanged from previous behaviour."""
    shared = store.SHARED_NAMESPACE
    for key, tid, _expected_type in _SCAFFOLDING_KEYS:
        doc = store.get_latest(shared, tid, "generation")
        if doc:
            data = yaml.safe_load(doc["yaml_content"]) or {}
            content = data.get("content", "")
            _SCAFFOLDING_CACHE[key] = content  # type: ignore[assignment]


def _get_scaffold(key: str, fallback: str | list[str]) -> str | list[str]:
    """Return the cached scaffold for *key*, or *fallback* if unset."""
    return _SCAFFOLDING_CACHE.get(key, fallback)


def reset_scaffolding_cache() -> None:
    """Clear the scaffolding cache (for tests)."""
    _SCAFFOLDING_CACHE.clear()


@dataclass(frozen=True)
class TemplateConfig:
    """Configuration for a generation template.

    Attributes:
        template_id: Unique identifier for this template (e.g., "how_does_it_work")
        task_instruction: The prompt instruction for this template
        weight: Selection weight for weighted random sampling (default 1.0)
        validation_rules: Template-specific HARD REJECT rules (optional)
        min_answer_length: Minimum answer length in characters (default 80)
        max_answer_length: Maximum answer length in characters (default 2000)
    """
    template_id: str
    task_instruction: str
    weight: float = 1.0
    validation_rules: list[str] | None = None
    min_answer_length: int = 80
    max_answer_length: int = 2000
    version: int | None = None  # NEW — template version tracking (Story 045)

    def __post_init__(self):
        if self.validation_rules is None:
            object.__setattr__(self, "validation_rules", [])


def _dict_to_template_config(doc: dict) -> TemplateConfig:
    """Convert a template dict (from YAML or MongoDB) to :class:`TemplateConfig`.

    The *doc* may come from either the MongoDB store (with ``yaml_content``
    containing a YAML string) or from :class:`~.YamlTemplateLoader` (with
    parsed fields like ``instruction``, ``weight``, etc. already resolved).

    Missing fields fall back to the :class:`TemplateConfig` defaults. The
    ``version`` field is preserved from the doc when present (e.g. MongoDB
    docs carry an integer version; YAML entries carry ``"1"`` as a stable
    sentinel).
    """
    # MongoDB path: yaml_content is a string that needs parsing
    if "yaml_content" in doc:
        data: Any = yaml.safe_load(doc["yaml_content"]) or {}
        return TemplateConfig(
            template_id=doc["template_id"],
            task_instruction=data.get("instruction", ""),
            weight=float(data.get("weight", 1.0)),
            validation_rules=data.get("validation_rules") or [],
            min_answer_length=int(data.get("min_answer_length", 80)),
            max_answer_length=int(data.get("max_answer_length", 2000)),
            version=doc.get("version"),
        )

    # YAML loader path: fields are already parsed
    return TemplateConfig(
        template_id=doc["template_id"],
        task_instruction=doc.get("instruction", ""),
        weight=float(doc.get("weight", 1.0)),
        validation_rules=doc.get("validation_rules") or [],
        min_answer_length=int(doc.get("min_answer_length", 80)),
        max_answer_length=int(doc.get("max_answer_length", 2000)),
        version=str(doc.get("version", "1")),
    )


# =============================================================================
# PROMPT BUILDING
# =============================================================================








def build_commander_prompt() -> str:
    """Generate Commander rules questions with MTG notation guide."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]

    commander_context = """
Commander rules:
- 100-card singleton deck
- One legendary creature commander
- Commander determines color identity
- Starting life: 40
- Command zone where commanders exist
- Commander tax: +{{2}} each time cast
- Commander damage: 21 from one commander kills
- Multiplayer: typically 4 players
"""
        
    prompt = f"""{MTG_NOTATION_LEGEND}

Based on Commander rules:

{commander_context}

Generate 20 common Commander questions with accurate answers.

Output JSON array. Keep answers 2-3 sentences, accurate and concise.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_multi_card_usage_prompt(card1: str, card2: str, description: str) -> str:
    """Generate multi-card usage prompt with MTG notation guide."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]

    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 2 usage questions for: {card1} and {card2}

How they work: {description}

Output JSON with natural questions like "How do I use X with Y?"
Explain the mechanics and why the combo is effective.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt

def build_card_detail(card_number: int | None, card: Card):
    """Build a short card description for prompt context.

    Supports both the legacy ``Card`` class and Pydantic domain models.
    When given a Pydantic model with ``to_prompt_detail()``, delegates to it.
    Otherwise falls back to the original formatting.
    """
    prefix = "" if card_number is None else f"Card {card_number}: "

    # Delegate to Pydantic model's serialization when available
    if hasattr(card, "to_prompt_detail"):
        return f"{prefix}{card.to_prompt_detail()}"

    detail = f"""
{prefix}{card.name}
Type: {card.type} | Cost: {card.mana_cost}
Text: {card.text}
"""
    return detail

def build_card_comparision_prompt(card1: Card, card2: Card) -> str:
    """Generate card comparison prompt with full MTG notation and analysis requirements."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    CARD_COMPARISON_INSTRUCTIONS = _get_scaffold("CARD_COMPARISON_INSTRUCTIONS", constants.CARD_COMPARISON_INSTRUCTIONS)  # type: ignore[assignment]

    card1_name = card1.name
    card2_name = card2.name
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Compare these two Magic cards with similar effects:

{build_card_detail(1, card1)}

{build_card_detail(2, card2)}

{CARD_COMPARISON_INSTRUCTIONS}

Generate 2 comparison Q&A pairs in JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Questions should be like:
- "Which is better, {card1_name} or {card2_name}?"
- "{card1_name} vs {card2_name}?"
- "Should I run {card1_name} or {card2_name}?"

Answers MUST:
- Accurately state what each card does mechanically (read the card text carefully)
- MENTION CARD TYPES and their implications (especially if one is a creature)
- Compare costs and benefits correctly (do the math)
- Mention ALL important abilities (card draw, color fixing, destruction, etc.)
- Give context-dependent recommendations (not just "X is always better")
- Use correct MTG terminology
- Be 3-5 sentences with clear reasoning

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_reverse_lookup_prompt(pattern: dict, card_details: str) -> str:
    """Generate reverse lookup (feature → cards) prompt with MTG notation guide."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]

    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 3 reverse lookup Q&A pairs for cards that "{pattern['feature']}".

Matching cards:
{card_details}

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Questions should be like:
- "What card {pattern['feature']}?"
- "What cards {pattern['feature']}?"
- "Is there a card that {pattern['feature']}?"

Answers should list 3-5 best cards from the matching cards above and briefly explain what they do.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_synergy_prompt(card: dict, synergy_cards: set) -> str:
    """Generate card synergy discovery prompt with MTG notation guide."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]

    card_name = card.get('name', '')
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 2 synergy Q&A pairs for {card_name}.

Card: {card_name}
Text: {card.get('text', '')}

Cards that synergize with it: {', '.join(list(synergy_cards)[:5])}

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Questions like:
- "What cards synergize with {card_name}?"
- "What goes well with {card_name}?"
- "What commander works with {card_name}?"

Answers should explain why the synergy works and list 2-3 cards.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_budget_alternative_prompt(exp_card: dict, budget_details: str) -> str:
    """Generate budget alternative recommendations prompt with MTG notation guide."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]

    exp_name = exp_card.get('name', '')
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 2 budget alternative Q&A pairs for {exp_name}.

Expensive card: {exp_name} (rare/mythic)
Text: {exp_card.get('text', '')}

Budget alternatives:
{budget_details}

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Questions like:
- "What's a budget alternative to {exp_name}?"
- "Cheap replacement for {exp_name}?"
- "Budget version of {exp_name}?"

Answers should list 2-3 budget cards and explain they do similar things for less $$.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_color_identity_prompt(card: dict, commander_name: str, commander_colors: list[str], is_legal: bool) -> str:
    """Generate color identity legality prompt with MTG notation guide."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]

    card_name = card.get('name', '')
    card_colors: list[str] = card.get('colorIdentity', card.get('colors', []))
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 2 color identity Q&A pairs.

Card: {card_name}
Color identity: {', '.join(list(filter(None, card_colors))) if card_colors else 'Colorless'}
Mana cost: {card.get('manaCost', 'N/A')}

Commander: {commander_name}
Color identity: {', '.join(commander_colors)}

Can this card be played: {"YES" if is_legal else "NO"}

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Questions like:
- "Can I play {card_name} in my {commander_name} deck?"
- "What's the color identity of {card_name}?"
- "Is {card_name} legal in {commander_name}?"

Answers should explain color identity rules and explain to the question asker why.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_quick_guidelines_prompt(base_question: str, base_answer: str) -> str:
    """Generate deckbuilding guideline variations (no MTG legend needed - already provided in base)."""
    
    prompt = f"""Given this deckbuilding guideline, generate 3 variations with different phrasings.

Original Q&A:
Q: {base_question}
A: {base_answer}

Generate 3 variations in JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Keep the core answer the same but phrase questions naturally and diversely.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_deckbuilding_theory_prompt(topic: str, context: str) -> str:
    """Generate deckbuilding theory Q&A covering ratios, evaluation, and construction principles."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are an expert Magic: The Gathering deckbuilder. Generate 3 Q&A pairs about this deckbuilding topic:

Topic: {topic}
Context: {context}

Questions should cover practical deckbuilding decisions, card evaluation, and construction theory.
Answers should be detailed, actionable, and explain the WHY behind the advice.

Examples of good questions:
- "How do I evaluate whether a card earns its slot in my deck?"
- "What's the difference between card advantage and card selection?"
- "How do I know when to cut cards during deck tuning?"
- "What makes a card a 'goodstuff' pick vs a synergy piece?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences with concrete examples and reasoning.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_commander_building_prompt(archetype: str, strategy_context: str) -> str:
    """Generate Commander-specific deckbuilding Q&A for various archetypes and strategies."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are an expert Commander deckbuilder. Generate 3 Q&A pairs about building a {archetype} Commander deck.

Strategy context:
{strategy_context}

Questions should be specific to Commander format construction challenges.
Cover topics like: choosing a commander, building around themes, threat density, political considerations, power level calibration.

Examples of good questions:
- "How do I build around a sacrifice commander?"
- "What's the right threat density for a control commander?"
- "How do I balance synergy pieces vs goodstuff in Commander?"
- "How many ways to win should my Commander deck have?"
- "What's the difference between a 75% deck and a cEDH deck?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-6 sentences with Commander-specific advice and reasoning.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_rules_scenario_prompt(scenario: str, relevant_rules: str) -> str:
    """Generate scenario-based rules Q&A that teaches rules reasoning, not just definitions."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering rules expert (Level 2+ judge). Generate 3 Q&A pairs about this rules scenario.

Scenario: {scenario}
Relevant rules concepts: {relevant_rules}

Questions should present realistic game situations and ask what happens.
Answers should explain the ruling AND the underlying rule principle so the player learns to reason through similar situations.

Examples of good questions:
- "I cast Lightning Bolt targeting my opponent's creature. They cast Giant Growth in response. What happens?"
- "My creature has lifelink and deathtouch. If it deals combat damage, what happens?"
- "Can I activate a planeswalker's ability the turn it enters the battlefield?"
- "My opponent casts a spell with split second. Can I respond?"
- "Two triggered abilities trigger at the same time. Who controls the order?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers MUST:
- State clearly what happens in the scenario
- Explain the rule(s) that govern the outcome
- Use correct MTG rules terminology (stack, resolve, state-based actions, etc.)
- Be 3-5 sentences

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_archetype_prompt(archetype: str, archetype_context: str) -> str:
    """Generate deck archetype and strategy Q&A covering playstyles and strategic concepts."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering strategy expert. Generate 3 Q&A pairs about the {archetype} archetype/strategy.

Context:
{archetype_context}

Questions should cover: how the archetype works, strengths and weaknesses, key cards, how to play against it, when to choose it.

Examples of good questions:
- "How does a stax deck win?"
- "What are the weaknesses of a voltron strategy?"
- "What's the difference between hard control and soft control in Commander?"
- "How do I recognize if I'm playing against a storm deck?"
- "When should I choose aggro over combo in a Commander pod?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences covering the strategic depth of the archetype.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_game_theory_prompt(situation: str, decision_context: str) -> str:
    """Generate game theory and decision-making Q&A covering sequencing, threat assessment, and politics."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are an expert Magic: The Gathering player. Generate 3 Q&A pairs about game theory and decision-making.

Situation: {situation}
Decision context: {decision_context}

Questions should cover practical in-game decisions, sequencing, threat assessment, and multiplayer politics.

Examples of good questions:
- "When should I use removal on an opponent's creature vs holding it?"
- "How do I evaluate whether a hand is worth keeping?"
- "When is it correct to attack the player in the lead?"
- "How do I sequence my spells to play around counterspells?"
- "When should I hold mana open instead of developing my board?"
- "How do I evaluate political deals in Commander?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences with actionable decision-making frameworks.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_meta_knowledge_prompt(topic: str, meta_context: str) -> str:
    """Generate meta and power level Q&A covering cEDH, pod dynamics, and format knowledge."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are an expert in Magic: The Gathering Commander meta and competitive play. Generate 3 Q&A pairs about:

Topic: {topic}
Context: {meta_context}

Questions should cover power levels, meta considerations, format-specific knowledge, and competitive vs casual play.

Examples of good questions:
- "What makes a deck cEDH viable?"
- "How do I calibrate my deck's power level for a casual pod?"
- "What's the difference between a 7/10 and a 9/10 Commander deck?"
- "What are the most common cEDH win conditions?"
- "How do I evaluate my local meta to improve my deck?"
- "What separates a good Commander from a great one?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences with specific, accurate meta knowledge.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_rule_explanation_prompt(rule_number: str, rule_text: str, template: dict[str, str]) -> str:
    """Generate natural Q&A from a specific rule, grounded in actual rule text."""
    SYSTEM_MESSAGE = _get_scaffold("SYSTEM_MESSAGE", constants.SYSTEM_MESSAGE)  # type: ignore[assignment]
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    OUTPUT_FORMAT = _get_scaffold("OUTPUT_FORMAT", constants.OUTPUT_FORMAT)  # type: ignore[assignment]
    prompt = f"""
    {SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<rule>
AUTHORITATIVE RULE — treat this as ground truth:

Rule {rule_number}: {rule_text}
</rule>

<task>
{template["task_instruction"]}

REQUIREMENTS:
1. Questions must be varied and natural-sounding. Do not ask "What does rule {rule_number} say about..." — players don't talk that way.
2. Classify each answer by question type and adjust depth accordingly:
   - "what happens when" questions → walk through the sequence of events concisely, citing relevant rule text to explain WHY.
   - "can I" questions → confirm or deny, then explain the mechanic that determines the answer.
   - "does X apply when" questions → state whether it applies and quote or paraphrase the rule condition that determines it.
3. Every answer MUST include a concrete in-game example that illustrates the rule. Never explain a rule in purely abstract terms.
4. When explaining why something works, quote or closely paraphrase the relevant part of the rule text from the <rule> block above.
5. Do NOT reference the rule number in answers — explain mechanics conversationally as a rules expert would.
6. Answers must be plain text only. Do not use markdown formatting such as bold (**text**), italics, or bullet points.
7. The answer field MUST be a single string (not an array).

{OUTPUT_FORMAT}
</task>"""
    return prompt

def build_rule_interaction_prompt(rule1_num: str, rule1_text: str, rule2_num: str, rule2_text: str) -> str:
    """Generate scenario Q&A where two rules interact, grounded in both rule texts."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering rules expert. Generate 2 scenario Q&A pairs where BOTH of these rules are relevant.

Rule {rule1_num}: {rule1_text}

Rule {rule2_num}: {rule2_text}

Create realistic in-game scenarios where a player needs to apply both rules to determine the outcome.
Answers must explain which rules apply and in what order, citing both rule numbers.

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers MUST:
- Describe the game situation clearly
- Explain which rule applies first and why
- State the final outcome
- Cite rule {rule1_num} and rule {rule2_num} by number
- Be 3-5 sentences

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_glossary_with_examples_prompt(term: str, definition: str) -> str:
    """Generate Q&A from a glossary term with concrete in-game examples, not just the definition."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering rules expert. Generate 3 Q&A pairs about this MTG term.

Term: {term}
Official definition: {definition}

Generate varied questions — not just "what does X mean" but also practical application questions.
Answers should include the definition AND a concrete in-game example that illustrates it.

Question styles to use:
- "What does '{term}' mean in Magic?"
- "How does {term} work in practice?"
- "Give me an example of {term} in a game."
- "What's the difference between {term} and [related concept]?" (if applicable)
- "Does {term} apply when [specific situation]?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers MUST:
- Include the official definition
- Include at least one concrete in-game example
- Be accurate — do not invent rules
- Be 2-4 sentences

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_rule_edge_case_prompt(rule_number: str, rule_text: str, section_name: str) -> str:
    """Generate edge case and tricky interaction questions from complex rule sections."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering Level 2 judge. Generate 2 tricky edge case Q&A pairs from this rule.

Section: {section_name}
Rule {rule_number}: {rule_text}

Focus on the non-obvious applications, common player mistakes, and edge cases this rule governs.
These should be questions that trip up experienced players, not beginners.

Examples of good edge case questions:
- "If [unusual condition], does rule {rule_number} still apply?"
- "My opponent claims [common misconception]. Is that correct per rule {rule_number}?"
- "What happens in the unusual case where [edge condition from rule text]?"
- "Players often think [wrong interpretation]. What does rule {rule_number} actually say?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers MUST:
- Correct any implied misconception in the question
- Cite rule {rule_number}
- Explain the correct ruling and the reasoning behind it
- Be 3-5 sentences

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_rule_why_prompt(rule_number: str, rule_text: str) -> str:
    """Generate 'why does this work' backward-reasoning questions from rule text."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering rules expert. Generate 2 Q&A pairs that ask WHY a ruling works the way it does.

Rule {rule_number}: {rule_text}

Questions should start from a known outcome or common interaction and ask why it works that way.
This teaches the underlying principle, not just the surface ruling.

Examples of good "why" questions:
- "Why can't I [action]? What rule prevents it?"
- "Why does [interaction] work the way it does?"
- "Why is [counterintuitive ruling] correct?"
- "My friend says [ruling]. Why is or isn't that correct?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers MUST:
- Explain the underlying principle, not just the outcome
- Reference rule {rule_number} by number
- Connect to the game design intent where relevant
- Be 3-5 sentences

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_article_qa_prompt(title: str, content: str) -> str:
    """Generate Q&A from an EDHREC article, using the full content as grounding."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering strategy expert. Read this EDHREC article and generate 4 Q&A pairs from it.

Article title: {title}
Article content:
{content}

Generate questions a Commander player would ask that this article answers.
Answers MUST be grounded in the article content above — do not invent information not present.
Answers should synthesize the article's advice, not quote it directly.

Question styles:
- "What does [article title] recommend about X?"
- "How should I approach [topic from article]?"
- "What's the best strategy for [topic]?"
- "Why is [concept from article] important in Commander?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences, practical, and actionable.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_guide_qa_prompt(title: str, content: str) -> str:
    """Generate Q&A from an EDHREC guide, focusing on instructional content."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering expert. Read this EDHREC guide and generate 4 Q&A pairs from it.

Guide title: {title}
Guide content:
{content}

Generate questions someone learning this topic would ask.
Answers MUST be grounded in the guide content — do not invent information.
Focus on the instructional, how-to aspects of the guide.

Question styles:
- "How do I [task from guide]?"
- "What's the best way to [topic]?"
- "What should I consider when [situation from guide]?"
- "What are the key principles of [topic]?"
- "What mistakes do players make with [topic]?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences, practical and beginner-friendly.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_staple_analysis_prompt(card: dict) -> str:
    """Generate Q&A analyzing why a game-changer card is a Commander staple."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    name = card.get('name', '')
    oracle_text = card.get('oracle_text', '')
    card_type = card.get('type', '')
    mana_cost = card.get('mana_cost', '')
    num_decks = card.get('num_decks', 0)
    salt = card.get('salt', 0)
    tags = card.get('tags', [])
    color_identity = card.get('color_identity', [])

    color_str = ', '.join(color_identity) if color_identity else 'Colorless'
    tags_str = ', '.join(tags) if tags else 'none'
    salt_label = 'very controversial' if salt > 2.5 else ('controversial' if salt > 1.5 else ('mildly disliked' if salt > 0.8 else 'generally accepted'))

    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering Commander expert. Generate 3 Q&A pairs analyzing why this card is a Commander staple.

Card: {name}
Type: {card_type}
Mana cost: {mana_cost}
Color identity: {color_str}
Oracle text: {oracle_text}
Number of Commander decks it appears in: {num_decks:,}
Salt score: {salt:.2f} ({salt_label})
Tags: {tags_str}

Generate questions about why this card is so widely played, what makes it powerful, and when/how to use it.
Also address the salt score if it's above 1.5 — why do players dislike it?

Question styles:
- "Why is {name} in so many Commander decks?"
- "What makes {name} a staple?"
- "Is {name} worth including in my deck?"
- "Why do people hate playing against {name}?" (if salty)
- "What kind of decks want {name}?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences grounded in the card's actual text and statistics.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_color_staples_prompt(color: str, cards: list) -> str:
    """Generate Q&A about the top cards for a given color in Commander."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    card_lines = []
    for c in cards[:10]:
        name = c.get('name', '')
        oracle = c.get('oracle_text', '')[:80]
        num_decks = c.get('num_decks', 0)
        tags = ', '.join(c.get('tags', []))
        card_lines.append(f"  - {name} ({num_decks:,} decks) [{tags}]: {oracle}...")
    card_info = '\n'.join(card_lines)

    color_full = {
        'black': 'Black', 'blue': 'Blue', 'colorless': 'Colorless',
        'green': 'Green', 'red': 'Red', 'white': 'White'
    }.get(color, color.title())

    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering Commander expert. Generate 3 Q&A pairs about the top {color_full} cards in Commander.

Top {color_full} Commander cards by deck inclusion:
{card_info}

Generate questions about what makes these cards good, when to include them, and {color_full}'s strengths in Commander.

Question styles:
- "What are the best {color_full} cards for Commander?"
- "What {color_full} staples should I include in every deck?"
- "What does {color_full} do best in Commander?"
- "What are the most popular {color_full} card draw spells?" (if applicable)
- "What {color_full} removal should I run?" (if applicable)

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should be 3-5 sentences mentioning specific cards from the list above.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_salt_prompt(cards: list) -> str:
    """Generate Q&A about salty/controversial cards — what they are and why players dislike them."""
    MTG_NOTATION_LEGEND = _get_scaffold("MTG_NOTATION_LEGEND", constants.MTG_NOTATION_LEGEND)  # type: ignore[assignment]
    card_lines = []
    for c in cards[:8]:
        name = c.get('name', '')
        oracle = c.get('oracle_text', '')[:80]
        salt = c.get('salt', 0)
        num_decks = c.get('num_decks', 0)
        card_lines.append(f"  - {name} (salt: {salt:.2f}, {num_decks:,} decks): {oracle}...")
    card_info = '\n'.join(card_lines)

    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering Commander expert. Generate 3 Q&A pairs about controversial/salty Commander cards.

High-salt Commander cards (scale 0-3, higher = more controversial):
{card_info}

Generate questions about why these cards frustrate players, whether they're fair, and how to play around them.

Question styles:
- "Why do people hate playing against [card name]?"
- "What are the saltiest cards in Commander?"
- "Is [card name] too powerful for casual Commander?"
- "How do I play around [frustrating card]?"
- "Should I avoid including [salty card] in casual pods?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers should explain WHY the card is frustrating (its effect on gameplay), not just that it is.
Be balanced — acknowledge both why it's played and why it's controversial.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt

def clean_html(raw: str) -> str:
    """Strip HTML tags and normalise whitespace from article/guide content."""
    # Remove script and style blocks entirely
    raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    raw = re.sub(r'<[^>]+>', ' ', raw)
    # Decode common HTML entities
    raw = (raw
           .replace('&amp;', '&')
           .replace('&lt;', '<')
           .replace('&gt;', '>')
           .replace('&quot;', '"')
           .replace('&#39;', "'")
           .replace('&nbsp;', ' '))
    # Collapse whitespace
    return re.sub(r'\s+', ' ', raw).strip()

# Re-export pure-card helpers (defined in card_utils to avoid heavy deps)
from .card_utils import map_card, map_card_with_zones  # noqa: PLC0415 


def validate_and_loop_with_suggested_fix(
    query_model: QueryModel,
    models: dict[ModelType, Model],
    qa_pairs: list[QuestionAnswer],
    validation_pct: float,
    enable_extra_validation: bool,
    build_context: Callable[[], str],
    source_category: str,
    source_data: list,
    source_template: str | None,
    metrics: ValidationMetrics | None = None,
    trace: GenerationTrace | None = None,
    sibling_corrections: list[str] | None = None) -> tuple[bool, QuestionAnswerEnhanced | None]:
    for enumerated_i, qa in enumerate(qa_pairs):

        if metrics:
            metrics.record_candidate(source_category, source_template)

        should_validate = True

        if random.random() > validation_pct:
            should_validate = False

        if not should_validate and metrics:
            metrics.record_skip(source_category, source_template)

        iteration = 0
        round_num = 0
        is_valid: bool = True
        reason: str | None = None
        score: float | None = None

        while should_validate:
            if metrics:
                metrics.record_validation_attempt(source_category, source_template)

            qa_context = build_context()

            round_data = {"round": round_num}
            is_valid, reason, score = query_model.validate_qa(
                validation_model=models[ModelType.VALIDATION],
                question=qa.question,
                answer=qa.answer,
                context=qa_context,
                category=source_category,
                enable_extra_validation=enable_extra_validation,
                trace_round=round_data,
            )

            if not is_valid:
                print(f"    ✗ REJECTED [attempt {iteration + 1}/3] (score: {score}/10, {reason}): {qa.question[:80]}")
                print(f"    → Passing back to generation model for correction...")
                regen_data = {}
                new_answer = query_model.regenerate_answer(
                    generation_model=models[ModelType.GENERATION],
                    question=qa.question,
                    old_answer=qa.answer,
                    reason=reason,
                    score=score,
                    context=qa_context,
                    category=source_category,
                    sibling_feedback="\n".join(sibling_corrections) if sibling_corrections else "",
                    trace_regeneration=regen_data,
                )
                round_data["regeneration"] = regen_data
                if new_answer:
                    if sibling_corrections is not None:
                        sibling_corrections.append(
                            f"Q{enumerated_i + 1} was rejected for: {reason}. "
                            f"The corrected answer now fixes that issue. "
                            f"Apply the same fix to any similar errors in your answer."
                        )
                    qa.answer = new_answer
                else:
                    print(f"    ✗ Regeneration failed, moving on.")
                    if trace is not None:
                        trace.validation_rounds.append(round_data)
                    break
                iteration += 1
                if metrics:
                    metrics.record_fix_attempt(source_category, source_template)
                if iteration >= 3:
                    print(f"    ✗ REJECTED after 3 regeneration attempts, moving on.")
                    if trace is not None:
                        trace.validation_rounds.append(round_data)
                    break
                round_num += 1
                if trace is not None:
                    trace.validation_rounds.append(round_data)
                continue
            else:
                if trace is not None:
                    trace.validation_rounds.append(round_data)
                break

        if trace is not None:
            trace.total_rounds = round_num + 1 if should_validate else 0
            trace.final_score = score
            if not should_validate:
                trace.final_outcome = "skipped"
            elif is_valid:
                trace.final_outcome = "accepted_first_attempt" if round_num == 0 else "accepted_after_fix"
            else:
                trace.final_outcome = "rejected"

        if is_valid:
            attempt_label = " (first attempt)" if iteration == 0 else f" (after {iteration} fix)"
            print(f"    ✓ ACCEPTED{attempt_label} (score: {score}/10): {qa.question[:80]}")
            if metrics:
                if iteration == 0:
                    metrics.record_first_attempt_pass(score, source_category, source_template)
                else:
                    metrics.record_pass_after_fix(score, source_category, source_template)

            doc = QuestionAnswerEnhanced(qa.question, qa.answer)
            doc.category = source_category
            doc.source_data = source_data
            doc.validated = should_validate
            doc.validation_score = score
            doc.needs_review = (not should_validate)
            doc.suggested_fix = None
            doc.source_template = source_template
            doc.generation_model = models[ModelType.GENERATION].name
            doc.validation_model = models[ModelType.VALIDATION].name if should_validate else None
            doc.run_id = metrics.run_id if metrics else None

            if metrics:
                metrics.flush()
                metrics.print_rolling_summary()

            return is_valid, doc
        else:
            if should_validate and metrics:
                if iteration == 0:
                    metrics.record_failed_first_attempt(source_category, source_template)
                else:
                    metrics.record_failed_after_fixes(source_category, source_template)
            print(f"    ✗ REJECTED (missing question/answer keys): {qa}")

        if metrics:
            metrics.flush()
            metrics.print_rolling_summary()

    return False, None