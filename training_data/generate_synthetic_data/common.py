import re

global MODEL_NAME
MODEL_NAME="qwen2.5:14b"  # Change to 14B when ready

# Rule sections that are most relevant for gameplay scenarios
RELEVANT_RULE_SECTIONS = [
    '1',   # Game Concepts
    '2',   # Parts of a Card
    '3',   # Card Types
    '4',   # Zones
    '5',   # Turn Structure
    '6',   # Spells, Abilities, and Effects
    '7',   # Additional Rules
    '8',   # Multiplayer Rules
    '9',   # Casual Variants
    '10',  # Commander
    '70',  # Keywords
    '702', # Keyword Abilities
    '704', # State-Based Actions
    '706', # Copying Objects
    '707', # Face-Down Spells and Permanents
    '708', # Split Cards
    '717', # Meld Cards
    '722', # Convenience Actions
]

# Complex sections worth generating edge case questions for
COMPLEX_RULE_SECTIONS = {
    '116': 'Timing and Priority',
    '117': 'Costs',
    '118': 'Paying Costs',
    '119': 'Life',
    '120': 'Damage',
    '121': 'Drawing a Card',
    '122': 'Counters',
    '400': 'General Zone Rules',
    '601': 'Casting Spells',
    '602': 'Activating Activated Abilities',
    '603': 'Handling Triggered Abilities',
    '604': 'Handling Static Abilities',
    '608': 'Resolving Spells and Abilities',
    '700': 'General Additional Rules',
    '701': 'Keyword Actions',
    '702': 'Keyword Abilities',
    '704': 'State-Based Actions',
    '706': 'Copying Objects',
    '800': 'Multiplayer Rules',
    '903': 'Commander',
}

# =============================================================================
# MTG NOTATION LEGEND
# =============================================================================

MTG_NOTATION_LEGEND = """
MTG NOTATION GUIDE:
- {{T}}: Tap symbol (rotate card 90°, can only use if untapped)
- {{C}}: Colorless mana
- {{W}}: White mana
- {{U}}: Blue mana  
- {{B}}: Black mana
- {{R}}: Red mana
- {{G}}: Green mana
- {{X}}: Variable amount chosen when casting
- {{1}}, {{2}}, {{3}}, etc.: Generic mana (can be paid with any color or colorless)
- Example: {{2}}{{U}}{{U}} = 2 generic + 2 blue mana = 4 total mana

CARD TYPES:
- Creature: Can attack/block, has summoning sickness (can't tap or attack first turn)
- Artifact: Permanent that stays on battlefield, no summoning sickness
- Enchantment: Permanent that stays on battlefield
- Instant: Cast anytime, goes to graveyard after resolving
- Sorcery: Cast only on your turn, goes to graveyard after resolving
- Land: Played once per turn (not cast), produces mana

KEY MECHANICS:
- ETB (Enters the Battlefield): Triggers when permanent comes into play
- Summoning Sickness: Creatures can't tap or attack the turn they enter
- Sacrifice: Put into graveyard as a cost (can't be prevented)
- Destroy: Put into graveyard (can be prevented by indestructible)
- Exile: Remove from game (harder to recover than graveyard)
"""

# =============================================================================
# INSTRUCTION BLOCKS FOR PROMPTS
# =============================================================================

CARD_COMPARISON_INSTRUCTIONS = """
CRITICAL ANALYSIS REQUIREMENTS:
Before writing your answer, analyze step-by-step:

0. Card Types:
   - What TYPE is each card? (Creature, Artifact, Enchantment, Land, etc.)
   - If one is a CREATURE and one is NOT, this is CRITICAL information
   - Creatures have summoning sickness (can't tap immediately)
   - Creatures die to creature removal AND board wipes
   - Non-creature permanents are generally more resilient
   - ALWAYS mention if card types differ

1. Mana Economics:
   - What does each card COST to cast? (compare {{1}} vs {{2}} vs {{3}}, etc.)
   - What does each card PRODUCE or DO?
   - Net benefit = (what you get) - (what you pay)
   - IMPORTANT: If a card costs X mana and produces X mana, that's NET ZERO (mana conversion, not ramp)
   - Example: Paying {{3}} to untap and tapping for {{3}} = break even, not profit
   - A card that costs {{2}} and taps for {{C}} gives you net +1 mana per turn (after initial investment)

2. Key Mechanics:
   - Does it sacrifice itself? (one-time use only)
   - Does it tap repeatedly? (ongoing value each turn)
   - Does it produce colored mana or colorless mana? (colored is more flexible)
   - Does it draw cards, destroy permanents, or have other effects?
   - Does it enter tapped? (delayed value)
   - If it's a creature, remember it has SUMMONING SICKNESS

3. Common Errors to Avoid:
   - DON'T confuse casting cost with activation cost (they're different things)
   - DON'T claim a card "produces more mana" if it costs X to produce X (that's conversion)
   - DON'T ignore important text like "enters tapped", "draw a card", "destroy", "exile"
   - DON'T forget to mention if mana is colored vs colorless (this matters a lot)
   - DON'T get costs backwards ({{2}} is MORE expensive than {{1}})
   - DON'T ignore card types (Creature vs Artifact is HUGE)
   - DON'T forget summoning sickness for creatures

4. Context Matters - Consider:
   - Which is better for fast mana acceleration (ramp)?
   - Which is better for color fixing?
   - Which is better for card advantage?
   - Which is better for removal/control?
   - Which is more resilient to removal?
   - Are there specific deck types or strategies where one shines?

EXAMPLE OF GOOD COMPARISON:
Q: "Which is better, Sol Ring or Fellwar Stone?"
A: "Sol Ring is generally better. Sol Ring costs {{1}} and taps for {{C}}{{C}}, giving you net +1 colorless mana per turn. Fellwar Stone costs {{2}} and taps for one mana of any color an opponent could produce, also net +1 per turn but more expensive to cast. Sol Ring's lower cost makes it faster, though Fellwar Stone offers color fixing that Sol Ring lacks. For pure ramp, Sol Ring wins. For multicolor decks needing color fixing, Fellwar Stone has merit."

EXAMPLE OF BAD COMPARISON (DO NOT DO THIS):
Q: "Which is better, Hedron Crawler or Dragon's Hoard?"
A: "Hedron Crawler costs {{2}} and taps for {{C}}, suitable for any deck. Dragon's Hoard costs {{3}} and requires Dragons."
[ERROR: Doesn't mention Hedron Crawler is a CREATURE with summoning sickness and dies to board wipes]
"""

VALIDATION_CHECKLIST = """
CRITICAL CARD TYPE CHECKS:
Before anything else, verify the answer addresses card types:

1. Are the card types mentioned?
   - Creature vs Non-Creature is CRITICAL
   - Artifact vs Enchantment vs Land matters
   - If one is a creature and one isn't, this MUST be discussed

2. Type-specific mechanics mentioned?
   - Creatures: Summoning sickness (can't {{T}} or attack first turn), vulnerable to creature removal, can attack/block
   - Artifacts: No summoning sickness, only vulnerable to artifact removal
   - Enchantments: Only vulnerable to enchantment removal
   - Lands: Can't be countered, don't cost mana to play
   - Instants/Sorceries: One-time spells, not affected by board wipes

3. Vulnerability differences explained?
   - If comparing creature vs non-creature, answer MUST mention board wipes
   - If comparing different permanent types, answer MUST mention removal types
   - If comparing instants/sorceries, focus on EFFECTS not vulnerability

VERIFICATION CHECKLIST:
Check each of these carefully:

1. Casting costs correct?
   - Does the answer correctly state which card costs more to cast?
   - Are mana symbols and costs accurate?

2. Mechanics accurate?
   - Does it correctly describe what each card DOES?
   - Are activation costs vs casting costs distinguished properly?
   - Is net mana production calculated correctly?
   - If a card costs X and produces X, is it correctly identified as net zero (conversion, not ramp)?
   
3. CARD TYPES mentioned and explained?
   - If one card is a creature and one isn't, is this addressed?
   - Are type-specific vulnerabilities mentioned?
   - Is summoning sickness mentioned for creatures?
   - For instants/sorceries, are effects discussed (not board wipe vulnerability)?
   
4. Important details mentioned?
   - Card draw effects mentioned if present?
   - "Enters tapped" mentioned if relevant?
   - Sacrifice requirements mentioned if present?
   - Color restrictions mentioned (colored vs colorless mana)?
   - Destruction/removal effects mentioned if present?

5. No false claims?
   - No invented abilities or effects?
   - No confusion between "costs X, produces X" (net zero) vs actual ramp?
   - No claiming cheaper cards are more expensive?
   - No ignoring critical card text?

COMMON ERROR PATTERNS TO REJECT:
- Claiming "costs less to activate" when actually comparing casting costs
- Saying a card "produces more mana if you pay more" when it's X-for-X conversion
- Ignoring that a card draws cards, destroys things, or has other important effects
- Missing that colored mana ≠ colorless mana
- Confusing one-time effects with repeatable effects
- Backwards cost comparisons (saying {{2}} is cheaper than {{1}})
- IGNORING CARD TYPES (creature vs artifact is a HUGE difference)
- NOT MENTIONING summoning sickness for creatures
- MISSING vulnerability differences between card types
- Discussing board wipe vulnerability for INSTANTS/SORCERIES (they're spells, not permanents!)
"""

VALIDATION_SCORING_GUIDE = """
SCORING GUIDE:
- 9-10: Perfect, all mechanics correct, comprehensive, card types addressed
- 7-8: Good, minor omissions but no errors
- 5-6: Acceptable but missing important context
- 3-4: Significant errors or missing critical info (like ignoring card types)
- 1-2: Fundamentally wrong about card mechanics

CRITICAL: 
- If card types are ignored when comparing creature vs non-creature, max score is 4
- If there are ANY factual errors about card mechanics, max score is 4
- If discussing board wipes for instant/sorcery cards, max score is 4
- A score of 7+ is acceptable. Below 7 should be rejected.
"""

# =============================================================================
# PROMPT BUILDING
# =============================================================================

def build_card_search_prompt(pattern: dict, card_info: str) -> str:
    """Generate card search prompt with MTG notation guide."""
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 5 Q&A pairs for: {pattern['name']}

Example cards:
{card_info}

Output JSON with natural questions and helpful answers listing 3-5 best cards.
Answers should explain what the cards do and why they're good for this purpose.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


def build_qa_validation_prompt(question: str, answer: str, context: str = "", category: str = "") -> str:
    """Build the generic Q&A validation prompt used by validate_qa()."""
    context_block = f"\nSource material the answer should be grounded in:\n{context}\n" if context else ""
    return f"""You are a Magic: The Gathering expert reviewing a generated Q&A pair for training data quality.

Category: {category or 'general'}{context_block}
Question: {question}

Answer to validate:
{answer}

Score this answer on:
1. Factual accuracy — Is everything correct? Wrong mana costs, wrong card names, wrong mechanics = instant reject.
2. Completeness — Does it fully answer the question without important gaps?
3. Usefulness — Is this a good training example? Clear and specific, not vague or generic?
4. Grounding — Is it grounded in the provided context, or hallucinating details?

Scoring guide:
- 9-10: Excellent, publish as-is
- 7-8: Good, acceptable for training
- 5-6: Too vague, incomplete, or minor errors — reject
- 1-4: Factual errors or hallucinations — reject

Respond ONLY with JSON:
{{
  "score": <1-10>,
  "is_acceptable": <true/false>,
  "errors": "<factual errors if any, or 'none'>",
  "missing_info": "<what is missing or vague, if anything>",
  "reason": "<one sentence summary>"
}}

Output ONLY valid JSON, no other text."""


def build_card_validation_prompt(card1: dict, card2: dict, question: str, answer: str) -> str:
    """Build validation prompt for card comparison answers."""
    
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering expert reviewing a comparison answer for accuracy.

Card 1: {card1.get('name', '')}
Type: {card1.get('type', 'N/A')}
Text: {card1.get('text', '')}
Cost: {card1.get('manaCost', 'N/A')}

Card 2: {card2.get('name', '')}
Type: {card2.get('type', 'N/A')}
Text: {card2.get('text', '')}
Cost: {card2.get('manaCost', 'N/A')}

Question: {question}

Answer to validate:
{answer}

{VALIDATION_CHECKLIST}

Review this answer for:
1. Accuracy - Does it correctly describe both cards' mechanics AND types?
2. Completeness - Does it mention ALL important abilities AND type-specific concerns?
3. Usefulness - Does it give clear, context-dependent guidance?
4. Factual correctness - Are there any outright errors or misconceptions?

Respond ONLY with JSON:
{{
"score": <1-10>,
"is_acceptable": <true/false>,
"missing_info": "<what critical info is missing, if any>",
"errors": "<factual errors, if any>",
"mechanical_accuracy": "<are the card mechanics described correctly?>",
"cost_comparison_correct": "<are costs compared accurately?>",
"card_types_addressed": "<are card types mentioned and their implications explained?>"
}}

{VALIDATION_SCORING_GUIDE}

Output ONLY valid JSON, no other text."""
    return prompt


def build_combo_prompt(card_name: str, combo_list: str) -> str:
    """Generate combo question prompt with MTG notation guide."""
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 3 natural Q&A pairs about combos with {card_name}.

Known combos:
{combo_list}

Output JSON:
[
{{"question": "...", "answer": "..."}},
{{"question": "...", "answer": "..."}},
{{"question": "...", "answer": "..."}}
]

Make questions varied and natural. Base answers on combo data above.
Explain how the combos work and what they achieve.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt


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


def build_card_comparision_prompt(card1: dict, card2: dict) -> str:
    """Generate card comparison prompt with full MTG notation and analysis requirements."""
    
    card1_name = card1.get('name', '')
    card2_name = card2.get('name', '')
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Compare these two Magic cards with similar effects:

Card 1: {card1_name}
Type: {card1.get('type', 'N/A')}
Cost: {card1.get('manaCost', 'N/A')}
Text: {card1.get('text', '')}

Card 2: {card2_name}
Type: {card2.get('type', 'N/A')}
Cost: {card2.get('manaCost', 'N/A')}
Text: {card2.get('text', '')}

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


def build_rule_explanation_prompt(rule_number: str, rule_text: str) -> str:
    """Generate natural Q&A from a specific rule, grounded in actual rule text."""
    prompt = f"""{MTG_NOTATION_LEGEND}

You are a Magic: The Gathering rules expert. Generate 3 Q&A pairs based on this official rule.

Rule {rule_number}: {rule_text}

Generate questions a player would naturally ask that this rule answers.
The answer MUST be grounded in the rule text above — do not invent or extrapolate beyond it.
Include the rule number in the answer for traceability.

Examples of good question styles:
- "What happens when [situation described by rule]?"
- "Can I [action related to rule]?"
- "Does [mechanic] apply when [condition from rule]?"
- "What does rule {rule_number} say about [topic]?"

Output JSON:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Answers MUST:
- Be directly grounded in the rule text provided
- Reference the rule number
- Use correct MTG terminology
- Be 2-4 sentences

Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
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