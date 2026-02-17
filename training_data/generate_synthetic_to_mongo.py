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
from datetime import datetime
import argparse
import time
import ollama

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
    
    return cards, combos, synthetic


def save_to_mongo(synthetic_collection, examples, batch_size=1000):
    """Save synthetic examples to MongoDB in batches"""
    print(f"\nSaving {len(examples):,} examples to MongoDB...")
    
    # Clear existing (optional - remove to keep appending)
    # synthetic_collection.delete_many({})
    
    for i in range(0, len(examples), batch_size):
        batch = examples[i:i+batch_size]
        
        # Add metadata
        for ex in batch:
            ex['generated_at'] = datetime.utcnow()
            ex['version'] = 1
        
        synthetic_collection.insert_many(batch)
        print(f"  → Saved {i+len(batch):,}/{len(examples):,}")
    
    print(f"  ✓ All examples saved to synthetic_queries.queries")


# =============================================================================
# MODEL QUERYING
# =============================================================================

def query_ollama(model_name: str, prompt: str, max_tokens=1000):
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
        
        print(response_content)
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
    card_colors = card.get('colorIdentity', card.get('colors', []))
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 2 color identity Q&A pairs.

Card: {card_name}
Color identity: {', '.join(card_colors) if card_colors else 'Colorless'}
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

Answers should explain color identity rules and give YES/NO.
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
        response =  query_ollama(MODEL_NAME, prompt, max_tokens=2000)
        response = response.replace("```json", "").replace("```", "").strip()
        qa_pairs = json.loads(response)
        
        for qa in qa_pairs:
            if 'question' in qa and 'answer' in qa:
                mongo_documents.append({
                    "question": qa['question'],
                    "answer": qa['answer'],
                    "category": "commander_rules",
                    "source_data": ["commander_format_rules"],
                    "validated": False,
                    "needs_review": True  # Manual verification needed!
                })
                print(f"    ✓ ACCEPTED: {qa['question'][:80]}")
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
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "multi_card_usage",
                        "source_data": card_names,
                        "validated": True,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED: {qa['question'][:80]}")

                    if len(mongo_documents) >= target_count:
                        break
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
            
            prompt = build_budget_alternative_prompt(exp_name, exp_card, budget_details)

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


def generate_color_identity_questions(cards_collection: Collection, target_count=2000) -> list[dict]:
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
    cards_sample = list(cards_collection.find(
        {'colors': {'$exists': True}},
        {'name': 1, 'colors': 1, 'colorIdentity': 1, 'manaCost': 1}
    ).limit(500))
    
    print(f"  → Processing {len(cards_sample)} cards...")
    
    # Common commander color identities
    commander_identities = [
        ('Atraxa', ['W', 'U', 'B', 'G']),
        ('Muldrotha', ['U', 'B', 'G']),
        ('Edgar Markov', ['W', 'B', 'R']),
        ('Chulane', ['W', 'U', 'G']),
        ('Korvold', ['B', 'R', 'G']),
        ('Kenrith', ['W', 'U', 'B', 'R', 'G']),
        ('Teysa', ['W', 'B']),
        ('Niv-Mizzet', ['U', 'R']),
        ('Golgari deck', ['B', 'G']),
        ('mono-red deck', ['R']),
    ]
    
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
        
        prompt = build_color_identity_prompt(card_name, card_colors, commander_name, commander_colors, is_legal)

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
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "guideline",
                        "source_data": ["deckbuilding_guidelines"],
                        "guideline_type": "deckbuilding",
                        "validated": False,
                        "needs_review": True  # Guidelines should be reviewed
                    })
                    print(f"    ✓ ACCEPTED: {qa['question'][:80]}")

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
    
    # Phase 1 formats (NEW!)
    parser.add_argument('--comparison', type=int, default=0, help='Card comparison questions')
    parser.add_argument('--reverse-lookup', type=int, default=0, help='Feature-to-card lookup')
    parser.add_argument('--synergy', type=int, default=0, help='Card synergy discovery')
    parser.add_argument('--budget', type=int, default=0, help='Budget alternatives')
    parser.add_argument('--color-identity', type=int, default=0, help='Color identity questions')
    parser.add_argument('--guidelines', type=int, default=0, help='Deckbuilding guidelines')
    parser.add_argument('--terminology', type=int, default=0, help='MTG terminology/slang')
    
    # Preset modes
    parser.add_argument('--phase1', action='store_true', help='Generate all Phase 1 formats (15K total)')
    parser.add_argument('--all', action='store_true', help='Generate all formats')
    
    args = parser.parse_args()
    
    if args.model:
        global MODEL_NAME
        MODEL_NAME = args.model
        print(f"\n⚡ Using {MODEL_NAME} for text generation and validation")
    
    # Apply presets
    if True: #args.phase1:
        args.comparison = 2000
        args.reverse_lookup = 3000
        args.synergy = 3000
        args.budget = 2000
        args.color_identity = 2000
        args.guidelines = 2000
        args.terminology = 1000
        print("\n🔥 PHASE 1 MODE: Generating 15K high-value examples")
    
    if args.all:
        args.combo_queries = 5000
        args.card_search = 3000
        args.commander = 200
        args.multi_card = 2000
        args.comparison = 2000
        args.reverse_lookup = 3000
        args.synergy = 3000
        args.budget = 2000
        args.color_identity = 2000
        args.guidelines = 2000
        args.terminology = 1000
        print("\n🚀 ALL MODE: Generating 25K+ examples")
    
    print("="*80)
    print("SYNTHETIC QUERY GENERATION → MongoDB")
    print("="*80)
    
    # Connect to MongoDB
    print("\nConnecting to MongoDB...")
    cards, combos, synthetic = get_mongo_collections(args.mongo_uri, args.mongo_user, args.mongo_pass)
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
        docs =generate_synergy_questions(cards, combos, args.synergy)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} synergy question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.budget > 0:
        docs = generate_budget_alternatives(cards, args.budget)
        all_documents.extend(docs)
        print(f"  ✓ Generated {len(docs):,} budget alternative question documents")
        save_to_mongo(synthetic, docs)  # Save incrementally after each format
    
    if args.color_identity > 0:
        docs = generate_color_identity_questions(cards, args.color_identity)
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