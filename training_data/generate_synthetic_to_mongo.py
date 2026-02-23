#!/usr/bin/env python3
import sys
from typing import Collection; sys.stdout.reconfigure(line_buffering=True); sys.stderr.reconfigure(line_buffering=True)
"""
Synthetic Query Generator - Saves to MongoDB

Generates natural query examples using Qwen 14B and stores them in MongoDB.
The main extraction script then treats these as another data source!

Process:
1. Use Qwen 14B to generate Q&A from existing MongoDB data
2. Validate outputs
3. Save to synthetic_queries.queries collection
4. Main extraction script pulls from this collection like any other source

MongoDB Schema:
{
  "question": "What combos can I do with Pitiless Plunderer?",
  "answer": "Pitiless Plunderer combos with...",
  "category": "combo_query",  // or "card_search", "commander_rules", "multi_card"
  "source_data": ["card_name", ...],  // Cards/combos referenced
  "validated": true,
  "needs_review": false,
  "generated_at": "2026-02-13T..."
}
"""

from pymongo import MongoClient
import json
import random
import re
from datetime import datetime
import argparse
import time
import ollama


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

global MODEL_NAME
MODEL_NAME="qwen2.5:14b"  # Change to 14B when ready

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
# MONGODB SETUP
# =============================================================================

def get_mongo_collections(uri, username, password):
    """Connect and get all collections"""
    client = MongoClient(uri, username=username, password=password, authSource='admin')
    
    # Existing collections (source data)
    cards = client['mtg_json']['cards']
    combos = client['commander_spellbook']['variants']
    
    # New collection (synthetic data)
    synthetic = client['synthetic_queries']['queries']
    
    commanders = client['edhrec']['commanders']
    articles = client['edhrec']['articles']
    guides = client['edhrec']['guides']
    game_changers = client['edhrec']['game-changers']

    # Top cards by color
    top_cards = {
        'black':     client['edhrec']['top-black'],
        'blue':      client['edhrec']['top-blue'],
        'colorless': client['edhrec']['top-colorless'],
        'green':     client['edhrec']['top-green'],
        'red':       client['edhrec']['top-red'],
        'white':     client['edhrec']['top-white'],
    }

    # Rules collections
    rules = client['mtg_rules']['rules']
    glossary = client['mtg_rules']['glossary']

    return cards, combos, synthetic, commanders, rules, glossary, articles, guides, game_changers, top_cards


def save_to_mongo(synthetic_collection, examples, batch_size=500):
    """
    Save synthetic examples to MongoDB, skipping exact duplicates.

    Uses a hash of (question, answer) as a unique key so re-running
    the script never creates duplicate entries.
    """
    import hashlib

    if not examples:
        return

    print(f"\nSaving {len(examples):,} examples to MongoDB (dedup-safe)...")

    # Ensure unique index exists on content_hash (idempotent)
    try:
        synthetic_collection.create_index('content_hash', unique=True, background=True)
    except Exception:
        pass  # Index may already exist

    inserted = 0
    skipped = 0

    for i in range(0, len(examples), batch_size):
        batch = examples[i:i+batch_size]

        # Add metadata and content hash
        for ex in batch:
            q = ex.get('question', '')
            a = ex.get('answer', '')
            ex['content_hash'] = hashlib.sha256(f"{q}||{a}".encode()).hexdigest()
            ex['generated_at'] = datetime.utcnow()
            ex['version'] = 1

        # Insert only documents whose hash doesn't already exist
        from pymongo import UpdateOne
        ops = [
            UpdateOne(
                {'content_hash': ex['content_hash']},
                {'$setOnInsert': ex},
                upsert=True
            )
            for ex in batch
        ]

        try:
            result = synthetic_collection.bulk_write(ops, ordered=False)
            batch_inserted = result.upserted_count
            batch_skipped = len(batch) - batch_inserted
            inserted += batch_inserted
            skipped += batch_skipped
            print(f"  → Batch {i//batch_size + 1}: {batch_inserted} inserted, {batch_skipped} skipped (already existed)")
        except Exception as e:
            print(f"  ⚠️  Batch error: {e}")

    print(f"  ✓ Done: {inserted:,} inserted, {skipped:,} skipped as duplicates")


# =============================================================================
# MODEL QUERYING
# =============================================================================

def query_ollama(model_name: str, prompt: str, max_tokens=9999):
    """Query Ollama API"""
    start = time.time()
    print(f"\n{'─'*60}")
    print(f"  → PROMPT ({len(prompt)} chars, max_tokens={max_tokens}):")
    print(f"{'─'*60}")
    print(prompt)
    print(f"{'─'*60}")
    
    try:
        print(f"  → RESPONSE:")
        print(f"{'─'*60}")
        
        response_content = ""
        
        stream = ollama.chat(
            model=model_name, 
            messages=[{"role": "user", "content": prompt}], 
            stream=True,
            options= {
                "num_predict": max_tokens,
                'num_ctx': 8192, # Set the total context window size
                "temperature": 0.7
            })
        
        for chunk in stream:
            if 'message' in chunk and 'content' in chunk['message']:
                content_chunk = chunk['message']['content']
                print(content_chunk, end='', flush=True)
                response_content += content_chunk
        
        print(f"{'─'*60}")
        end = time.time()
        print(f"  ✓ Response generated in {end - start:.2f} seconds")
        return response_content.strip()
    except Exception as e:
        end = time.time()
        print(f"  ✗ Error querying Ollama: {type(e).__name__}: {e} (after {end - start:.2f} seconds)")
        raise e


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


# ============================================================================
# VALIDATION
# ============================================================================

def validate_with_model(model_name: str, card1: dict, card2: dict, qa: dict):
    """
    Ask the model to validate its own comparison answer
    
    Returns: (is_valid: bool, reason: str, score: int)
    """
    question = qa.get('question', '')
    answer = qa.get('answer', '')
    
    validation_prompt = build_card_validation_prompt(card1, card2, question, answer)

    try:
        response = query_ollama(model_name, validation_prompt)
        
        # Parse JSON response - handle common formatting issues
        response = response.replace("```json", "").replace("```", "").strip()
        
        # Try to extract JSON if there's extra text
        if not response.startswith('{'):
            # Find first { and last }
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                response = response[start:end+1]
        
        result = json.loads(response)
        
        score = result.get('score', 0)
        is_acceptable = result.get('is_acceptable', False)
        missing_info = result.get('missing_info', '')
        errors = result.get('errors', '')
        mechanical_accuracy = result.get('mechanical_accuracy', '')
        cost_comparison_correct = result.get('cost_comparison_correct', '')
        
        # Build detailed reason string
        reason_parts = []
        
        if errors:
            reason_parts.append(f"Errors: {errors}")
        
        if missing_info:
            reason_parts.append(f"Missing: {missing_info}")
        
        if mechanical_accuracy and 'incorrect' in mechanical_accuracy.lower():
            reason_parts.append(f"Mechanics: {mechanical_accuracy}")
        
        if cost_comparison_correct and 'incorrect' in cost_comparison_correct.lower():
            reason_parts.append(f"Costs: {cost_comparison_correct}")
        
        # Additional validation: if score is low, flag it
        if score < 7 and not errors:
            reason_parts.append(f"Low score ({score}/10)")
        
        # Build final reason
        if not is_acceptable or reason_parts:
            reason = "; ".join(reason_parts) if reason_parts else f"Score too low ({score}/10)"
        else:
            reason = "OK"
        
        # Extra safety check: if there are errors mentioned, force rejection
        if errors and errors.lower() not in ['none', 'n/a', '']:
            is_acceptable = False
            score = min(score, 4)  # Cap score at 4 if there are errors
        
        # Extra safety check: if mechanical accuracy is wrong, force rejection
        if mechanical_accuracy and any(word in mechanical_accuracy.lower() 
                                       for word in ['no', 'incorrect', 'wrong', 'false']):
            is_acceptable = False
            score = min(score, 4)
        
        return is_acceptable, reason, score
    
    except json.JSONDecodeError as e:
        print(f"    ⚠️  Failed to parse validation JSON: {e}")
        print(f"    Raw response: {response[:200]}...")
        # Be conservative - REJECT if we can't validate
        # (Changed from accepting by default)
        return False, f"Validation parse failed: {str(e)}", 0
    
    except Exception as e:
        print(f"    ⚠️  Validation error: {e}")
        # Be conservative - REJECT if validation fails
        return False, f"Validation error: {str(e)}", 0


def validate_qa(question: str, answer: str, context: str = "", category: str = "") -> tuple:
    """
    Generic Q&A validator — calls the model to score any question/answer pair.

    Used by all generation functions that lack card-specific validation.
    `context` should contain the source material the answer is grounded in
    (rule text, article content, archetype description, etc.).

    Returns: (is_valid: bool, reason: str, score: int)
    """
    prompt = build_qa_validation_prompt(question, answer, context, category)

    try:
        response = query_ollama(MODEL_NAME, prompt)
        response = response.replace("```json", "").replace("```", "").strip()
        if not response.startswith('{'):
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                response = response[start:end+1]

        result = json.loads(response)
        score = result.get('score', 0)
        is_acceptable = result.get('is_acceptable', False)
        errors = result.get('errors', '')
        reason = result.get('reason', f"Score {score}/10")

        # Force reject if errors mentioned
        if errors and errors.lower() not in ['none', 'n/a', '']:
            is_acceptable = False
            score = min(score, 4)

        return is_acceptable and score >= 7, reason, score

    except json.JSONDecodeError as e:
        print(f"    ⚠️  Validation JSON parse failed: {e}")
        return False, f"Validation parse failed: {str(e)}", 0
    except Exception as e:
        print(f"    ⚠️  Validation error: {e}")
        return False, f"Validation error: {str(e)}", 0


# =============================================================================
# GENERATION FUNCTIONS (adapted to save MongoDB format)
# =============================================================================

def generate_combo_queries(combos_collection: Collection, target_count=5000) -> list:
    """Generate combo queries - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} COMBO QUERIES ===")
    mongo_documents = []
    
    # Get combos grouped by card
    all_combos = list(combos_collection.find({'status': 'OK'}))
    
    combos_by_card = {}
    for combo in all_combos:
        cards = combo.get('uses', [])
        for card_info in cards:
            card_name = card_info.get('card', {}).get('name', '')
            if card_name:
                if card_name not in combos_by_card:
                    combos_by_card[card_name] = []
                combos_by_card[card_name].append(combo)
    
    cards_with_combos = [(card, combos) for card, combos in combos_by_card.items() if len(combos) >= 2]
    cards_with_combos.sort(key=lambda x: len(x[1]), reverse=True)
    
    print(f"  → Processing {len(cards_with_combos):,} cards...")
    
    for card_name, card_combos in cards_with_combos:
        if len(mongo_documents) >= target_count:
            break
        
        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")
        
        # Prepare combo data
        combo_descriptions = []
        for combo in card_combos[:5]:
            combo_cards = [c.get('card', {}).get('name', '') for c in combo.get('uses', []) if c.get('card')]
            description = combo.get('description', '')
            if len(combo_cards) >= 2 and description:
                combo_descriptions.append({'cards': combo_cards, 'description': description})
        
        if not combo_descriptions:
            continue
        
        # Build prompt
        combo_list = "\n".join([f"  - {' + '.join(c['cards'])}: {c['description']}" for c in combo_descriptions])
        
        prompt = build_combo_prompt(card_name, combo_list)

        try:
            response =  query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    # Validate
                    valid = any(combo_card in qa['answer'] for combo in combo_descriptions for combo_card in combo['cards'] if combo_card != card_name)

                    if valid:
                        # Create MongoDB document
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "combo_query",
                            "source_data": [card_name],
                            "validated": True,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED: {qa['question'][:80]}")

                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (no combo cards in answer): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        
        except Exception as e:
            print(f"  ✗ Error generating for {card_name}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} combo queries")
    return mongo_documents

def generate_card_search_queries(cards_collection: Collection, target_count=3000) -> list:
    """Generate card search queries - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} CARD SEARCH QUERIES ===")
    mongo_documents = []
    
    search_patterns = [
        {'name': 'Green ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
        {'name': 'Zombie tokens', 'query': {'text': {'$regex': 'zombie.*token', '$options': 'i'}}},
        {'name': 'Treasure tokens', 'query': {'text': {'$regex': 'treasure', '$options': 'i'}}},
        {'name': 'White removal', 'query': {'text': {'$regex': 'exile|destroy', '$options': 'i'}, 'colors': ['W']}},
        {'name': 'Blue card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'colors': ['U']}},
        {'name': 'ETB effects', 'query': {'text': {'$regex': 'enters the battlefield', '$options': 'i'}}},
        {'name': 'Black removal', 'query': {'text': {'$regex': 'destroy.*creature', '$options': 'i'}, 'colors': ['B']}},
        {'name': 'Red burn', 'query': {'text': {'$regex': 'deals.*damage', '$options': 'i'}, 'colors': ['R']}},
    ]
    
    for pattern in search_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['name']}")
        
        matching_cards = list(cards_collection.find(pattern['query'], {'name': 1, 'text': 1, 'manaCost': 1}).limit(15))
        
        if not matching_cards:
            continue
        
        card_info = "\n".join([f"  - {c.get('name', '')} ({c.get('manaCost', '')}): {c.get('text', '')[:100]}..." for c in matching_cards[:10]])
        card_names = [c.get('name', '') for c in matching_cards]
        
        prompt = build_card_search_prompt(pattern, card_info)

        try:
            response =  query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    mentioned = sum(1 for name in card_names if name in qa['answer'])

                    if mentioned >= 2:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "card_search",
                            "source_data": card_names[:5],
                            "search_pattern": pattern['name'],
                            "validated": True,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED ({mentioned} cards mentioned): {qa['question'][:80]}")

                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (only {mentioned}/2 cards mentioned): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating for {pattern['name']}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} card search queries")
    return mongo_documents


def generate_commander_knowledge(target_count=200) -> list[dict]:
    """Generate Commander knowledge - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} COMMANDER KNOWLEDGE ===")
    mongo_documents = []
    
    prompt = build_commander_prompt()

    try:
        response =  query_ollama(MODEL_NAME, prompt, max_tokens=9999)
        response = response.replace("```json", "").replace("```", "").strip()
        qa_pairs = json.loads(response)
        
        for qa in qa_pairs:
            if 'question' in qa and 'answer' in qa:
                is_valid, reason, score = validate_qa(
                    qa['question'], qa['answer'],
                    context="Commander format rules: 100-card singleton, commander in command zone, commander tax, commander damage, color identity restrictions.",
                    category="commander_rules"
                )
                if is_valid:
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "commander_rules",
                        "source_data": ["commander_format_rules"],
                        "validated": True,
                        "validation_score": score,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
            else:
                print(f"    ✗ REJECTED (missing question/answer keys): {qa}")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
    
    print(f"  ✓ Generated {len(mongo_documents):,} Commander rules")
    print(f"  ⚠️  Needs manual review!")
    return mongo_documents


def generate_multi_card_usage(combos_collection: Collection, target_count=2000) -> list[dict]:
    """Generate multi-card usage - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} MULTI-CARD USAGE ===")
    mongo_documents = []
    
    combos = list(combos_collection.find({'status': 'OK'}).limit(target_count * 2))
    
    for combo in combos:
        if len(mongo_documents) >= target_count:
            break
        
        cards = combo.get('uses', [])
        card_names = [c.get('card', {}).get('name', '') for c in cards if c.get('card')]
        description = combo.get('description', '')
        
        if len(card_names) < 2 or not description:
            continue
        
        card1, card2 = card_names[0], card_names[1]
        
        prompt = build_multi_card_usage_prompt(card1, card2, description)

        try:
            response =  query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Cards: {', '.join(card_names)}\nCombo/interaction: {description}",
                        category="multi_card_usage"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "multi_card_usage",
                            "source_data": card_names,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating for {card1} + {card2}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} multi-card usage")
    return mongo_documents


# =============================================================================
# PHASE 1: HIGH-VALUE QUESTION FORMATS (Easy + High Impact)
# =============================================================================

def generate_comparison_questions(cards_collection: Collection, target_count=2000) -> list[dict]:
    """
    Generate card comparison questions
    
    Examples:
    - "Which is better, Sol Ring or Mana Crypt?"
    - "Cultivate vs Kodama's Reach?"
    - "Should I run Lightning Bolt or Shock?"
    """
    print(f"\n=== GENERATING {target_count:,} COMPARISON QUESTIONS ===")
    mongo_documents = []
    
    # Define comparison patterns (cards with similar effects)
    comparison_patterns = [
        {'effect': 'fast mana', 'query': {'text': {'$regex': 'add.*mana|add {{C}}', '$options': 'i'}, 'type': {'$regex': 'Artifact'}}},
        {'effect': 'ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
        {'effect': 'removal', 'query': {'text': {'$regex': 'destroy|exile', '$options': 'i'}}},
        {'effect': 'card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}}},
        {'effect': 'counterspells', 'query': {'text': {'$regex': 'counter target', '$options': 'i'}, 'type': {'$regex': 'Instant'}}},
        {'effect': 'board wipes', 'query': {'text': {'$regex': 'destroy all|exile all', '$options': 'i'}}},
        {'effect': 'tutors', 'query': {'text': {'$regex': 'search.*library', '$options': 'i'}}},
        {'effect': 'reanimation', 'query': {'text': {'$regex': 'return.*creature.*graveyard', '$options': 'i'}}},
    ]
    
    for pattern in comparison_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['effect']}")
        
        # Get cards with similar effects
        similar_cards = list(cards_collection.find(
            pattern['query'],
            {'name': 1, 'text': 1, 'manaCost': 1, 'type': 1}
        ).limit(20))
        
        if len(similar_cards) < 2:
            continue
        
        # Generate comparisons between pairs
        for i in range(0, len(similar_cards) - 1, 2):
            if len(mongo_documents) >= target_count:
                break
            
            card1 = similar_cards[i]
            card2 = similar_cards[i + 1]
            
            card1_name = card1.get('name', '')
            card2_name = card2.get('name', '')
            
            if not card1_name or not card2_name:
                continue
            
            # Build prompt
            prompt = build_card_comparision_prompt(card1, card2)
            
            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for qa in qa_pairs:
                    # Basic structure check
                    if 'question' not in qa or 'answer' not in qa:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
                        continue
                    
                    # Quick check: at least one card mentioned (fast filter)
                    if card1_name not in qa['answer'] and card2_name not in qa['answer']:
                        print(f"    ✗ REJECTED (neither card in answer): {qa['question'][:80]}")
                        continue
                    
                    # Quick check: not too short
                    if len(qa['answer']) < 80:
                        print(f"    ✗ REJECTED (answer too short: {len(qa['answer'])} chars): {qa['question'][:80]}")
                        continue
                    
                    # Model-based validation (the smart filter!)
                    try:
                        is_valid, reason, score = validate_with_model(MODEL_NAME, card1, card2, qa)
                    except Exception as e:
                        print(f"    ⚠️  Validation failed ({e}), accepting by default")
                        is_valid = True
                        score = 5
                        reason = "validation_error"
                    
                    # Accept if score is 7 or higher
                    if is_valid and score >= 7:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "comparison",
                            "source_data": [card1_name, card2_name],
                            "effect_type": pattern['effect'],
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
            except Exception as e:
                print(f"  ✗ Error generating comparison for {card1_name} vs {card2_name}: {type(e).__name__}: {e}")
                continue

    print(f"  ✓ Generated {len(mongo_documents):,} comparison questions")
    return mongo_documents


def generate_reverse_lookup_questions(cards_collection: Collection, target_count=3000) -> list[dict]:
    """
    Generate reverse lookup questions (feature → card)
    
    Examples:
    - "What card lets me play lands from graveyard?"
    - "What creature tutors for artifacts?"
    - "What destroys all enchantments?"
    """
    print(f"\n=== GENERATING {target_count:,} REVERSE LOOKUP QUESTIONS ===")
    mongo_documents = []
    
    # Define searchable features
    feature_patterns = [
        {'feature': 'play lands from graveyard', 'regex': 'play.*land.*graveyard|land.*graveyard.*battlefield'},
        {'feature': 'tutor for artifacts', 'regex': 'search.*library.*artifact'},
        {'feature': 'tutor for creatures', 'regex': 'search.*library.*creature'},
        {'feature': 'destroy all creatures', 'regex': 'destroy all creature|destroy all nonland'},
        {'feature': 'destroy all artifacts', 'regex': 'destroy all artifact'},
        {'feature': 'destroy all enchantments', 'regex': 'destroy all enchantment|destroy target enchantment'},
        {'feature': 'exile from graveyard', 'regex': 'exile.*graveyard'},
        {'feature': 'return creatures from graveyard', 'regex': 'return.*creature.*graveyard'},
        {'feature': 'draw cards when creatures die', 'regex': 'draw.*card.*creature.*dies|creature dies.*draw'},
        {'feature': 'create treasure tokens', 'regex': 'create.*treasure|treasure token'},
        {'feature': 'create zombie tokens', 'regex': 'create.*zombie|zombie token'},
        {'feature': 'sacrifice creatures for value', 'regex': 'sacrifice.*creature.*draw|sacrifice.*creature.*mana'},
        {'feature': 'give creatures haste', 'regex': 'creatures.*have haste|creatures you control have haste'},
        {'feature': 'give creatures flying', 'regex': 'creatures.*have flying|creatures you control have flying'},
        {'feature': 'untap all creatures', 'regex': 'untap all creature|untap target creature'},
        {'feature': 'copy spells', 'regex': 'copy.*instant|copy.*sorcery|copy target spell'},
        {'feature': 'double mana', 'regex': 'double.*mana|add.*equal to'},
        {'feature': 'prevent combat damage', 'regex': 'prevent.*combat damage|creatures can.?t attack'},
    ]
    
    per_feature = target_count // len(feature_patterns)
    
    for pattern in feature_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['feature']}")
        
        # Find cards with this feature
        matching_cards = list(cards_collection.find(
            {'text': {'$regex': pattern['regex'], '$options': 'i'}},
            {'name': 1, 'text': 1, 'type': 1}
        ).limit(15))
        
        if not matching_cards:
            continue
        
        card_names = [c.get('name', '') for c in matching_cards]
        card_details = "\n".join([f"  - {c.get('name', '')}: {c.get('text', '')[:80]}..." for c in matching_cards[:5]])
        
        # Generate varied questions
        
        prompt = build_reverse_lookup_prompt(pattern, card_details)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    # Validate at least 2 cards mentioned
                    mentioned = sum(1 for name in card_names if name in qa['answer'])
                    if mentioned >= 2:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "reverse_lookup",
                            "source_data": card_names[:5],
                            "feature": pattern['feature'],
                            "validated": True,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED ({mentioned} cards mentioned): {qa['question'][:80]}")

                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (only {mentioned}/2 cards mentioned): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating reverse lookup for '{pattern['feature']}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} reverse lookup questions")
    return mongo_documents


def generate_synergy_questions(cards_collection: Collection, combos_collection: Collection, target_count=3000):
    """
    Generate synergy discovery questions
    
    Examples:
    - "What cards synergize with Sol Ring?"
    - "What goes well with treasure tokens?"
    - "What commander works with artifacts?"
    """
    print(f"\n=== GENERATING {target_count:,} SYNERGY QUESTIONS ===")
    mongo_documents = []
    
    # Get popular cards from combos
    all_combos = list(combos_collection.find({'status': 'OK'}).limit(5000))
    
    # Count card appearances in combos
    card_combo_count = {}
    for combo in all_combos:
        cards = combo.get('uses', [])
        for card_info in cards:
            card_name = card_info.get('card', {}).get('name', '')
            if card_name:
                card_combo_count[card_name] = card_combo_count.get(card_name, 0) + 1
    
    # Get top cards by combo appearances
    popular_cards = sorted(card_combo_count.items(), key=lambda x: x[1], reverse=True)[:200]
    
    print(f"  → Processing {len(popular_cards)} popular combo cards...")
    
    for card_name, combo_count in popular_cards:
        if len(mongo_documents) >= target_count:
            break
        
        if (len(mongo_documents) + 1) % 200 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")
        
        # Get card details
        card = cards_collection.find_one({'name': card_name})
        if not card:
            continue
        
        # Find combos with this card
        card_combos = [c for c in all_combos if card_name in str(c.get('uses', []))][:3]
        
        # Get synergy cards (cards that appear with this card in combos)
        synergy_cards = set()
        for combo in card_combos:
            cards = combo.get('uses', [])
            for c in cards:
                other_name = c.get('card', {}).get('name', '')
                if other_name and other_name != card_name:
                    synergy_cards.add(other_name)
        
        if not synergy_cards:
            continue
        
        prompt = build_synergy_prompt(card, synergy_cards)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    # Validate at least one synergy card mentioned
                    matched_synergies = [syn for syn in synergy_cards if syn in qa['answer']]
                    if matched_synergies:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "synergy",
                            "source_data": [card_name] + list(synergy_cards)[:5],
                            "validated": True,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (synergies: {', '.join(matched_synergies[:3])}): {qa['question'][:80]}")

                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (no synergy cards in answer): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating synergy for {card_name}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} synergy questions")
    return mongo_documents


def generate_budget_alternatives(cards_collection: Collection, target_count=2000) -> list[dict]:
    """
    Generate budget alternative questions
    
    Examples:
    - "What's a budget alternative to Mana Crypt?"
    - "Cheap replacement for Cyclonic Rift?"
    - "Under $5 cards that ramp?"
    """
    print(f"\n=== GENERATING {target_count:,} BUDGET ALTERNATIVE QUESTIONS ===")
    mongo_documents = []
    
    # Use rarity as proxy for price (Mythic/Rare = expensive, Uncommon/Common = budget)
    # Get expensive cards (Mythic/Rare staples)
    expensive_patterns = [
        {'effect': 'ramp', 'query': {'text': {'$regex': 'search.*land|add.*mana', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        {'effect': 'removal', 'query': {'text': {'$regex': 'destroy|exile', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        {'effect': 'card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        {'effect': 'tutors', 'query': {'text': {'$regex': 'search.*library', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
    ]
    
    for pattern in expensive_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['effect']}")
        
        # Get expensive cards
        expensive_cards = list(cards_collection.find(
            pattern['query'],
            {'name': 1, 'text': 1, 'rarity': 1}
        ).limit(10))
        
        # Get budget alternatives (uncommon/common with similar effect)
        budget_query = pattern['query'].copy()
        budget_query['rarity'] = {'$in': ['uncommon', 'common']}
        
        budget_cards = list(cards_collection.find(
            budget_query,
            {'name': 1, 'text': 1, 'rarity': 1}
        ).limit(15))
        
        if not expensive_cards or not budget_cards:
            continue
        
        # Generate alternatives for each expensive card
        for exp_card in expensive_cards[:5]:
            if len(mongo_documents) >= target_count:
                break
            
            exp_name = exp_card.get('name', '')
            if not exp_name:
                continue
            
            budget_names = [c.get('name', '') for c in budget_cards[:5]]
            budget_details = "\n".join([f"  - {c.get('name', '')} ({c.get('rarity', '')})" for c in budget_cards[:5]])
            
            prompt = build_budget_alternative_prompt(exp_card, budget_details)

            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for qa in qa_pairs:
                    if 'question' in qa and 'answer' in qa:
                        # Validate budget cards mentioned
                        matched_budget = [name for name in budget_names if name in qa['answer']]
                        if matched_budget:
                            print(f"    ✓ ACCEPTED (budget cards: {', '.join(matched_budget[:3])}): {qa['question'][:80]}")
                            mongo_documents.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "budget_alternative",
                                "source_data": [exp_name] + budget_names,
                                "expensive_card": exp_name,
                                "validated": True,
                                "needs_review": False
                            })
                        else:
                            print(f"    ✗ REJECTED (no budget cards in answer): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            except Exception as e:
                print(f"  ✗ Error generating budget alt for {exp_name}: {type(e).__name__}: {e}")
                continue
    
    print(f"  ✓ Generated {len(mongo_documents):,} budget alternative questions")
    return mongo_documents


# TODO Get common commanders from EDHREC data and generate questions about color identity and card legality in those decks
def generate_color_identity_questions(cards_collection: Collection, commanders_collection: Collection, target_count=2000) -> list[dict]:
    """
    Generate color identity questions
    
    Examples:
    - "Can I play Sol Ring in my Atraxa deck?"
    - "What's the color identity of Boros Charm?"
    - "Colorless cards for mono-red?"
    """
    print(f"\n=== GENERATING {target_count:,} COLOR IDENTITY QUESTIONS ===")
    mongo_documents = []
    
    # Sample diverse cards
    cards_sample = list(map(lambda c: { 'name': c.get('name'), 'colors': json.loads(c.get('colors')), 'colorIdentity': json.loads(c.get('colorIdentity')), 'manaCost': c.get('manaCost') }, cards_collection.find(
        {'colors': {'$exists': True}},
        {'name': 1, 'colors': 1, 'colorIdentity': 1, 'manaCost': 1}
    ).limit(500)))
    
    print(f"  → Processing {len(cards_sample)} cards...")
    
    # Common commander color identities
    commanders: list[dict] = commanders_collection.find(
        {'color_identity': {'$exists': True}},
        {'name': 1, 'color_identity': 1}
    ).limit(100)
    
    commander_identities = [
        ('mono-red deck', ['R']),
    ]
    
    for card in commanders:
        commander_identities.append((card.get('name'), card.get('color_identity')))
    
    for card in random.sample(cards_sample, min(200, len(cards_sample))):
        if len(mongo_documents) >= target_count:
            break
        
        card_name = card.get('name', '')
        card_colors = card.get('colorIdentity', card.get('colors', []))
        
        if not card_name:
            continue
        
        # Pick a random commander
        commander_name, commander_colors = random.choice(commander_identities)
        
        # Determine if card is legal
        card_color_set = set(card_colors) if card_colors else set()
        commander_color_set = set(commander_colors)
        is_legal = card_color_set.issubset(commander_color_set)

        prompt = build_color_identity_prompt(card, commander_name, commander_colors, is_legal)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "color_identity",
                        "source_data": [card_name, commander_name],
                        "card_colors": card_colors,
                        "commander_colors": commander_colors,
                        "is_legal": is_legal,
                        "validated": True,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED: {qa['question'][:80]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating color identity for {card_name}/{commander_name}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} color identity questions")
    return mongo_documents


def generate_quick_guidelines(target_count=2000) -> list[dict]:
    """
    Generate quick deckbuilding guideline questions
    
    Examples:
    - "How many lands in a 100-card deck?"
    - "How much ramp is enough?"
    - "How many board wipes should I run?"
    """
    print(f"\n=== GENERATING {target_count:,} QUICK GUIDELINE QUESTIONS ===")
    mongo_documents = []
    
    # Curated deckbuilding guidelines
    guidelines = [
        ("How many lands in a 100-card Commander deck?", "A typical Commander deck runs 36-40 lands, with 37-38 being most common. Adjust based on your average mana cost and amount of ramp."),
        ("How much ramp should I include?", "Include 8-12 ramp sources (mana rocks, land ramp spells, or mana dorks) to ensure consistent mana development."),
        ("How many board wipes should I run?", "Run 3-5 board wipes in most decks. More in control, fewer in aggressive strategies."),
        ("How much card draw do I need?", "Include 8-12 sources of card draw or card advantage. Commander games go long, and you need to keep your hand full."),
        ("How much removal should I include?", "Run 8-12 targeted removal spells. Include a mix of creature removal, artifact/enchantment removal, and flexible answers."),
        ("What's a good mana curve?", "Peak at 2-3 mana, with most spells costing 2-4 mana. Include some expensive bombs but keep your average CMC around 3-4."),
        ("How many creatures should I run?", "Most decks run 20-35 creatures. Creature-heavy strategies might run 35-40, while spell-based decks might run 15-20."),
        ("What's the right number of counterspells?", "Blue control decks typically run 5-8 counterspells. Include a mix of cheap counters and versatile ones."),
        ("How many tutors should I include?", "2-5 tutors is typical. More tutors make your deck more consistent but can make games repetitive."),
        ("What's a good balance of instant vs sorcery speed?", "Aim for 60-70% instant speed interaction when possible. Instant speed is more flexible in multiplayer."),
        ("How many win conditions do I need?", "Include 2-4 distinct ways to win. This ensures you can close out games and have backup plans."),
        ("How much protection should I run?", "Include 4-6 ways to protect your key pieces (counterspells, hexproof, indestructible, recursion)."),
        ("What's the right amount of recursion?", "3-5 recursion effects lets you recover from removal and board wipes without being excessive."),
        ("How many mana rocks for artifact-based ramp?", "5-8 mana rocks is typical, with Sol Ring and Arcane Signet being auto-includes in most decks."),
        ("How do I know if I have enough interaction?", "Aim for 12-15 total interaction pieces (removal, counterspells, board wipes, protection)."),
    ]
    
    print(f"  → Using {len(guidelines)} curated guidelines...")
    
    # Generate variations with Qwen
    for base_question, base_answer in guidelines:
        if len(mongo_documents) >= target_count:
            break
        
        prompt = build_quick_guidelines_prompt(base_question, base_answer)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Deckbuilding guideline: {base_question}\nExpected answer direction: {base_answer}",
                        category="guideline"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "guideline",
                            "source_data": ["deckbuilding_guidelines"],
                            "guideline_type": "deckbuilding",
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating guideline variation for '{base_question[:50]}...': {type(e).__name__}: {e}")
            # If generation fails, use original
            mongo_documents.append({
                "question": base_question,
                "answer": base_answer,
                "category": "guideline",
                "source_data": ["deckbuilding_guidelines"],
                "guideline_type": "deckbuilding",
                "validated": True,
                "needs_review": False
            })
    
    print(f"  ✓ Generated {len(mongo_documents):,} guideline questions")
    return mongo_documents


def generate_terminology_questions(target_count=1000):
    """
    Generate MTG terminology/slang questions
    
    Examples:
    - "What is CEDH?"
    - "What's a 'pillow fort'?"
    - "What does MLD stand for?"
    """
    print(f"\n=== GENERATING {target_count:,} TERMINOLOGY QUESTIONS ===")
    mongo_documents = []
    
    # Curated MTG terminology
    terminology = [
        ("CEDH", "CEDH stands for Competitive EDH (Elder Dragon Highlander/Commander). It's Commander played at the highest power level with optimized decks, fast combos, and competitive mindset."),
        ("pillow fort", "A 'pillow fort' is a defensive strategy that uses enchantments and effects to discourage opponents from attacking you, like Ghostly Prison, Propaganda, and Sphere of Safety."),
        ("MLD", "MLD stands for Mass Land Destruction - effects that destroy all or most lands, like Armageddon. It's generally frowned upon in casual Commander."),
        ("staple", "A 'staple' is a card that's commonly played across many decks because it's powerful and generically useful, like Sol Ring, Arcane Signet, or Swords to Plowshares."),
        ("salt", "In Commander, 'salt' refers to cards or strategies that make opponents unhappy or frustrated, often because they're seen as unfun or oppressive."),
        ("aristocrats", "Aristocrats is a sacrifice-based strategy that generates value from creatures dying, using cards like Blood Artist, Zulaport Cutthroat, and sacrifice outlets."),
        ("voltron", "Voltron is a strategy focused on making one creature (usually your commander) extremely large and powerful with equipment, auras, and buffs to win through commander damage."),
        ("group hug", "Group hug is a political strategy that gives benefits to all players (card draw, mana, etc.) to make friends and avoid being targeted, sometimes hiding a secret win condition."),
        ("stax", "Stax (from 'The Stacks') is a prison strategy that uses tax effects and restrictions to slow down opponents while you build towards a win."),
        ("GY", "GY is shorthand for 'graveyard' - the zone where cards go when they die, are discarded, or milled."),
        ("ETB", "ETB stands for 'enters the battlefield' - refers to triggered abilities that happen when a permanent comes into play."),
        ("LTB", "LTB stands for 'leaves the battlefield' - refers to triggered abilities when a permanent is removed from play."),
        ("ramp", "Ramp refers to cards and strategies that accelerate your mana production, letting you cast bigger spells earlier than usual."),
        ("tutor", "A tutor is any card that lets you search your library for specific cards, named after the card Demonic Tutor."),
        ("wheel", "A wheel effect forces all players to discard their hand and draw a new hand of seven cards, named after Wheel of Fortune."),
        ("pod", "Pod refers to sacrifice-and-search effects like Birthing Pod, letting you sacrifice a creature to find one that costs more."),
        ("blink", "Blink effects temporarily exile a creature and return it immediately, retriggering ETB abilities. Named after the card Momentary Blink."),
        ("flicker", "Flicker is synonymous with blink - temporarily exiling and returning permanents to retrigger ETB effects."),
        ("bounce", "Bounce means returning permanents from the battlefield to hand, like with Cyclonic Rift or Unsummon."),
        ("hatedraft", "Hatedraft means drafting a card not for your deck, but to prevent opponents from getting it. Not relevant in Commander but part of MTG terminology."),
    ]
    
    print(f"  → Using {len(terminology)} terms...")
    
    # Generate variations
    for term, definition in terminology:
        if len(mongo_documents) >= target_count:
            break
        
        # Create multiple question phrasings
        questions = [
            f"What is {term}?",
            f"What does {term} mean?",
            f"What's {term} in Magic?",
            f"Explain {term}",
            f"What does '{term}' refer to?",
        ]
        
        for question in questions[:3]:  # Use 3 variations per term
            if len(mongo_documents) >= target_count:
                break
            
            mongo_documents.append({
                "question": question,
                "answer": definition,
                "category": "terminology",
                "source_data": [term],
                "term": term,
                "validated": True,
                "needs_review": False
            })
    
    print(f"  ✓ Generated {len(mongo_documents):,} terminology questions")
    return mongo_documents


# =============================================================================
# EDHREC-GROUNDED GENERATION FUNCTIONS
# =============================================================================

def generate_article_qa(articles_collection, target_count=2000) -> list[dict]:
    """
    Generate Q&A grounded in EDHREC article content.
    Uses Qwen 14B to synthesize article advice into natural Q&A — not truncated raw text.

    Examples:
    - "What does this article recommend about building a sacrifice deck?"
    - "How should I approach land count in Commander?"
    """
    print(f"\n=== GENERATING {target_count:,} ARTICLE Q&A ===")
    mongo_documents = []

    print("  → Fetching articles from MongoDB...")
    all_articles = list(articles_collection.find(
        {'title': {'$exists': True}, 'content': {'$exists': True, '$ne': ''}},
        {'title': 1, 'content': 1}
    ))

    # Filter to articles with enough content to be useful
    good_articles = [a for a in all_articles if len(clean_html(a.get('content', ''))) > 300]
    random.shuffle(good_articles)
    print(f"  → Found {len(good_articles):,} articles with sufficient content")

    for article in good_articles:
        if len(mongo_documents) >= target_count:
            break

        title = article.get('title', '')
        # Clean HTML and take up to 2000 chars — enough context without overwhelming the prompt
        content = clean_html(article.get('content', ''))[:2000]

        if not title or not content:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_article_qa_prompt(title, content)

        try:
            response = query_ollama(MODEL_NAME, prompt, max_tokens=9999)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            accepted = 0
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Article: {title}\n{content[:500]}",
                        category="article_qa"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "article_qa",
                            "source_data": [title],
                            "article_title": title,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        accepted += 1
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")

            print(f"    ✓ ACCEPTED {accepted}/4 from: {title[:60]}")
        except Exception as e:
            print(f"  ✗ Error for article '{title[:50]}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} article Q&A examples")
    return mongo_documents


def generate_guide_qa(guides_collection, target_count=2000) -> list[dict]:
    """
    Generate Q&A grounded in EDHREC guide content.
    Guides are more instructional than articles — focus on how-to and best practices.

    Examples:
    - "How do I build a consistent mana base?"
    - "What mistakes do beginners make with Commander deckbuilding?"
    """
    print(f"\n=== GENERATING {target_count:,} GUIDE Q&A ===")
    mongo_documents = []

    print("  → Fetching guides from MongoDB...")
    all_guides = list(guides_collection.find(
        {'title': {'$exists': True}, 'content': {'$exists': True, '$ne': ''}},
        {'title': 1, 'content': 1}
    ))

    good_guides = [g for g in all_guides if len(clean_html(g.get('content', ''))) > 300]
    random.shuffle(good_guides)
    print(f"  → Found {len(good_guides):,} guides with sufficient content")

    for guide in good_guides:
        if len(mongo_documents) >= target_count:
            break

        title = guide.get('title', '')
        content = clean_html(guide.get('content', ''))[:2000]

        if not title or not content:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_guide_qa_prompt(title, content)

        try:
            response = query_ollama(MODEL_NAME, prompt, max_tokens=9999)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            accepted = 0
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Guide: {title}\n{content[:500]}",
                        category="guide_qa"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "guide_qa",
                            "source_data": [title],
                            "guide_title": title,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        accepted += 1
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")

            print(f"    ✓ ACCEPTED {accepted}/4 from: {title[:60]}")
        except Exception as e:
            print(f"  ✗ Error for guide '{title[:50]}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} guide Q&A examples")
    return mongo_documents


def generate_staple_analysis(game_changers_collection, target_count=2000) -> list[dict]:
    """
    Generate Q&A analyzing why game-changer cards are Commander staples.
    Uses num_decks and salt scores to ground the analysis.

    Examples:
    - "Why is Rhystic Study in 939K Commander decks?"
    - "Why do people hate Sol Ring at the table?"
    - "What kind of decks want Smothering Tithe?"
    """
    print(f"\n=== GENERATING {target_count:,} STAPLE ANALYSIS QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching game-changer cards from MongoDB...")
    all_changers = list(game_changers_collection.find(
        {'game_changer': True, 'oracle_text': {'$exists': True, '$ne': ''}},
        {'name': 1, 'oracle_text': 1, 'type': 1, 'mana_cost': 1,
         'num_decks': 1, 'salt': 1, 'tags': 1, 'color_identity': 1}
    ).sort('num_decks', -1))  # Sort by popularity

    print(f"  → Found {len(all_changers):,} game-changer cards")

    for card in all_changers:
        if len(mongo_documents) >= target_count:
            break

        name = card.get('name', '')
        if not name:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_staple_analysis_prompt(card)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            accepted = 0
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    # Validate: card name must appear in answer
                    if name not in qa['answer']:
                        continue
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "staple_analysis",
                        "source_data": [name],
                        "card_name": name,
                        "num_decks": card.get('num_decks', 0),
                        "salt": card.get('salt', 0),
                        "validated": True,
                        "needs_review": False
                    })
                    accepted += 1
                    if len(mongo_documents) >= target_count:
                        break

            print(f"    ✓ ACCEPTED {accepted}/3 from: {name}")
        except Exception as e:
            print(f"  ✗ Error for card '{name}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} staple analysis questions")
    return mongo_documents


def generate_color_staples(top_cards_dict, target_count=2000) -> list[dict]:
    """
    Generate Q&A about the top cards for each color in Commander.
    Uses EDHREC's top-color collections sorted by deck inclusion.

    Examples:
    - "What are the best Blue cards for Commander?"
    - "What Green ramp spells should I always include?"
    - "What colorless staples work in any Commander deck?"
    """
    print(f"\n=== GENERATING {target_count:,} COLOR STAPLE QUESTIONS ===")
    mongo_documents = []

    per_color = target_count // len(top_cards_dict)

    for color, collection in top_cards_dict.items():
        if len(mongo_documents) >= target_count:
            break

        print(f"  → Processing {color}...")

        # Get top cards for this color sorted by popularity
        top_cards = list(collection.find(
            {'oracle_text': {'$exists': True}},
            {'name': 1, 'oracle_text': 1, 'num_decks': 1, 'tags': 1,
             'type': 1, 'mana_cost': 1, 'color_identity': 1}
        ).sort('num_decks', -1).limit(30))

        if not top_cards:
            print(f"    ⚠️  No cards found for {color}")
            continue

        # Generate multiple batches using different subsets of top cards
        # so we get variety (top 10, next 10, etc.)
        subsets = [top_cards[:10], top_cards[10:20], top_cards[20:30]]

        color_docs = []
        for subset in subsets:
            if len(color_docs) >= per_color:
                break
            if not subset:
                continue

            prompt = build_color_staples_prompt(color, subset)

            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                if not response.startswith('['):
                    start = response.find('[')
                    end = response.rfind(']')
                    if start != -1 and end != -1:
                        response = response[start:end+1]
                qa_pairs = json.loads(response)

                card_names = [c.get('name', '') for c in subset]
                for qa in qa_pairs:
                    if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                        # Validate: at least 2 card names from the subset appear in the answer
                        mentioned = sum(1 for n in card_names if n in qa['answer'])
                        if mentioned < 2:
                            print(f"    ✗ REJECTED ({mentioned} cards mentioned): {qa['question'][:60]}")
                            continue
                        color_docs.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "color_staples",
                            "source_data": card_names[:5],
                            "color": color,
                            "validated": True,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED ({color}, {mentioned} cards): {qa['question'][:60]}")
                        if len(color_docs) >= per_color:
                            break
            except Exception as e:
                print(f"  ✗ Error for {color} subset: {type(e).__name__}: {e}")
                continue

        mongo_documents.extend(color_docs)
        print(f"  ✓ {color}: {len(color_docs):,} questions")

    print(f"  ✓ Generated {len(mongo_documents):,} color staple questions")
    return mongo_documents


def generate_salt_questions(game_changers_collection, target_count=1000) -> list[dict]:
    """
    Generate Q&A about controversial/salty cards — why they frustrate players,
    whether they're fair, and how to play around them.

    Examples:
    - "Why do people hate Cyclonic Rift?"
    - "Is Thassa's Oracle too powerful for casual Commander?"
    - "How do I play around Stax pieces?"
    """
    print(f"\n=== GENERATING {target_count:,} SALT QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching high-salt cards from MongoDB...")
    salty_cards = list(game_changers_collection.find(
        {'salt': {'$gte': 1.2}, 'oracle_text': {'$exists': True, '$ne': ''}},
        {'name': 1, 'oracle_text': 1, 'type': 1, 'mana_cost': 1,
         'num_decks': 1, 'salt': 1, 'tags': 1, 'color_identity': 1}
    ).sort('salt', -1))  # Saltiest first

    print(f"  → Found {len(salty_cards):,} high-salt cards (salt >= 1.2)")

    # Process in groups of 8 so each prompt covers multiple cards
    batch_size = 8
    batches = [salty_cards[i:i+batch_size] for i in range(0, len(salty_cards), batch_size)]

    for batch in batches:
        if len(mongo_documents) >= target_count:
            break

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_salt_prompt(batch)
        card_names = [c.get('name', '') for c in batch]

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    # Validate: at least one card name from batch in answer
                    mentioned = [n for n in card_names if n in qa['answer']]
                    if not mentioned:
                        print(f"    ✗ REJECTED (no card names in answer): {qa['question'][:60]}")
                        continue
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "salt_analysis",
                        "source_data": card_names,
                        "cards_mentioned": mentioned,
                        "validated": True,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED ({', '.join(mentioned[:2])}): {qa['question'][:60]}")
                    if len(mongo_documents) >= target_count:
                        break
        except Exception as e:
            print(f"  ✗ Error for salt batch: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} salt questions")
    return mongo_documents


# =============================================================================
# RULES-GROUNDED GENERATION FUNCTIONS
# =============================================================================

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


def generate_rule_explanations(rules_collection, target_count=2000) -> list[dict]:
    """
    Generate natural Q&A grounded in actual rule text.
    Each Q&A is traceable back to a specific rule number.

    Examples:
    - "What does rule 702.2 say about flying?"
    - "Can a creature with flying block a ground creature?"
    - "What happens when a creature with flying attacks?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE EXPLANATION QUESTIONS ===")
    mongo_documents = []

    # Fetch rules from relevant sections — skip overly short or administrative rules
    print("  → Fetching rules from MongoDB...")
    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$ne': '', '$not': {'$regex': r'^See rule \d'}}},
        {'rule_number': 1, 'text': 1}
    ))

    # Filter to rules with meaningful content (>50 chars) and shuffle for variety
    meaningful_rules = [r for r in all_rules if len(r.get('text', '')) > 50]
    random.shuffle(meaningful_rules)
    print(f"  → Found {len(meaningful_rules):,} meaningful rules")

    for rule in meaningful_rules:
        if len(mongo_documents) >= target_count:
            break

        rule_num = rule.get('rule_number', '')
        rule_text = rule.get('text', '')

        if not rule_num or not rule_text:
            continue

        if (len(mongo_documents) + 1) % 200 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_explanation_prompt(rule_num, rule_text)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            # Handle array wrapped in extra brackets
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    # Validate: answer must reference the rule number
                    if rule_num not in qa['answer']:
                        print(f"    ✗ REJECTED (rule number not in answer): {qa['question'][:60]}")
                        continue
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "rule_explanation",
                        "source_data": [f"rule_{rule_num}"],
                        "rule_number": rule_num,
                        "rule_text": rule_text,
                        "validated": True,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED (rule {rule_num}): {qa['question'][:70]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rule {rule_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule explanation questions")
    return mongo_documents


def generate_rule_interactions(rules_collection, target_count=2000) -> list[dict]:
    """
    Generate scenario Q&A where two rules interact.
    Grounded in actual rule text from both rules.

    Examples:
    - "I have a creature with deathtouch that deals 1 damage to a 5/5. What happens?" (702.2 + 704.5g)
    - "A triggered ability and a state-based action happen simultaneously. Which applies first?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE INTERACTION QUESTIONS ===")
    mongo_documents = []

    # Fetch rules and group by section for pairing rules from related sections
    print("  → Fetching rules for interaction pairing...")
    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$not': {'$regex': r'^See rule \d'}}, },
        {'rule_number': 1, 'text': 1}
    ))

    meaningful_rules = [r for r in all_rules if len(r.get('text', '')) > 60]

    # Group rules by top-level section number
    rules_by_section = {}
    for rule in meaningful_rules:
        num = rule.get('rule_number', '')
        section = num.split('.')[0] if '.' in num else num[:3]
        if section not in rules_by_section:
            rules_by_section[section] = []
        rules_by_section[section].append(rule)

    print(f"  → Grouped into {len(rules_by_section)} sections")

    # Define section pairs that commonly interact in real games
    interaction_pairs = [
        ('601', '116'),  # Casting spells + Priority
        ('603', '116'),  # Triggered abilities + Priority
        ('603', '704'),  # Triggered abilities + State-based actions
        ('608', '603'),  # Resolving spells + Triggered abilities
        ('702', '120'),  # Keyword abilities + Damage
        ('702', '704'),  # Keyword abilities + State-based actions
        ('706', '603'),  # Copying + Triggered abilities
        ('601', '117'),  # Casting + Costs
        ('700', '116'),  # Additional rules + Priority
        ('800', '116'),  # Multiplayer + Priority
        ('903', '603'),  # Commander + Triggered abilities
        ('120', '704'),  # Damage + State-based actions
        ('118', '117'),  # Paying costs + Costs
        ('604', '603'),  # Static abilities + Triggered abilities
    ]

    attempts = 0
    max_attempts = target_count * 3

    while len(mongo_documents) < target_count and attempts < max_attempts:
        attempts += 1

        # Pick a section pair
        sec1, sec2 = random.choice(interaction_pairs)

        rules1 = rules_by_section.get(sec1, [])
        rules2 = rules_by_section.get(sec2, [])

        if not rules1 or not rules2:
            continue

        rule1 = random.choice(rules1)
        rule2 = random.choice(rules2)

        rule1_num = rule1.get('rule_number', '')
        rule1_text = rule1.get('text', '')
        rule2_num = rule2.get('rule_number', '')
        rule2_text = rule2.get('text', '')

        if not all([rule1_num, rule1_text, rule2_num, rule2_text]):
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_interaction_prompt(rule1_num, rule1_text, rule2_num, rule2_text)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    # Validate: both rule numbers must appear in the answer
                    has_rule1 = rule1_num in qa['answer']
                    has_rule2 = rule2_num in qa['answer']
                    if not has_rule1 or not has_rule2:
                        print(f"    ✗ REJECTED (missing rule refs r1:{has_rule1} r2:{has_rule2}): {qa['question'][:60]}")
                        continue
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "rule_interaction",
                        "source_data": [f"rule_{rule1_num}", f"rule_{rule2_num}"],
                        "rule_numbers": [rule1_num, rule2_num],
                        "sections": [sec1, sec2],
                        "validated": True,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED (rules {rule1_num}+{rule2_num}): {qa['question'][:70]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rules {rule1_num}+{rule2_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule interaction questions")
    return mongo_documents


def generate_glossary_with_examples(glossary_collection, target_count=1500) -> list[dict]:
    """
    Generate Q&A from glossary terms with concrete in-game examples.
    Grounded in the official glossary definition — not just "what does X mean".

    Examples:
    - "Give me an example of deathtouch in a game."
    - "How does lifelink work in practice?"
    - "What's the difference between exile and destroy?"
    """
    print(f"\n=== GENERATING {target_count:,} GLOSSARY WITH EXAMPLES QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching glossary terms from MongoDB...")
    all_terms = list(glossary_collection.find(
        {'word': {'$exists': True}, 'definition': {'$exists': True, '$ne': ''}},
        {'word': 1, 'definition': 1}
    ))

    # Filter to terms with meaningful definitions
    meaningful_terms = [t for t in all_terms if len(t.get('definition', '')) > 30]
    random.shuffle(meaningful_terms)
    print(f"  → Found {len(meaningful_terms):,} glossary terms")

    for term_doc in meaningful_terms:
        if len(mongo_documents) >= target_count:
            break

        term = term_doc.get('word', '')
        definition = term_doc.get('definition', '')

        if not term or not definition:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_glossary_with_examples_prompt(term, definition)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Term: {term}\nDefinition: {definition}",
                        category="glossary_with_examples"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "glossary_with_examples",
                            "source_data": [f"glossary_{term}"],
                            "term": term,
                            "definition": definition,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10, {term}): {qa['question'][:70]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for term '{term}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} glossary with examples questions")
    return mongo_documents


def generate_rule_edge_cases(rules_collection, target_count=1500) -> list[dict]:
    """
    Generate tricky edge case questions from complex rule sections.
    Designed to trip up experienced players, not beginners.

    Examples:
    - "Players often think X. What does rule 704.5g actually say?"
    - "If a creature has both deathtouch and indestructible assigned to it, what happens?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE EDGE CASE QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching rules from complex sections...")
    # Only fetch from sections known to be tricky
    complex_section_prefixes = list(COMPLEX_RULE_SECTIONS.keys())

    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$ne': '', '$not': {'$regex': r'^See rule \d'}}},
        {'rule_number': 1, 'text': 1}
    ))

    # Filter to rules from complex sections with substantial text
    complex_rules = []
    for rule in all_rules:
        num = rule.get('rule_number', '')
        text = rule.get('text', '')
        if len(text) < 80:
            continue
        # Check if this rule is in a complex section
        for prefix in complex_section_prefixes:
            if num.startswith(prefix):
                section_name = COMPLEX_RULE_SECTIONS[prefix]
                rule['section_name'] = section_name
                complex_rules.append(rule)
                break

    random.shuffle(complex_rules)
    print(f"  → Found {len(complex_rules):,} rules in complex sections")

    for rule in complex_rules:
        if len(mongo_documents) >= target_count:
            break

        rule_num = rule.get('rule_number', '')
        rule_text = rule.get('text', '')
        section_name = rule.get('section_name', 'General Rules')

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_edge_case_prompt(rule_num, rule_text, section_name)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    if rule_num not in qa['answer']:
                        print(f"    ✗ REJECTED (rule number not cited): {qa['question'][:60]}")
                        continue
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "rule_edge_case",
                        "source_data": [f"rule_{rule_num}"],
                        "rule_number": rule_num,
                        "section": section_name,
                        "rule_text": rule_text,
                        "validated": True,
                        "needs_review": True  # Edge cases warrant a review pass
                    })
                    print(f"    ✓ ACCEPTED (rule {rule_num}, {section_name}): {qa['question'][:60]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rule {rule_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule edge case questions")
    return mongo_documents


def generate_rule_why_questions(rules_collection, target_count=1000) -> list[dict]:
    """
    Generate backward-reasoning 'why does this work' questions grounded in rule text.
    Teaches the underlying principle, not just the surface ruling.

    Examples:
    - "Why can't I respond to a mana ability?"
    - "Why does damage use the stack but destroy doesn't?"
    - "Why does a copy of a spell not have the same targets as the original?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE WHY QUESTIONS ===")
    mongo_documents = []

    # Focus on rules that have interesting underlying principles
    principle_sections = ['116', '117', '118', '120', '601', '602', '603', '604',
                          '608', '700', '701', '702', '704', '706']

    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$not': {'$regex': r'^See rule \d'}}},
        {'rule_number': 1, 'text': 1}
    ))

    # Filter to principle sections with substantial text
    principle_rules = []
    for rule in all_rules:
        num = rule.get('rule_number', '')
        text = rule.get('text', '')
        if len(text) < 100:
            continue
        for prefix in principle_sections:
            if num.startswith(prefix):
                principle_rules.append(rule)
                break

    random.shuffle(principle_rules)
    print(f"  → Found {len(principle_rules):,} principle rules")

    for rule in principle_rules:
        if len(mongo_documents) >= target_count:
            break

        rule_num = rule.get('rule_number', '')
        rule_text = rule.get('text', '')

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_why_prompt(rule_num, rule_text)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    if rule_num not in qa['answer']:
                        print(f"    ✗ REJECTED (rule not cited): {qa['question'][:60]}")
                        continue
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "rule_why",
                        "source_data": [f"rule_{rule_num}"],
                        "rule_number": rule_num,
                        "rule_text": rule_text,
                        "validated": True,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED (rule {rule_num}): {qa['question'][:70]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rule {rule_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule why questions")
    return mongo_documents


# =============================================================================
# NEW GENERATION FUNCTIONS
# =============================================================================

def generate_deckbuilding_theory(target_count=2000) -> list[dict]:
    """
    Generate deckbuilding theory Q&A covering card evaluation, ratios, construction principles.

    Examples:
    - "How do I evaluate whether a card earns its slot?"
    - "What's the difference between card advantage and card selection?"
    - "How do I know when to cut cards during tuning?"
    """
    print(f"\n=== GENERATING {target_count:,} DECKBUILDING THEORY QUESTIONS ===")
    mongo_documents = []

    topics = [
        (
            "card evaluation and slot justification",
            "How to determine if a card belongs in your deck, evaluating cards on rate, role, and redundancy."
        ),
        (
            "card advantage vs card selection",
            "The difference between drawing more cards (Rhystic Study) vs filtering cards (Ponder). When each matters."
        ),
        (
            "mana curve and tempo",
            "How to build a mana curve, what tempo means, why you want to spend mana efficiently each turn."
        ),
        (
            "redundancy and consistency",
            "Why you run multiple effects that do similar things, how to determine the right amount of redundancy."
        ),
        (
            "synergy vs goodstuff",
            "The tradeoff between running powerful generic cards vs cards that specifically support your strategy."
        ),
        (
            "win conditions and closing games",
            "How to identify your win conditions, ensure they're reachable, and have enough redundancy to close games."
        ),
        (
            "deck tuning and iteration",
            "How to identify what's wrong with a deck after testing, what to cut, what to add, how to iterate."
        ),
        (
            "threat density and role assignment",
            "Assigning cards roles (threat, answer, engine, accelerant) and ensuring the right density of each."
        ),
        (
            "mana base construction",
            "How to build a mana base, dual lands vs basics, color ratios, when to run utility lands."
        ),
        (
            "protection and resilience",
            "How to protect your key pieces, recover from board wipes, maintain card advantage after setbacks."
        ),
        (
            "interaction and removal philosophy",
            "When to hold up interaction vs advance your game plan, reactive vs proactive playstyles."
        ),
        (
            "tribal deck construction",
            "Special considerations for tribal decks: lord effects, creature density, tribal synergies, non-creature support."
        ),
    ]

    for topic, context in topics:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {topic}")
        prompt = build_deckbuilding_theory_prompt(topic, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Topic: {topic}\nContext: {context}",
                        category="deckbuilding_theory"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "deckbuilding_theory",
                            "source_data": ["deckbuilding_theory"],
                            "topic": topic,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for topic '{topic}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} deckbuilding theory questions")
    return mongo_documents


def generate_commander_building(target_count=3000) -> list[dict]:
    """
    Generate Commander-specific deckbuilding Q&A for various archetypes and strategies.

    Examples:
    - "How do I build around a sacrifice commander?"
    - "What's the right threat density for a control commander?"
    - "How do I balance synergy vs goodstuff in Commander?"
    """
    print(f"\n=== GENERATING {target_count:,} COMMANDER BUILDING QUESTIONS ===")
    mongo_documents = []

    archetypes = [
        (
            "sacrifice/aristocrats",
            "Decks that sacrifice creatures for value, using Blood Artist-style effects, sac outlets, and token generators. Key challenge: balancing fodder, payoffs, and sac outlets."
        ),
        (
            "spellslinger/magecraft",
            "Decks that cast lots of instants and sorceries, using magecraft triggers, prowess, and spell-based win conditions. Key challenge: protecting your win condition while staying low to the ground."
        ),
        (
            "token swarm",
            "Decks that generate many creature tokens and win through wide attacks or combo. Key challenge: having enough anthems and ways to win through chump blockers."
        ),
        (
            "reanimator",
            "Decks that put big creatures in the graveyard and reanimate them cheaply. Key challenge: filling the graveyard, protecting the reanimation target, winning with the reanimated creature."
        ),
        (
            "combo",
            "Decks that assemble a specific combination of cards to win instantly or lock opponents out. Key challenge: finding the combo pieces, protecting the combo, having backup win conditions."
        ),
        (
            "control",
            "Decks that answer every threat and win through superior card advantage in the late game. Key challenge: staying relevant in multiplayer, having a win condition that can close through disruption."
        ),
        (
            "voltron",
            "Decks that buff one creature (usually the commander) with equipment and auras to win through commander damage. Key challenge: protecting your commander, rebuilding after removal, winning through 21 combat damage."
        ),
        (
            "stax/prison",
            "Decks that use symmetrical or asymmetrical effects to slow opponents while you advance your own game plan. Key challenge: calibrating the lock pieces so you can still win, not making the game unfun."
        ),
        (
            "landfall/lands matter",
            "Decks that trigger off lands entering the battlefield, using extra land effects and landfall payoffs. Key challenge: getting enough lands into play per turn, balancing consistency with power."
        ),
        (
            "graveyard value",
            "Decks that use the graveyard as a resource without necessarily being reanimator — flashback, delve, threshold, cycling. Key challenge: filling the graveyard efficiently, playing around graveyard hate."
        ),
        (
            "turbo draw/card advantage",
            "Decks built around drawing as many cards as possible to find combo pieces or assemble overwhelming card advantage. Key challenge: using the cards drawn effectively, not decking yourself."
        ),
        (
            "midrange goodstuff",
            "Decks that play powerful cards at every part of the curve without a focused synergy strategy. Key challenge: distinguishing this from a tuned synergy deck, knowing when to choose goodstuff over theme."
        ),
    ]

    for archetype, context in archetypes:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {archetype}")
        prompt = build_commander_building_prompt(archetype, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Archetype: {archetype}\nContext: {context}",
                        category="commander_building"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "commander_building",
                            "source_data": ["commander_format"],
                            "archetype": archetype,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for archetype '{archetype}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} Commander building questions")
    return mongo_documents


def generate_rules_scenarios(target_count=3000) -> list[dict]:
    """
    Generate scenario-based rules Q&A that teaches rules reasoning.

    Examples:
    - "I cast Lightning Bolt, they respond with Giant Growth. What happens?"
    - "My creature has lifelink and deathtouch. What happens when it deals damage?"
    - "Can I activate a planeswalker ability the turn it enters?"
    """
    print(f"\n=== GENERATING {target_count:,} RULES SCENARIO QUESTIONS ===")
    mongo_documents = []

    scenarios = [
        (
            "spell resolution and the stack",
            "Last in first out stack resolution, responding to spells, fizzling spells, counterspells"
        ),
        (
            "combat damage and blocking",
            "Assigning combat damage, trample, first strike, double strike, deathtouch in combat, lifelink in combat"
        ),
        (
            "triggered abilities and timing",
            "When triggered abilities go on the stack, controlling the order of your own triggers, missed triggers"
        ),
        (
            "state-based actions",
            "Creatures dying from lethal damage or 0 toughness, legend rule, planeswalker uniqueness rule, poison counters"
        ),
        (
            "activated abilities and costs",
            "Paying costs for activated abilities, tapping as a cost, sacrifice as a cost, mana abilities"
        ),
        (
            "replacement effects and prevention effects",
            "How replacement effects modify events, prevention effects, damage prevention, redirection"
        ),
        (
            "keyword abilities interactions",
            "How keywords interact: hexproof vs targeting, shroud vs targeting, indestructible vs destroy vs exile, regenerate"
        ),
        (
            "Commander-specific rules",
            "Commander tax, commander damage, moving to command zone vs graveyard, color identity in deck building"
        ),
        (
            "planeswalker rules",
            "Activating planeswalker abilities, attacking planeswalkers, the planeswalker uniqueness rule, loyalty counters"
        ),
        (
            "token and copy rules",
            "Creating tokens, copying spells, copying permanents, token characteristics, copy effects on the stack"
        ),
        (
            "priority and passing priority",
            "When players receive priority, how to sequence actions, when you can and cannot respond"
        ),
        (
            "enters the battlefield and leaves the battlefield triggers",
            "ETB triggers, LTB triggers, flicker effects, blink, phasing, bouncing permanents"
        ),
        (
            "targeting and illegal targets",
            "Choosing targets on announcement, targets becoming illegal before resolution, fizzling"
        ),
        (
            "mana and casting",
            "Mana pool, emptying the mana pool, split second, flash, timing restrictions for casting spells"
        ),
        (
            "graveyard and exile interactions",
            "Cards going to graveyard, replacement effects for dying, exile vs graveyard, returning from exile"
        ),
    ]

    for scenario, rules in scenarios:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {scenario}")
        prompt = build_rules_scenario_prompt(scenario, rules)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Rules topic: {scenario}\nRelevant rules: {rules}",
                        category="rules_scenario"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "rules_scenario",
                            "source_data": ["comprehensive_rules"],
                            "rules_topic": scenario,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for scenario '{scenario}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rules scenario questions")
    return mongo_documents


def generate_archetypes(target_count=1500) -> list[dict]:
    """
    Generate deck archetype and strategy Q&A.

    Examples:
    - "How does a stax deck win?"
    - "What are the weaknesses of voltron?"
    - "How do I recognize a storm deck?"
    """
    print(f"\n=== GENERATING {target_count:,} ARCHETYPE QUESTIONS ===")
    mongo_documents = []

    archetypes = [
        (
            "stax/prison",
            "Stax uses symmetrical and asymmetrical tax effects and lock pieces to slow opponents to a crawl. Win conditions are usually faster mana and hatebears. Cards like Smokestack, Winter Orb, Sphere of Resistance, and Cursed Totem."
        ),
        (
            "storm/spellslinger combo",
            "Storm decks chain spells to generate a large storm count and win with Tendrils of Agony or Brain Freeze. Require rituals, cantrips, and a way to win at high storm count. Fragile to counterspells."
        ),
        (
            "aggro/tempo",
            "Aggressive decks develop threats quickly and attack the opponent's life total before they can set up. Rely on efficient creatures, haste, and pump spells. Weaker in longer games."
        ),
        (
            "hard control",
            "Control decks answer every threat with counterspells, removal, and board wipes, winning with a single powerful threat in the late game. Card advantage is paramount."
        ),
        (
            "midrange",
            "Midrange decks play powerful cards at every mana cost and win through card quality rather than synergy. Flexible but less explosive than combo or aggro."
        ),
        (
            "infinite combo",
            "Infinite combo decks assemble two or more cards that create an infinite loop — infinite mana, infinite creatures, infinite damage. Win immediately on assembly."
        ),
        (
            "reanimator",
            "Reanimator puts large expensive creatures into the graveyard cheaply (via discard, mill, or self-mill) and brings them back for cheap. Fast and resilient but weak to graveyard hate."
        ),
        (
            "aristocrats/sacrifice",
            "Aristocrats generates value from creatures dying repeatedly. Uses Blood Artist-style effects, recursive creatures, and sacrifice outlets to drain opponents incrementally."
        ),
        (
            "tokens/go wide",
            "Token strategies flood the board with small creatures and win through wide attacks, token doublers, or sacrifice payoffs. Weak to board wipes, strong against single-target removal."
        ),
        (
            "voltron",
            "Voltron buffs one creature to enormous size and wins through combat damage, often specifically 21 commander damage. Equipment-based voltron is more resilient than aura-based."
        ),
        (
            "group hug",
            "Group hug gives all players resources (card draw, mana, etc.) to stay out of the crosshairs while building toward a secret win condition. Political and unique playstyle."
        ),
        (
            "lands/landfall",
            "Lands-matter decks maximize land drops per turn and use landfall triggers to generate value. Often use extra land effects, land recursion, and powerful landfall payoffs."
        ),
    ]

    for archetype, context in archetypes:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {archetype}")
        prompt = build_archetype_prompt(archetype, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Archetype: {archetype}\nContext: {context}",
                        category="archetype"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "archetype",
                            "source_data": ["strategy"],
                            "archetype": archetype,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for archetype '{archetype}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} archetype questions")
    return mongo_documents


def generate_game_theory(target_count=1500) -> list[dict]:
    """
    Generate game theory and decision-making Q&A.

    Examples:
    - "When should I use removal on a creature vs holding it?"
    - "How do I evaluate whether a hand is worth keeping?"
    - "When is it correct to attack the player in the lead?"
    """
    print(f"\n=== GENERATING {target_count:,} GAME THEORY QUESTIONS ===")
    mongo_documents = []

    situations = [
        (
            "threat assessment and removal sequencing",
            "Deciding which threats to answer immediately vs ignore, when to hold removal, opportunity cost of using removal early"
        ),
        (
            "opening hand evaluation and mulliganing",
            "What makes a hand keepable, when to mulligan, evaluating land count, curve, and role of each card in opening hand"
        ),
        (
            "sequencing spells for maximum efficiency",
            "Playing around counterspells, ordering your spells to maximize impact, sandbagging threats"
        ),
        (
            "mana efficiency and tempo",
            "Spending all your mana every turn, tempo advantage, knowing when to hold up mana vs spend it"
        ),
        (
            "multiplayer politics and deal-making",
            "When to make deals in Commander, how to evaluate political deals, threat perception, being the archenemy"
        ),
        (
            "threat perception and table dynamics",
            "Recognizing who is ahead, when to team up vs go it alone, threat ordering in multiplayer"
        ),
        (
            "when to go all-in vs play conservatively",
            "Assessing when it's correct to commit your hand to the board vs hold back, playing around sweepers"
        ),
        (
            "card advantage decisions",
            "When to use your card draw, whether to refill your hand or deploy threats, resource management"
        ),
        (
            "combat math and blocking decisions",
            "How to evaluate attack and block decisions, when to take damage vs trade creatures, alpha strikes"
        ),
        (
            "timing your win attempt",
            "Reading the table to know when to go for the win, when opponents are tapped out, winning through disruption"
        ),
    ]

    for situation, context in situations:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {situation}")
        prompt = build_game_theory_prompt(situation, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Situation: {situation}\nContext: {context}",
                        category="game_theory"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "game_theory",
                            "source_data": ["strategy"],
                            "situation_type": situation,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for situation '{situation}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} game theory questions")
    return mongo_documents


def generate_meta_knowledge(target_count=1000) -> list[dict]:
    """
    Generate meta and power level Q&A covering cEDH, pod dynamics, and format knowledge.

    Examples:
    - "What makes a deck cEDH viable?"
    - "How do I calibrate my deck's power level?"
    - "What separates a 7/10 from a 9/10 Commander deck?"
    """
    print(f"\n=== GENERATING {target_count:,} META KNOWLEDGE QUESTIONS ===")
    mongo_documents = []

    topics = [
        (
            "cEDH viability and what separates competitive from casual",
            "cEDH decks win on turns 3-5, use fast mana (Mana Crypt, Chrome Mox), run tutors, counterspells, and win through established combo lines. Power level 9-10."
        ),
        (
            "Commander power level scale (1-10)",
            "The 1-10 power level scale: 1-3 precon/kitchen table, 4-6 focused casual, 7-8 optimized synergy, 9 high power, 10 cEDH. How to self-assess your deck."
        ),
        (
            "pod communication and power level matching",
            "How to communicate your deck's power level to your pod, why mismatched power levels ruin games, asking before you sit down."
        ),
        (
            "fast mana and why it's powerful",
            "Sol Ring, Mana Crypt, Chrome Mox — why fast mana is so format-warping, what separates high power from casual, the role of 0-cost acceleration."
        ),
        (
            "tutors and deck consistency",
            "How tutors increase consistency, why tutors are stronger in Commander than other formats, the tradeoff between consistency and fun."
        ),
        (
            "common cEDH win conditions and strategies",
            "Flash Hulk, Thassa's Oracle + Demonic Consultation, Underworld Breach loops, Dockside Extortionist combos — recognizing and playing against them."
        ),
        (
            "evaluating commanders for power level",
            "What makes a commander powerful: built-in card advantage, low mana cost, combo enabler, resilience. Why some commanders are format staples."
        ),
        (
            "meta reads and adapting your deck",
            "Reading your local meta, building hate for common strategies, adjusting your deck for the environment you play in."
        ),
        (
            "banned list philosophy in Commander",
            "Why certain cards are banned in Commander (Flash, Primeval Titan, Braids), how the rules committee evaluates bans, why some powerful cards aren't banned."
        ),
    ]

    for topic, context in topics:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {topic}")
        prompt = build_meta_knowledge_prompt(topic, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Topic: {topic}\nContext: {context}",
                        category="meta_knowledge"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "meta_knowledge",
                            "source_data": ["meta_strategy"],
                            "topic": topic,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for topic '{topic}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} meta knowledge questions")
    return mongo_documents


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017/')
    parser.add_argument('--mongo-user', default='root')
    parser.add_argument('--mongo-pass', default='whatever')
    
    # Original formats
    parser.add_argument('--combo-queries', type=int, default=0)
    parser.add_argument('--card-search', type=int, default=0)
    parser.add_argument('--commander', type=int, default=0)
    parser.add_argument('--multi-card', type=int, default=0)
    parser.add_argument('--model', type=str, default='qwen2.5:14b', help='Ollama model name for generation and validation')
    
    # Phase 1 formats
    parser.add_argument('--comparison', type=int, default=0, help='Card comparison questions')
    parser.add_argument('--reverse-lookup', type=int, default=0, help='Feature-to-card lookup')
    parser.add_argument('--synergy', type=int, default=0, help='Card synergy discovery')
    parser.add_argument('--budget', type=int, default=0, help='Budget alternatives')
    parser.add_argument('--color-identity', type=int, default=0, help='Color identity questions')
    parser.add_argument('--guidelines', type=int, default=0, help='Deckbuilding guidelines')
    parser.add_argument('--terminology', type=int, default=0, help='MTG terminology/slang')

    # Phase 2 formats (new)
    parser.add_argument('--deckbuilding-theory', type=int, default=0, help='Deckbuilding theory and card evaluation')
    parser.add_argument('--commander-building', type=int, default=0, help='Commander archetype construction')
    parser.add_argument('--rules-scenarios', type=int, default=0, help='Scenario-based rules reasoning questions')
    parser.add_argument('--archetypes', type=int, default=0, help='Deck archetype strategy questions')
    parser.add_argument('--game-theory', type=int, default=0, help='In-game decision making and sequencing')
    parser.add_argument('--meta-knowledge', type=int, default=0, help='cEDH, power levels, meta evaluation')

    # Rules-grounded formats (Phase 3)
    parser.add_argument('--rule-explanations', type=int, default=0, help='Q&A grounded in specific rule text')
    parser.add_argument('--rule-interactions', type=int, default=0, help='Scenarios where two rules interact')
    parser.add_argument('--glossary-examples', type=int, default=0, help='Glossary terms with in-game examples')
    parser.add_argument('--rule-edge-cases', type=int, default=0, help='Tricky edge case questions from complex rules')
    parser.add_argument('--rule-why', type=int, default=0, help='Backward-reasoning why-does-this-work questions')

    # EDHREC-grounded formats (Phase 4)
    parser.add_argument('--article-qa', type=int, default=0, help='Q&A synthesized from EDHREC articles')
    parser.add_argument('--guide-qa', type=int, default=0, help='Q&A synthesized from EDHREC guides')
    parser.add_argument('--staple-analysis', type=int, default=0, help='Why game-changer cards are Commander staples')
    parser.add_argument('--color-staples', type=int, default=0, help='Top cards by color in Commander')
    parser.add_argument('--salt-questions', type=int, default=0, help='Controversial/salty card analysis')

    # Preset modes
    parser.add_argument('--phase1', action='store_true', help='Generate all Phase 1 formats (15K total)')
    parser.add_argument('--phase2', action='store_true', help='Generate all Phase 2 formats (13K total) - strategy/theory focus')
    parser.add_argument('--phase3', action='store_true', help='Generate all Phase 3 formats (8K total) - rules-grounded')
    parser.add_argument('--phase4', action='store_true', help='Generate all Phase 4 formats (9K total) - EDHREC grounded')
    parser.add_argument('--all', action='store_true', help='Generate all formats (Phase 1 + Phase 2 + Phase 3 + Phase 4)')
    
    args = parser.parse_args()
    
    if args.model:
        global MODEL_NAME
        MODEL_NAME = args.model
        print(f"\n⚡ Using {MODEL_NAME} for text generation and validation")
    
    # Apply presets
    if args.phase1: #args.phase1:
        args.comparison = 2000
        args.reverse_lookup = 3000
        args.synergy = 3000
        args.budget = 2000
        args.color_identity = 2000
        args.guidelines = 2000
        args.terminology = 1000
        print("\n🔥 PHASE 1 MODE: Generating 15K high-value examples")

    if args.phase2:
        args.deckbuilding_theory = 2000
        args.commander_building = 3000
        args.rules_scenarios = 3000
        args.archetypes = 1500
        args.game_theory = 1500
        args.meta_knowledge = 1000
        print("\n🔥 PHASE 2 MODE: Generating 13K strategy/theory examples")

    if args.phase3:
        args.rule_explanations = 2000
        args.rule_interactions = 2000
        args.glossary_examples = 1500
        args.rule_edge_cases = 1500
        args.rule_why = 1000
        print("\n🔥 PHASE 3 MODE: Generating 8K rules-grounded examples")

    if args.phase4:
        args.article_qa = 2000
        args.guide_qa = 2000
        args.staple_analysis = 2000
        args.color_staples = 2000
        args.salt_questions = 1000
        print("\n🔥 PHASE 4 MODE: Generating 9K EDHREC-grounded examples")

    if args.all:
        args.combo_queries = 5000
        args.card_search = 3000
        args.commander = 200
        args.multi_card = 2000
        args.comparison = 2000
        args.reverse_lookup = 3000
        args.synergy = 4000
        args.budget = 2000
        args.color_identity = 2000
        args.guidelines = 3000
        args.terminology = 1000
        args.deckbuilding_theory = 2000
        args.commander_building = 3000
        args.rules_scenarios = 3000
        args.archetypes = 1500
        args.game_theory = 1500
        args.meta_knowledge = 1000
        args.rule_explanations = 2000
        args.rule_interactions = 2000
        args.glossary_examples = 1500
        args.rule_edge_cases = 1500
        args.rule_why = 1000
        args.article_qa = 2000
        args.guide_qa = 2000
        args.staple_analysis = 2000
        args.color_staples = 2000
        args.salt_questions = 1000
        print("\n🚀 ALL MODE: Generating 57K+ examples (Phase 1 + Phase 2 + Phase 3 + Phase 4)")
    
    print("="*80)
    print("SYNTHETIC QUERY GENERATION → MongoDB")
    print("="*80)
    
    # Connect to MongoDB
    print("\nConnecting to MongoDB...")
    cards, combos, synthetic, commanders, rules, glossary, articles, guides, game_changers, top_cards = get_mongo_collections(args.mongo_uri, args.mongo_user, args.mongo_pass)
    print("  ✓ Connected")
    
    # Generate all synthetic data
    all_documents = []
    
    # Original formats
    if args.combo_queries > 0:
        docs = generate_combo_queries(combos, args.combo_queries)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} combo query documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.card_search > 0:
        docs = generate_card_search_queries(cards, args.card_search)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} card search documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.commander > 0:
        docs = generate_commander_knowledge(args.commander)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} commander knowledge documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.multi_card > 0:
        docs = generate_multi_card_usage(combos, args.multi_card)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} multi-card usage documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.comparison > 0:
        docs = generate_comparison_questions(cards, args.comparison)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} comparison question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.reverse_lookup > 0:
        docs = generate_reverse_lookup_questions(cards, args.reverse_lookup)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} reverse lookup question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.synergy > 0:
        docs = generate_synergy_questions(cards, combos, args.synergy)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} synergy question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.budget > 0:
        docs = generate_budget_alternatives(cards, args.budget)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} budget alternative question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.color_identity > 0:
        docs = generate_color_identity_questions(cards, commanders, args.color_identity)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} color identity question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.guidelines > 0:
        docs = generate_quick_guidelines(args.guidelines)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} guideline question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.terminology > 0:
        docs = generate_terminology_questions(args.terminology)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} terminology question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format

    # Phase 2: Strategy/Theory formats
    if args.deckbuilding_theory > 0:
        docs = generate_deckbuilding_theory(args.deckbuilding_theory)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} deckbuilding theory documents")
        save_to_mongo(synthetic, docs)

    if args.commander_building > 0:
        docs = generate_commander_building(args.commander_building)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} commander building documents")
        save_to_mongo(synthetic, docs)

    if args.rules_scenarios > 0:
        docs = generate_rules_scenarios(args.rules_scenarios)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rules scenario documents")
        save_to_mongo(synthetic, docs)

    if args.archetypes > 0:
        docs = generate_archetypes(args.archetypes)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} archetype documents")
        save_to_mongo(synthetic, docs)

    if args.game_theory > 0:
        docs = generate_game_theory(args.game_theory)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} game theory documents")
        save_to_mongo(synthetic, docs)

    if args.meta_knowledge > 0:
        docs = generate_meta_knowledge(args.meta_knowledge)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} meta knowledge documents")
        save_to_mongo(synthetic, docs)

    # Phase 3: Rules-grounded formats
    if args.rule_explanations > 0:
        docs = generate_rule_explanations(rules, args.rule_explanations)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule explanation documents")
        save_to_mongo(synthetic, docs)

    if args.rule_interactions > 0:
        docs = generate_rule_interactions(rules, args.rule_interactions)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule interaction documents")
        save_to_mongo(synthetic, docs)

    if args.glossary_examples > 0:
        docs = generate_glossary_with_examples(glossary, args.glossary_examples)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} glossary with examples documents")
        save_to_mongo(synthetic, docs)

    if args.rule_edge_cases > 0:
        docs = generate_rule_edge_cases(rules, args.rule_edge_cases)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule edge case documents")
        save_to_mongo(synthetic, docs)

    if args.rule_why > 0:
        docs = generate_rule_why_questions(rules, args.rule_why)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} rule why question documents")
        save_to_mongo(synthetic, docs)

    # Phase 4: EDHREC-grounded formats
    if args.article_qa > 0:
        docs = generate_article_qa(articles, args.article_qa)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} article Q&A documents")
        save_to_mongo(synthetic, docs)

    if args.guide_qa > 0:
        docs = generate_guide_qa(guides, args.guide_qa)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} guide Q&A documents")
        save_to_mongo(synthetic, docs)

    if args.staple_analysis > 0:
        docs = generate_staple_analysis(game_changers, args.staple_analysis)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} staple analysis documents")
        save_to_mongo(synthetic, docs)

    if args.color_staples > 0:
        docs = generate_color_staples(top_cards, args.color_staples)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} color staple documents")
        save_to_mongo(synthetic, docs)

    if args.salt_questions > 0:
        docs = generate_salt_questions(game_changers, args.salt_questions)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} salt question documents")
        save_to_mongo(synthetic, docs)
    
    # Summary
    print("\n" + "="*80)
    print("✓ SAVED TO MongoDB: synthetic_queries.queries")
    print("="*80)
    print(f"Total documents: {len(all_documents):,}")
    print(f"\nBreakdown by category:")
    
    from collections import Counter
    categories = Counter(d['category'] for d in all_documents)
    for category, count in sorted(categories.items()):
        print(f"  {category:20s}: {count:,}")
    
    needs_review = sum(1 for d in all_documents if d.get('needs_review', False))
    print(f"\n⚠️  Needs manual review: {needs_review:,}")
    
    print(f"\n✅ Ready to extract!")
    print("="*80)


if __name__ == "__main__":
    main()