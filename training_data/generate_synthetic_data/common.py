import random
import re
from typing import Any, Callable
from query_model import QueryModel
from models import Card, Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced
from constants import *


# =============================================================================
# PROMPT BUILDING
# =============================================================================








def build_commander_prompt() -> str:
    """Generate Commander rules questions with MTG notation guide."""
    
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
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 2 usage questions for: {card1} and {card2}

How they work: {description}

Output JSON with natural questions like "How do I use X with Y?"
Explain the mechanics and why the combo is effective.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt

def build_card_detail(card_number: int | None, card: Card):
    detail = f"""
{"" if card_number is None else f"Card {card_number}: "}{card.name}
Type: {card.type} | Cost: {card.mana_cost}
Text: {card.text}
"""

    return detail

def build_card_comparision_prompt(card1: Card, card2: Card) -> str:
    """Generate card comparison prompt with full MTG notation and analysis requirements."""
    
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

def map_card(card: dict) -> Card | None: # type: ignore
    import json
    
    if not card or 'name' not in card or 'type' not in card or 'manaCost' not in card or 'text' not in card:
        return None
    
    projected_card: Card = Card(
        name=card.get('name', 'Unknown'),
        type=card.get('type', 'Unknown'),
        mana_cost=card.get('manaCost', 'Unknown'),
        text=card.get('text', ''),
        subtypes=json.loads(card.get('subtypes', '[]')) if card.get('subtypes') else [],
        supertypes=json.loads(card.get('supertypes', '[]')) if card.get('supertypes') else [],
        color_identity=json.loads(card.get('colorIdentity', '[]')) if card.get('colorIdentity') else [],
        zone_locations=[]
    )
    
    return 


def validate_and_loop_with_suggested_fix(
    query_model: QueryModel,
    models: dict[ModelType, Model],
    qa_pairs: list[QuestionAnswer], 
    validation_pct: float,
    enable_extra_validation: bool, 
    build_context: Callable[[], str],
    source_category: str,
    source_data: list,
    source_template: str | None) -> tuple[bool, QuestionAnswerEnhanced | None]:
    for enumerated_i, qa in enumerate(qa_pairs):
        
        should_validate = True
        
        if random.random() > validation_pct:
            should_validate = False
        
        iteration = 0
        is_valid: bool = True
        reason: str | None = None
        score: float | None = None
        suggested_fix: str | None = None
        
        while should_validate:
            qa_context = build_context()
            
            is_valid, reason, score, suggested_fix = query_model.validate_qa(
                validation_model=models[ModelType.VALIDATION],
                question=qa.question, 
                answer=qa.answer,
                context=qa_context,
                category=source_category,
                enable_extra_validation=enable_extra_validation
            )
            
            if not is_valid and suggested_fix:
                print(f"    ✗ REJECTED but suggested fix provided: {suggested_fix}. Applying fix and re-validating...")
                qa.answer = suggested_fix
                iteration += 1
                if iteration >= 3:
                    print(f"    ✗ REJECTED after 3 iterations, moving on.")
                    break
                continue                    
            elif is_valid:
                break     
            else:
                print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa.question[:80]}")
        
        print(f"    ✓ ACCEPTED (score: {score}/10): {qa.question[:80]}")
        
        if is_valid:
            doc = QuestionAnswerEnhanced(qa.question, qa.answer)
            doc.category = source_category
            doc.source_data = source_data
            doc.validated = should_validate
            doc.validation_score = score
            doc.needs_review = (not should_validate)
            doc.suggested_fix = suggested_fix if not is_valid else None
            doc.source_template = source_template
            
            
            return is_valid, doc
                
        else:
            print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            
    return False, None