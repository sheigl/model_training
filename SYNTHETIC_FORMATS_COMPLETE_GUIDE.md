# Complete Synthetic Question Format Guide
## Implementation Priority & Feasibility Analysis

## 🔥 PHASE 1: MUST IMPLEMENT (Easy + High Impact)
**Target: 15K examples | Effort: Low | Impact: Huge**

### 1. Comparison Questions (2K examples)
```python
# Easy to generate from similar cards
"Which is better, Sol Ring or Mana Crypt?"
"Cultivate vs Kodama's Reach?"
"Should I run Lightning Bolt or Shock?"
```
**How:** Query cards with similar effects, Qwen compares
**Data needed:** Cards DB only
**Validation:** Check both cards exist

### 2. Reverse Lookup (3K examples)
```python
# Feature → Card search
"What card lets me play lands from graveyard?"
"What creature tutors for artifacts?"
"What destroys all enchantments?"
```
**How:** Query by text pattern, list results
**Data needed:** Cards DB only
**Validation:** Regex match on card text

### 3. Synergy Discovery (3K examples)
```python
# What works with X?
"What cards synergize with Sol Ring?"
"What goes well with treasure tokens?"
"What commander works with artifacts?"
```
**How:** Query cards by mechanic, Qwen suggests synergies
**Data needed:** Cards DB + Combos DB
**Validation:** Check if suggestions make sense mechanically

### 4. Budget Alternatives (2K examples)
```python
# Cheap replacement
"What's a budget alternative to Mana Crypt?"
"Cheap replacement for Cyclonic Rift?"
"Under $5 cards that ramp?"
```
**How:** Query similar effects, filter by rarity/popularity
**Data needed:** Cards DB (rarity as proxy for price)
**Validation:** Similar effect exists

### 5. Color Identity Queries (2K examples)
```python
# Commander restrictions
"Can I play Sol Ring in my Atraxa deck?"
"What's the color identity of Boros Charm?"
"Colorless cards for mono-red?"
```
**How:** Calculate color identity from mana cost + rules text
**Data needed:** Cards DB
**Validation:** Easy - rules-based

### 6. Quick Deckbuilding Guidelines (2K examples)
```python
# Rules of thumb
"How many lands in a 100-card deck?"
"How much ramp is enough?"
"How many board wipes should I run?"
```
**How:** Curate ~50 common guidelines, Qwen paraphrases
**Data needed:** None (general knowledge)
**Validation:** Manual review once

### 7. MTG Terminology/Slang (1K examples)
```python
# Onboarding
"What is CEDH?"
"What's a 'pillow fort'?"
"What does MLD stand for?"
```
**How:** Curate glossary, Qwen generates variations
**Data needed:** None (general knowledge)
**Validation:** Manual review once

---

## ⭐ PHASE 2: SHOULD IMPLEMENT (Medium Effort + Good Value)
**Target: 10K examples | Effort: Medium | Impact: High**

### 8. "I want to..." Goal-Oriented (2K examples)
```python
# Reverse engineering
"I want to win by turn 5, what do I need?"
"I want to protect my commander, what do I run?"
"I want infinite mana, what's easiest?"
```
**How:** Define common goals, query enablers, Qwen explains
**Data needed:** Cards DB + Combos DB
**Validation:** Goal-card alignment check

### 9. Win Condition Discovery (1K examples)
```python
# How do I actually win?
"What are my win conditions in Golgari?"
"How do I win with aristocrats?"
"What's my backup if combo fails?"
```
**How:** Query by archetype, list win conditions
**Data needed:** Cards DB + Combos DB + Articles DB
**Validation:** Win condition validity

### 10. Archetype Explanations (1K examples)
```python
# Strategy overviews
"How do I build a voltron deck?"
"What's an aristocrats strategy?"
"How does storm work?"
```
**How:** Pull from EDHRec articles, Qwen summarizes
**Data needed:** Articles DB
**Validation:** Archetype definition accuracy

### 11. Upgrade Paths (2K examples)
```python
# Progressive improvement
"How do I upgrade [precon]?"
"What's the next card after Sol Ring?"
"How do I make this deck competitive?"
```
**How:** Define upgrade tiers (budget → optimized), Qwen suggests
**Data needed:** Cards DB (by power level)
**Validation:** Upgrade makes sense

### 12. Card Evaluation (2K examples)
```python
# Is X good?
"Is Sol Ring worth it?"
"Why is Pitiless Plunderer good?"
"What makes Rhystic Study strong?"
```
**How:** Qwen analyzes card text + combo appearances
**Data needed:** Cards DB + Combos DB
**Validation:** Reasoning sounds correct

### 13. Pattern Recognition (2K examples)
```python
# Similar cards
"What cards work like Sol Ring?"
"Functional reprints of Cultivate?"
"What's the blue version of Lightning Bolt?"
```
**How:** Query by effect similarity
**Data needed:** Cards DB
**Validation:** Effects actually similar

---

## 💡 PHASE 3: NICE TO HAVE (Higher Effort / Lower Priority)
**Target: 5K examples | Effort: High | Impact: Medium**

### 14. Scenario-Based "I have X, what do?" (1K examples)
```python
# Contextual decisions
"I drew Sol Ring turn 1, when do I play it?"
"Opponent has Narset, how do I draw cards?"
"I have 10 life, opponent attacks for 12, what do I do?"
```
**How:** Generate common scenarios, Qwen advises
**Data needed:** Game state knowledge (hard!)
**Validation:** Strategic validity (requires expertise)

### 15. Threat Assessment (1K examples)
```python
# Multiplayer politics
"Who is the threat at this table?"
"Should I save removal or use it now?"
"When do I stop [player] from winning?"
```
**How:** Generate board states, Qwen evaluates
**Data needed:** Complex game state (very hard!)
**Validation:** Subjective, hard to validate

### 16. "Can I win from here?" Puzzles (1K examples)
```python
# Line finding
"I have [cards], can I win this turn?"
"Is there lethal with [board state]?"
"Can I combo off?"
```
**How:** Generate puzzle scenarios, Qwen solves
**Data needed:** Complex game logic
**Validation:** Puzzle solution correctness (hard!)

### 17. Stack Interactions (1K examples)
```python
# Advanced rules
"What resolves first, [A] or [B]?"
"Can I respond to [trigger]?"
"What's the correct stack order?"
```
**How:** Generate interaction scenarios, apply rules
**Data needed:** Comprehensive Rules + timing rules
**Validation:** Rules accuracy (critical!)

### 18. "What if..." Contingencies (1K examples)
```python
# Backup plans
"What if opponent counters my commander?"
"What if I don't draw lands?"
"What if my combo piece gets exiled?"
```
**How:** Generate failure scenarios, suggest alternatives
**Data needed:** Strategy knowledge
**Validation:** Advice quality

---

## 🚫 PHASE 4: SKIP FOR NOW (Too Hard / Low ROI)
**Not worth implementing yet**

### Political Questions
- Too subjective ("Should I make a deal?")
- No data source
- Hard to validate

### Historical Context
- Requires meta knowledge over time
- Not in our databases
- Low practical value

### Self-Assessment / Meta-Learning
- Requires expertise evaluation
- Can't generate from data
- Better suited for human mentorship

### Resource Recommendations
- Needs external content database
- Constantly changing
- Not in scope

---

## 📊 RECOMMENDED IMPLEMENTATION PLAN

### Total Synthetic Data: 30K examples

```
PHASE 1 (Easy wins):     15K examples (50%)
PHASE 2 (Good value):    10K examples (33%)
PHASE 3 (Nice to have):   5K examples (17%)

Total: 30K synthetic examples = 6% of 500K dataset
```

### Timeline Estimate:

```
Phase 1: 3-4 hours generation time
  - Mostly straightforward queries
  - High automation
  - Low manual review needed

Phase 2: 5-6 hours generation time
  - More complex prompts
  - Some manual curation
  - Medium review needed

Phase 3: 8-10 hours generation time
  - Complex scenarios
  - Significant manual work
  - High review needed

Total: 16-20 hours to generate 30K high-quality examples
```

---

## 🎯 RECOMMENDED STRATEGY

### Start Small, Iterate:

**Round 1: Core 10K (Phase 1 subset)**
```
1. Comparison Questions: 2K
2. Reverse Lookup: 3K
3. Synergy Discovery: 2K
4. Budget Alternatives: 2K
5. Color Identity: 1K
```
→ Train model → Test → Evaluate

**Round 2: Add 10K (Rest of Phase 1 + Phase 2 start)**
```
6. Quick Guidelines: 2K
7. Terminology: 1K
8. Goal-Oriented: 2K
9. Win Conditions: 1K
10. Card Evaluation: 2K
11. Pattern Recognition: 2K
```
→ Retrain → Test → Evaluate

**Round 3: Add 10K (Complete Phase 2 + Phase 3)**
```
12. Archetype Explanations: 1K
13. Upgrade Paths: 2K
14. Scenario-Based: 2K
15. Threat Assessment: 1K
16. Puzzles: 1K
17. Stack Interactions: 1K
18. Contingencies: 1K
19. Polish/Fix previous rounds: 1K
```
→ Final training → Ship!

---

## 💡 KEY INSIGHTS

### What Makes a Good Synthetic Question?

✅ **Generatable from data** (not opinion)
✅ **Validatable** (can check answer correctness)
✅ **High user value** (people actually ask this)
✅ **Scalable** (can generate 100s automatically)
✅ **Diverse** (many phrasings possible)

### What to Avoid?

❌ Requires game state (too complex)
❌ Subjective opinions (no ground truth)
❌ Time-sensitive (meta changes)
❌ External knowledge (not in our DB)
❌ Human judgment (politics, deals, threat assessment without context)

---

## 🔧 IMPLEMENTATION IN CODE

Add to `generate_synthetic_to_mongo.py`:

```python
# Phase 1 functions:
generate_comparison_questions()
generate_reverse_lookup()
generate_synergy_discovery()
generate_budget_alternatives()
generate_color_identity()
generate_quick_guidelines()
generate_terminology()

# Phase 2 functions:
generate_goal_oriented()
generate_win_conditions()
generate_archetypes()
generate_upgrade_paths()
generate_card_evaluation()
generate_pattern_recognition()

# Phase 3 functions:
generate_scenarios()
generate_threat_assessment()
generate_puzzles()
generate_stack_interactions()
generate_contingencies()
```

Each function:
1. Queries MongoDB for relevant data
2. Constructs prompt for Qwen 14B
3. Validates output against data
4. Saves to MongoDB collection

---

## 🎉 EXPECTED OUTCOME

### With 30K diverse synthetic examples:

**Before:** "What does Sol Ring do?" → Perfect ✅
**After:** All of these perfect too:
- "What combos use Sol Ring?" ✅
- "Sol Ring vs Mana Crypt?" ✅
- "What synergizes with Sol Ring?" ✅
- "Budget alternative to Mana Crypt?" ✅
- "Can I play Sol Ring in Atraxa?" ✅
- "I want infinite mana, how?" ✅
- "What ramps better than Sol Ring?" ✅
- "How do I win with artifacts?" ✅

**Transform from card database → true MTG assistant!** 🚀
