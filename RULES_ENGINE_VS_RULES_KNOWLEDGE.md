# Can Training on Rules Make Your Model a "Rules Engine"?

## TL;DR: No, but it's still extremely valuable

Your fine-tuned model will be a **rules encyclopedia**, not a **rules simulator**.

## What You WILL Get: Rules Expert

After training on the Comprehensive Rules, your model will:

### ✅ Excellent Rules Recall
```
User: "What happens when a creature with lifelink and deathtouch deals damage?"
Model: "According to the Comprehensive Rules [CR 702.15], lifelink causes you to 
gain life equal to the damage dealt. Deathtouch [CR 702.2] means any amount of 
damage is lethal. So you gain life and the creature dies."
```

### ✅ Keyword Explanations
```
User: "What is cumulative upkeep?"
Model: "[CR 702.24] Cumulative upkeep is an upkeep trigger that requires you to 
pay an increasing cost each turn. Put an age counter on the permanent, then 
sacrifice it unless you pay the cost for each age counter on it."
```

### ✅ Rules Citations
```
User: "When does the stack resolve?"
Model: "According to [CR 608], when a spell or ability on the stack resolves, 
players follow its instructions in order..."
```

### ✅ Pattern Recognition for Known Scenarios
```
User: "If I have Doubling Season and create a token, how many do I get?"
Model: "Based on replacement effects [CR 614], Doubling Season replaces 'create 
one token' with 'create two tokens'. So you'd create two tokens."
```

## What You WON'T Get: Rules Simulation Engine

### ❌ Cannot Execute Complex Game States
Your model CANNOT simulate this:

```
User: "I have 15 creatures with these specific abilities on the battlefield. 
I cast this spell. What happens?"

What you need: A rules engine that maintains game state
What your model does: Pattern matching against similar scenarios it's seen
```

The model doesn't maintain:
- Game state (life totals, board state, stack contents)
- Priority windows
- Layer interactions (continuous effects applying in order)
- State-based actions checking

### ❌ Cannot Discover Novel Combos Reliably

**Scenario 1: Known Pattern**
```
User: "Do Pestermite and Splinter Twin combo?"
Model: ✅ "Yes! This is a classic combo. Splinter Twin enchants Pestermite, 
tap to create a token copy with haste, the token enters and untaps the original 
Pestermite, repeat infinitely."

Why it works: The model has seen this exact combo or very similar "untap + copy" 
patterns dozens of times in training.
```

**Scenario 2: Novel Combination**
```
User: "Do [Brand New Card A] and [Obscure Card B] combo?"
Model: ❌ "I'm not familiar with that specific combination. Based on the card 
text, they might have synergy if [pattern], but I can't confirm this forms an 
infinite combo. Check Commander Spellbook to verify."

Why it fails: The model has never seen this combination. It can recognize 
SIMILAR patterns, but can't execute the rules step-by-step to prove it works.
```

## The Fundamental Problem: Pattern Matching vs. Logical Execution

### What Training Does
```python
# The model learns statistical associations
if "untap" in card_text and "tap for" in other_card:
    probably_infinite_combo()

if "enters the battlefield" in text and "bounce" in combo:
    recognize_etb_bounce_pattern()
```

### What a Rules Engine Does
```python
# A rules engine executes step-by-step
game_state = GameState()
game_state.add_permanent(hullbreaker_horror)
game_state.add_permanent(sol_ring)
game_state.add_permanent(ornithopter)

# Simulate
game_state.tap(sol_ring)  # Generate {C}{C}
game_state.cast(ornithopter, cost=0)  # Use {0}
game_state.trigger(hullbreaker_horror)  # Bounce permanent
game_state.choose_target(sol_ring)  # Target Sol Ring
game_state.resolve_bounce()  # Sol Ring to hand
game_state.cast(sol_ring, cost=1)  # Recast using {C}
game_state.trigger(hullbreaker_horror)  # Bounce permanent again
# ... loop detected! This is infinite!
```

Your model can't execute this simulation. It can only say "hmm, this LOOKS like 
combos I've seen before."

## Realistic Combo Discovery Capabilities

### High Confidence (Known Patterns)
✅ "Untap + tap ability" → Infinite activations
✅ "ETB bounce + 0-cost permanent" → Infinite ETBs
✅ "Draw on damage + damage on draw" → Infinite damage
✅ "Free sac + ETB death trigger" → Infinite loop
✅ "Storm + cost reduction to 0" → Infinite storm

Your model will recognize these because it's seen them 100+ times.

### Medium Confidence (Similar Patterns)
🟡 Novel cards with known patterns → "This might combo similar to X"
🟡 Keyword combinations → "These keywords often work together"
🟡 Mana loops → "This looks like it could generate mana"

The model will hedge: "Based on similar combos, this might work, but verify."

### Low Confidence (True Novel Combos)
❌ Complex multi-card interactions it's never seen
❌ Rules edge cases with weird timing
❌ Layer interactions determining if something works
❌ State-based actions breaking or enabling loops

The model should admit: "I don't know if this works. Test it or check Spellbook."

## What Makes This Still Incredibly Valuable

Even though it's not a rules engine, your model will be:

### 1. Best-in-Class Rules Reference
Faster than searching the 292-page PDF, better than asking Reddit

### 2. Combo Pattern Recognition Expert
"This looks like combo X" is hugely valuable for deck building

### 3. Strategic Rules Advisor
Knows which rules matter for different strategies

### 4. Honest About Limitations
Won't hallucinate that cards combo when they don't

## The Hybrid Approach (Most Realistic)

```python
# Combine LLM with simple checks
def does_combo(card_a, card_b):
    # Step 1: Check known combos database
    known = commander_spellbook.search(card_a, card_b)
    if known:
        return llm.explain(known)
    
    # Step 2: LLM pattern recognition
    patterns = llm.identify_combo_patterns(card_a, card_b)
    if patterns.confidence > 0.7:
        return llm.explain_with_hedging(patterns)
    
    # Step 3: Admit uncertainty
    return llm.admit_unknown_with_recommendation()
```

## Can We Do Better? (Future Directions)

### Option 1: Fine-tune on Chain-of-Thought
Train with explicit reasoning:

```json
{
  "messages": [
    {"role": "user", "content": "Do Hullbreaker Horror and Sol Ring combo?"},
    {"role": "assistant", "content": "Let me work through this step by step:
    
    1. Hullbreaker Horror: 'Whenever you cast a spell, return target nonland 
       permanent to its owner's hand.'
    2. Sol Ring costs {1} and produces {C}{C}
    3. We need a 0-cost permanent to bounce repeatedly
    
    With just these two: NO infinite combo
    
    With a 0-cost permanent (Ornithopter, Memnite, etc.):
    1. Tap Sol Ring for {C}{C}
    2. Cast 0-cost permanent using {0}
    3. Hullbreaker triggers, bounce Sol Ring
    4. Recast Sol Ring for {1}
    5. Hullbreaker triggers, bounce the 0-cost permanent
    6. Repeat infinitely
    
    Result: YES, this combos with a 0-cost permanent!"}
  ]
}
```

This teaches step-by-step reasoning but still isn't true simulation.

### Option 2: Rules Engine Integration (The Dream)
```python
# Use an actual MTG rules engine
from mtg_rules_engine import Game

def verify_combo(card_a, card_b):
    # Simulate in actual engine
    game = Game()
    result = game.test_infinite_loop([card_a, card_b])
    
    # Use LLM to explain what the engine found
    return llm.explain_simulation(result)
```

This would be THE solution, but requires a full MTG rules engine (which is hard).

### Option 3: Tool-Augmented LLM
Give your model tools to verify its guesses:

```python
tools = [
    "search_commander_spellbook(card_name)",
    "check_card_text(card_name)",
    "search_rules(keyword)",
    "find_similar_combos(pattern)",
]

# Model can call tools to verify before answering
```

## Bottom Line

Your trained model will be:
- ✅ Elite rules encyclopedia
- ✅ Pattern recognition for known combos
- ✅ Strategic advisor
- ✅ Honest about uncertainty
- ❌ Not a rules simulator
- ❌ Not reliably discovering novel combos

But that's still incredibly valuable! Most MTG questions are:
- "What does this card do?" → Model knows
- "How does [known combo] work?" → Model knows
- "What's the ruling on X?" → Model knows
- "Do these specific cards combo?" → Model recommends Spellbook

Think of it as training a **very knowledgeable judge**, not a **rules computer**.
