# Magic: The Gathering Training Data Guide

This guide shows you how to train a comprehensive MTG model that knows about cards, strategy, combos, deck building, and rules.

## 🎯 Three Types of MTG Knowledge

Your model can learn from three complementary data sources:

1. **Card Facts** - What cards do, their costs, types, legality
2. **Strategy & Synergies** - Deck building, commander recommendations  
3. **Expert Knowledge** - Combos, rules interactions, archetypes

Combining all three creates the most powerful MTG assistant!

## 🚀 Quick Start: Complete MTG Expert

### Option 1: Use Your Existing AllPrintings.json (Recommended)

```bash
# Step 1: Generate card facts (3000 examples, ~2 min)
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 3000 \
  --output mtg_cards.jsonl

# Step 2: Generate Commander strategy (400 examples, ~60 sec)
python convert_edhrec_data.py \
  --num-commanders 50 \
  --output edhrec_strategy.jsonl

# Step 3: Generate curated knowledge (40 examples, instant)
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl

# Step 4: Combine everything
cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > complete_mtg.jsonl

# Step 5: Train your comprehensive MTG expert!
python finetune_qwen.py \
  --dataset file \
  --data-file complete_mtg.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --batch-size 4 \
  --output-dir ./qwen-mtg-expert
```

**Total:** ~3,500 examples, ~45 minutes training  
**Result:** Model that knows cards + strategy + combos + rules!

### Option 2: Start Simple (Card Facts Only)

```bash
# Just card information to start
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 2000 \
  --output mtg_training.jsonl

# Train
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_training.jsonl \
  --epochs 4 \
  --output-dir ./qwen-mtg
```

**Total:** ~2,000 examples, ~20 minutes training  
**Result:** Model that knows card facts

## What the Conversion Scripts Do

You have **three scripts** that generate different types of MTG training data:

### 1. `convert_mtg_data.py` - Card Facts

Extracts information from MTGJSON (AtomicCards or AllPrintings):

**Generates questions about:**
- Card types and subtypes
- Mana costs and colors
- Creature stats (power/toughness)
- Card abilities and text
- Format legalities
- Basic strategy (when to cast, combat use)

**Example output:**
```json
{"messages": [
  {"role": "user", "content": "What does Lightning Bolt do?"},
  {"role": "assistant", "content": "Lightning Bolt: Lightning Bolt deals 3 damage to any target."}
]}
```

**Typical yield:** 1000-10000 examples depending on settings

---

### 2. `convert_edhrec_data.py` - Commander Strategy

Scrapes EDHREC's JSON endpoints for deck-building knowledge:

**Generates questions about:**
- Popular cards for specific commanders
- Card recommendations by category (creatures, instants, artifacts, etc.)
- Themes that work with commanders
- General Commander strategy (mana curves, removal ratios, card draw)
- Deck building principles (Rule of 8, mana base construction)

**Example output:**
```json
{"messages": [
  {"role": "user", "content": "What are good creatures for a Atraxa, Praetors' Voice deck?"},
  {"role": "assistant", "content": "Popular creatures in Atraxa decks include: Deepglow Skate, Evolution Sage, Tekuthal Inquiry Dominus. These cards synergize well with the commander's strategy."}
]}
```

**Typical yield:** 300-500 examples for 50 commanders (rate-limited, takes ~60 seconds)

---

### 3. `convert_curated_mtg.py` - Expert Knowledge

Manually curated high-quality MTG knowledge:

**Generates questions about:**
- Classic combos (Splinter Twin, Thassa's Oracle, Kiki-Jiki, etc.)
- Rules interactions (stack, priority, legend rule, indestructible)
- Format staples (best removal, counterspells, lands by format)
- Draft strategy (BREAD method, mana curves, creature counts)
- Deck archetypes (tempo, toolbox, aggro vs midrange vs control)

**Example output:**
```json
{"messages": [
  {"role": "user", "content": "What's the Splinter Twin combo?"},
  {"role": "assistant", "content": "Splinter Twin combo creates infinite creature tokens:\n1. Enchant Pestermite or Deceiver Exarch with Splinter Twin\n2. Tap the creature to create a hasty token copy\n3. The token's ETB trigger untaps the original\n4. Repeat infinitely\n5. Attack with infinite hasty tokens for lethal\n\nYou need the creature already in play before casting Twin, or have haste enabler. The combo wins the turn you assemble it."}
]}
```

**Typical yield:** 30-40 examples (easily expandable with your own knowledge!)

---

### AtomicCards vs AllPrintings (for convert_mtg_data.py)

**AtomicCards.json (~50MB)**
- Contains one entry per unique card
- Smaller file, faster to download and process
- Doesn't include set-specific information
- ✅ Best for: General card knowledge
- ⏱️ Download time: 2-3 minutes

**AllPrintings.json (~150MB)**
- Contains every printing of every card
- Includes set codes, collector numbers, specific printings
- More comprehensive data
- ✅ Best for: Complete card database, set information
- ⏱️ Download time: 5-10 minutes

**For training, both work equally well!** The script extracts unique cards from either format.

## Types of Questions Generated

### From Card Data (convert_mtg_data.py)

#### 1. Basic Information
```
Q: What type of card is Lightning Bolt?
A: Lightning Bolt is an Instant.

Q: What is the mana cost of Counterspell?
A: The mana cost of Counterspell is Blue Blue.

Q: What colors is Sol Ring?
A: Sol Ring is colorless.
```

#### 2. Card Abilities
```
Q: What does Birds of Paradise do?
A: Birds of Paradise: Flying. {T}: Add one mana of any color.

Q: What does Llanowar Elves do?
A: Llanowar Elves: {T}: Add {G}.
```

#### 3. Creature Stats
```
Q: What are the power and toughness of Tarmogoyf?
A: Tarmogoyf is a */*.

Q: What is the mana value of Mulldrifter?
A: Mulldrifter has a mana value of 5.
```

#### 4. Subtypes and Tribes
```
Q: What creature type is Snapcaster Mage?
A: Snapcaster Mage is a Human Wizard.

Q: What are the subtypes of Arid Mesa?
A: The subtypes of Arid Mesa are: Plains, Mountain.
```

#### 5. Format Legality
```
Q: Is Black Lotus legal in Commander?
A: No, Black Lotus is banned in Commander.

Q: Is Lightning Bolt legal in Modern?
A: Yes, Lightning Bolt is legal in Modern.
```

#### 6. Strategy Questions
```
Q: How can I use Delver of Secrets in combat?
A: Delver of Secrets is a 1/1 creature. At the beginning of your upkeep, look at the top card of your library. You may reveal that card. If an instant or sorcery card is revealed this way, transform Delver of Secrets. Consider its power and toughness when deciding whether to attack or block.

Q: When can I cast Path to Exile?
A: Path to Exile is an instant. You can cast it at any time you have priority, including during combat or on your opponent's turn.
```

---

### From EDHREC Data (convert_edhrec_data.py)

#### 7. Commander-Specific Recommendations
```
Q: What are good creatures for a Atraxa, Praetors' Voice deck?
A: Popular creatures in Atraxa decks include: Deepglow Skate, Evolution Sage, Tekuthal Inquiry Dominus. These cards synergize well with the commander's strategy.

Q: What artifacts should I run in Urza, Lord High Artificer?
A: Key artifacts for Urza include: Sol Ring, Mana Vault, Grim Monolith. These provide ramp and utility.

Q: What themes work well with Krark, the Thumbless?
A: Krark synergizes with these themes: Spellslinger, Storm, Copy effects. Build around these strategies for best results.
```

#### 8. General Commander Strategy
```
Q: How many lands should I run in a Commander deck?
A: Most Commander decks run 36-38 lands. Use 36 lands if you have 10+ ramp sources (mana rocks/dorks), 37-38 as a baseline, and 38-40 if your curve is high or you lack ramp. Adjust based on your deck's mana curve and strategy.

Q: What's the rule of 8 in Commander deck building?
A: The Rule of 8: For each effect you want in your deck, include 8 cards that provide it. For example, 8 ramp sources, 8 card draw effects, 8 removal spells. This increases consistency while still allowing for 99 unique cards. It's a guideline, not a strict rule.

Q: How much removal should I include in Commander?
A: Include 8-12 removal spells in Commander. This should be a mix of: single-target removal (4-6 cards like Path to Exile, Beast Within), board wipes (2-4 cards like Wrath of God), and flexible answers (2-3 cards like Generous Gift). More removal for competitive metas, less for casual.
```

---

### From Curated Knowledge (convert_curated_mtg.py)

#### 9. Famous Combos
```
Q: What's the Splinter Twin combo?
A: Splinter Twin combo creates infinite creature tokens:
1. Enchant Pestermite or Deceiver Exarch with Splinter Twin
2. Tap the creature to create a hasty token copy
3. The token's ETB trigger untaps the original
4. Repeat infinitely
5. Attack with infinite hasty tokens for lethal

You need the creature already in play before casting Twin, or have haste enabler. The combo wins the turn you assemble it.

Q: How does Heliod + Walking Ballista combo work?
A: Heliod, Sun-Crowned + Walking Ballista creates infinite damage:
1. Have Heliod in play
2. Cast Walking Ballista with X≥1
3. Ballista deals 1 damage (remove counter)
4. Heliod's ability triggers, put a +1/+1 counter on Ballista
5. Repeat infinitely to kill all opponents

Requires 4 mana (3 for Heliod + 1 for Ballista). Works at instant speed.
```

#### 10. Rules Interactions
```
Q: How does the stack work in Magic?
A: The stack is a zone where spells and abilities wait to resolve. It follows Last In, First Out (LIFO):

1. When you cast a spell or activate an ability, it goes on the stack
2. Players can respond by adding more items
3. When all players pass priority, the top item resolves
4. Players can respond again before the next item resolves

Example: You cast Lightning Bolt. Opponent casts Counterspell. Counterspell resolves first (being on top), countering the Bolt.

Q: Can I respond to someone playing a land?
A: NO - You cannot respond to playing a land:

Playing a land:
- Is a special action, not a spell
- Doesn't use the stack
- Can't be countered or responded to
- Limited to once per turn
- Only during main phase when stack is empty

However, you CAN respond to:
- Triggered abilities when land enters (fetchland crack, Valakut trigger)
- Abilities lands have after entering
```

#### 11. Format Staples
```
Q: What are the best removal spells in Modern?
A: Top Modern removal by color:

White:
- Path to Exile (1 mana, exile creature)
- Prismatic Ending (flexible permanent removal)

Black:
- Fatal Push (1 mana, kills 2 or 4 CMC)
- Thoughtseize (hand disruption)
- Terminate (unconditional creature kill)

Red:
- Lightning Bolt (3 damage anywhere)
- Unholy Heat (with delirium, kills anything)

Blue:
- Counterspell (2 mana hard counter)
- Archmage's Charm (versatile)

Green:
- Force of Vigor (free artifact/enchantment removal)
```

#### 12. Deck Archetypes
```
Q: What's a tempo deck in Magic?
A: Tempo decks aim to get ahead early and stay ahead:

**Strategy:**
1. Deploy cheap, efficient threats (Delver, Ragavan)
2. Protect them with cheap interaction (Spell Pierce, Daze)
3. Disrupt opponent's gameplan
4. Win before they stabilize

**Key Elements:**
- Efficient threats (1-2 mana)
- Cheap interaction (0-2 mana counters/removal)
- Card selection (Brainstorm, Ponder)
- Tempo plays (bounce spells like Vapor Snag)

**Examples:**
- UR Delver (Legacy)
- Mono-Blue Tempo (Standard)
- Izzet Phoenix (Modern)

**Weakness:**
Runs out of steam if game goes long. Needs to close quickly.
```

#### 13. Draft Strategy
```
Q: What's the BREAD method for drafting?
A: BREAD is a draft pick priority system:

**B - Bombs:**
Game-winning cards (planeswalkers, big evasive creatures, removal on a stick)
Pick: 1st-2nd

**R - Removal:**
Kill spells to answer opponent's threats
Pick: 2nd-3rd

**E - Evasion:**
Creatures that are hard to block (flying, menace, unblockable)
Pick: 3rd-4th

**A - Aggro:**
Efficient creatures that fill your curve (2-3 drops)
Pick: 4th

**D - Duds:**
Cards you don't want
Pick: Never

Modern variation: CABS (Cards that Affect Board State) focuses on board impact over curve.
```

## Command-Line Options for All Scripts

### `convert_mtg_data.py` - Card Facts

```bash
# Use your existing AllPrintings.json
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 2000

# Download fresh AtomicCards.json
python convert_mtg_data.py --download --file-type atomic --num-examples 2000

# Download fresh AllPrintings.json
python convert_mtg_data.py --download --file-type allprintings --num-examples 2000

# Auto-detect existing file (looks for AllPrintings.json or AtomicCards.json)
python convert_mtg_data.py --num-examples 2000

# Specify custom output file
python convert_mtg_data.py --data-file AllPrintings.json --output my_mtg_data.jsonl --num-examples 3000
```

**Options:**

- **`--data-file PATH`**: Path to your existing MTGJSON file
  - Use this if you already have AllPrintings.json or AtomicCards.json
  - If omitted, script auto-detects files in current directory

- **`--download`**: Download fresh data from MTGJSON
  - Use this to get the latest card data
  - Requires `--file-type` to specify which file to download

- **`--file-type {atomic,allprintings}`**: Which file to download (requires `--download`)
  - **`atomic`**: Downloads AtomicCards.json (~50MB, 2-3 min) - smaller, one entry per card
  - **`allprintings`**: Downloads AllPrintings.json (~150MB, 5-10 min) - all printings

- **`--num-examples N`**: How many Q&A pairs to generate
  - **500**: Quick test (covers ~100 cards)
  - **1000**: Good starting point (covers ~200 cards)
  - **2000**: Better coverage (covers ~400 cards) - **RECOMMENDED**
  - **5000**: Comprehensive (covers ~1000 cards)
  - **10000+**: Maximum coverage

- **`--output FILE`**: Where to save the training data (default: `mtg_training.jsonl`)

---

### `convert_edhrec_data.py` - Commander Strategy

```bash
# Generate EDHREC data for 50 commanders (recommended)
python convert_edhrec_data.py --num-commanders 50 --output edhrec_strategy.jsonl

# Generate for more commanders (takes longer)
python convert_edhrec_data.py --num-commanders 100 --output edhrec_large.jsonl

# Skip general strategy questions (commander-specific only)
python convert_edhrec_data.py --num-commanders 50 --no-include-general
```

**Options:**

- **`--output FILE`**: Where to save the training data (default: `edhrec_training.jsonl`)

- **`--num-commanders N`**: Number of commanders to fetch data for
  - **50**: Good balance (~300-500 examples, ~60 seconds)
  - **100**: More coverage (~600-1000 examples, ~2 minutes)
  - **200**: Comprehensive (~1200-2000 examples, ~4 minutes)
  - Note: Rate-limited to be respectful to EDHREC servers

- **`--include-general`**: Include general Commander strategy questions (default: True)
  - Adds questions about mana curves, removal ratios, card draw, etc.
  - Disable with `--no-include-general` if you only want commander-specific data

**Important:** This script is rate-limited and will take time. ~1 second per commander + general questions.

---

### `convert_curated_mtg.py` - Expert Knowledge

```bash
# Generate all curated knowledge
python convert_curated_mtg.py --output curated_knowledge.jsonl
```

**Options:**

- **`--output FILE`**: Where to save the training data (default: `curated_mtg.jsonl`)

**What's included:**
- Classic combos (7 examples)
- Rules interactions (8 examples)
- Format staples (3 examples)
- Draft strategy (3 examples)
- Deck archetypes (3 examples)

**Total:** ~30-40 examples

**Easy to expand!** Just edit the script and add your own questions.

## Training Recommendations

### Recommended: Complete MTG Expert (All Three Sources)

```bash
# 1. Generate card facts (3000 examples)
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 3000 \
  --output mtg_cards.jsonl

# 2. Generate EDHREC strategy (400 examples, ~60 sec)
python convert_edhrec_data.py \
  --num-commanders 50 \
  --output edhrec_strategy.jsonl

# 3. Generate curated knowledge (40 examples)
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl

# 4. Combine everything
cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > complete_mtg.jsonl

# 5. Train comprehensive model
python finetune_qwen.py \
  --dataset file \
  --data-file complete_mtg.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --lora-alpha 64 \
  --batch-size 4 \
  --output-dir ./qwen-mtg-expert
```

**Time:** ~45 minutes total (5 min data generation + 40 min training)  
**Examples:** ~3,500 total  
**Covers:**  
✅ Card knowledge (names, costs, abilities, legalities)  
✅ Commander strategy (synergies, recommendations)  
✅ Combos (how they work)  
✅ Rules (stack, priority, interactions)  
✅ Archetypes (tempo, control, aggro)  
✅ Draft advice (BREAD, mana curves)  

---

### For Casual Commander Focus

```bash
# 1. Focus on Commander-relevant cards
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 2000 \
  --output mtg_cards.jsonl

# 2. Extensive EDHREC data
python convert_edhrec_data.py \
  --num-commanders 100 \
  --output edhrec_strategy.jsonl

# 3. Curated knowledge (includes Commander strategy)
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl

# 4. Combine and train
cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > commander_expert.jsonl

python finetune_qwen.py \
  --dataset file \
  --data-file commander_expert.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --output-dir ./qwen-commander
```

**Time:** ~60 minutes  
**Examples:** ~3,000-4,000  
**Best for:** Commander deck building, casual play

---

### For Competitive/cEDH Knowledge

```bash
# 1. Comprehensive card data
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 5000 \
  --output mtg_cards.jsonl

# 2. Top competitive commanders
python convert_edhrec_data.py \
  --num-commanders 100 \
  --output edhrec_strategy.jsonl

# 3. Curated knowledge (expand with cEDH combos!)
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl

# 4. Combine and train with larger LoRA
cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > cedh_expert.jsonl

python finetune_qwen.py \
  --dataset file \
  --data-file cedh_expert.jsonl \
  --epochs 3 \
  --lora-r 48 \
  --lora-alpha 96 \
  --batch-size 4 \
  --output-dir ./qwen-cedh
```

**Time:** ~90 minutes  
**Examples:** ~6,000-7,000  
**Best for:** Competitive Commander, fast combos, optimization

**Pro Tip:** Edit `convert_curated_mtg.py` to add cEDH-specific combos like:
- Thassa's Oracle + Consultation
- Food Chain combos
- Underworld Breach lines
- Ad Nauseam strategies

---

### Card Knowledge Only (Simplest)

```bash
# Just card facts
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 2000 \
  --output mtg_simple.jsonl

# Train
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_simple.jsonl \
  --epochs 4 \
  --lora-r 16 \
  --output-dir ./qwen-mtg-cards
```

**Time:** ~20 minutes  
**Examples:** ~2,000  
**Best for:** Testing, basic card lookup  
**Limitation:** No strategy, combos, or deck building advice

---

### Maximum Coverage (Everything!)

```bash
# 1. Maximum card data
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 10000 \
  --output mtg_cards_max.jsonl

# 2. Many commanders
python convert_edhrec_data.py \
  --num-commanders 200 \
  --output edhrec_large.jsonl

# 3. Curated knowledge
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl

# 4. Combine (large file!)
cat mtg_cards_max.jsonl edhrec_large.jsonl curated_knowledge.jsonl > mtg_ultimate.jsonl

# 5. Train with adjusted settings
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_ultimate.jsonl \
  --epochs 2 \
  --lora-r 48 \
  --lora-alpha 96 \
  --batch-size 4 \
  --gradient-accumulation 4 \
  --output-dir ./qwen-mtg-ultimate
```

**Time:** ~3-4 hours (data gen + training)  
**Examples:** ~12,000-15,000  
**Best for:** Comprehensive MTG encyclopedia  
**Note:** Requires ~8-10GB VRAM, reduce batch size if OOM

## Data Quality Tips

### More Examples = Better Coverage
- 1000 examples covers ~200 unique cards
- 5000 examples covers ~1000 unique cards
- 10000 examples covers ~2000 unique cards
- More examples means more cards the model knows about

### What the Model Will Learn
✅ **Card names and types**  
✅ **Mana costs and colors**  
✅ **Creature stats (P/T)**  
✅ **Card text and abilities**  
✅ **Format legalities**  
✅ **Basic strategy**  

❌ **Will NOT learn:**
- Current metagame
- Prices
- Card availability
- Combo interactions (unless you add specific examples)
- Rules edge cases

## Customizing Your Training Data

All three scripts are designed to be easily expandable with your own knowledge!

### Easiest: Expand Curated Knowledge

The `convert_curated_mtg.py` script is the simplest to customize. Just add more functions!

#### Adding Your Own Combos

```python
def get_combo_questions():
    """Well-known MTG combos"""
    return [
        # ... existing combos ...
        
        # Add your own!
        {
            "user": "How does Protean Hulk combo work?",
            "assistant": "Protean Hulk dies and searches for creatures totaling 6 CMC or less. Common lines:\n\n1. Get Viscera Seer + Karmic Guide\n2. Karmic Guide returns Hulk\n3. Sacrifice Hulk again\n4. Get more combo pieces\n5. Assemble your win condition\n\nPopular targets: Mikaeus + Walking Ballista, or various 2-card combos."
        },
        {
            "user": "What's the Food Chain combo?",
            "assistant": "Food Chain + Eternal Scourge/Misthollow Griffin creates infinite mana:\n1. Cast Food Chain\n2. Cast creature from exile (Eternal Scourge)\n3. Exile it to Food Chain for mana\n4. Cast it again from exile\n5. Repeat for infinite colored mana\n\nUse with Prossh or other outlets to win."
        },
    ]
```

#### Adding Your Local Meta Knowledge

```python
def get_local_meta_questions():
    """Add knowledge about your playgroup"""
    return [
        {
            "user": "What's strong in my local Commander meta?",
            "assistant": "Your meta features:\n- Heavy graveyard strategies (bring Rest in Peace)\n- Lots of tribal decks (board wipes are key)\n- Combo-light, more value-focused\n- Power level 7-8\n\nBest answers: Beast Within, Generous Gift, Cyclonic Rift, counterspells"
        },
        {
            "user": "What beats my friend's Ur-Dragon deck?",
            "assistant": "Against Ur-Dragon:\n- Early pressure (they're slow to set up)\n- Graveyard hate for Scion reanimation\n- Counterspells for big dragons\n- Targeted removal for Ur-Dragon itself\n- Board wipes (Wrath of God, Damnation)\n- Faster combo (race them)"
        },
    ]
```

Then add it to main():
```python
def main():
    # ... existing code ...
    
    print("Adding local meta questions...")
    all_questions.extend(get_local_meta_questions())
    
    # ... rest of code ...
```

#### Adding Format-Specific Knowledge

```python
def get_pioneer_questions():
    """Pioneer format knowledge"""
    return [
        {
            "user": "What are the best decks in Pioneer?",
            "assistant": "Top Pioneer decks:\n1. Rakdos Midrange - Efficient removal + Fable\n2. Mono-Green Devotion - Ramp into Karn\n3. Izzet Phoenix - Recursive threats\n4. Lotus Field Combo - Thespian's Stage combo\n5. Azorius Control - Supreme Verdict + counters"
        },
    ]
```

#### Adding Your Deck Tech

```python
def get_my_decks():
    """Your personal deck knowledge"""
    return [
        {
            "user": "How should I play my Meren deck?",
            "assistant": "Your Meren strategy:\n1. Early: Ramp and fill graveyard (Sakura-Tribe Elder, Viscera Seer)\n2. Mid: Start recurring value creatures (Eternal Witness, Spore Frog)\n3. Late: Lock out with Fleshbag Marauder loops\n\nKey cards: Buried Alive, Living Death, Mikaeus\nWin cons: Mike+Trike combo, Kokusho loops"
        },
    ]
```

---

### Moderate: Expand Card Data

You can modify `convert_mtg_data.py` to generate additional question types:

```python
def generate_color_identity_questions(card_name, card):
    """Generate questions about color identity for Commander"""
    questions = []
    
    # For legendary creatures
    if 'Legendary' in card.get('supertypes', []) and 'Creature' in card.get('types', []):
        colors = get_card_colors(card)
        questions.append({
            "user": f"What color identity is {card_name} for Commander?",
            "assistant": f"{card_name} has a {colors} color identity, so you can only use {colors} cards in the deck."
        })
    
    return questions
```

Then add to `generate_training_data()`:
```python
questions.extend(generate_color_identity_questions(card_name, card))
```

---

### Advanced: Expand EDHREC Data

You can modify `convert_edhrec_data.py` to fetch additional data:

```python
def get_theme_page(theme_name):
    """Get data for a specific theme"""
    url = f"{EDHREC_BASE}/pages/themes/{theme_name}.json"
    return fetch_json(url)

def generate_theme_questions():
    """Generate questions about themes"""
    themes = ['aristocrats', 'tokens', 'voltron', 'landfall']
    questions = []
    
    for theme in themes:
        theme_data = get_theme_page(theme)
        # Process theme data...
        questions.append({
            "user": f"What are the best cards for a {theme} strategy?",
            "assistant": f"Top {theme} cards include: ..."
        })
    
    return questions
```

## Testing Your Trained Model

After training, test it:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

# Load model
base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-0.5B-Instruct",
    device_map="auto",
    torch_dtype=torch.bfloat16
)
model = PeftModel.from_pretrained(base_model, "./qwen-mtg")
tokenizer = AutoTokenizer.from_pretrained("./qwen-mtg")

# Test questions
questions = [
    "What type of card is Lightning Bolt?",
    "What does Counterspell do?",
    "Is Sol Ring legal in Commander?",
    "What are the colors of Tarmogoyf?",
]

for question in questions:
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to("xpu")
    
    outputs = model.generate(**inputs, max_new_tokens=100)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    print(f"Q: {question}")
    print(f"A: {response}\n")
```

## Troubleshooting

### "Download taking forever"
- The AtomicCards.json file is ~50MB
- Should take 2-5 minutes depending on internet speed
- If it fails, try again or download manually from: https://mtgjson.com/api/v5/AtomicCards.json

### "Not generating enough questions"
- Some cards have limited information
- Increase `--num-examples` to cover more cards
- The script will generate as many questions as possible per card

### "Model doesn't know about specific cards"
- The training data only includes cards in your dataset
- Generate more examples: `--num-examples 10000`
- Or add specific cards you care about

### "Model gives wrong information"
- More training examples usually helps
- Try training for more epochs: `--epochs 5`
- Increase LoRA rank: `--lora-r 32`

## Advanced: Combining with Other Data

You can combine MTG data with other instruction data:

```bash
# Generate MTG data
python convert_mtg_data.py --num-examples 2000 --output mtg.jsonl

# Combine with general instructions
cat mtg.jsonl > combined.jsonl
cat other_instructions.jsonl >> combined.jsonl

# Train on combined data
python finetune_qwen.py --dataset file --data-file combined.jsonl
```

This gives you a model that knows MTG AND can follow general instructions!

## Data Storage

The downloaded files:
- `AtomicCards.json`: ~50MB (can delete after generating training data)
- `mtg_training.jsonl`: ~100KB-1MB depending on num-examples
- Trained model: ~50MB (LoRA adapter only)

## Complete Example Workflow

### Step-by-Step: Build a Comprehensive MTG Expert

```bash
# ============================================
# STEP 1: Generate All Training Data (~5 min)
# ============================================

# 1a. Card facts (uses your existing AllPrintings.json)
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 3000 \
  --output mtg_cards.jsonl

# Output: ~3000 examples about card names, costs, abilities, legalities

# 1b. Commander strategy (rate-limited, ~60 sec)
python convert_edhrec_data.py \
  --num-commanders 50 \
  --output edhrec_strategy.jsonl

# Output: ~400 examples about deck building, synergies, Commander advice

# 1c. Curated expert knowledge (instant)
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl

# Output: ~40 examples of combos, rules, archetypes, format staples

# ============================================
# STEP 2: Combine All Data
# ============================================

cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > complete_mtg.jsonl

# Verify total count
wc -l complete_mtg.jsonl
# Should show ~3,440 lines (examples)

# ============================================
# STEP 3: Train the Model (~40 min)
# ============================================

python finetune_qwen.py \
  --dataset file \
  --data-file complete_mtg.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --lora-alpha 64 \
  --batch-size 4 \
  --output-dir ./qwen-mtg-expert

# Training progress will show:
# - Epoch 1/3
# - Epoch 2/3
# - Epoch 3/3
# - Saving model...

# ============================================
# STEP 4: Test Your Model
# ============================================

# Create a test script (test_mtg_model.py):
```

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

# Load model
print("Loading model...")
base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-0.5B-Instruct",
    device_map="auto",
    torch_dtype=torch.bfloat16
)
model = PeftModel.from_pretrained(base_model, "./qwen-mtg-expert")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")

def ask_question(question):
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    outputs = model.generate(
        **inputs,
        max_new_tokens=256,
        temperature=0.7,
        do_sample=True
    )
    
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    return response

# Test different question types
print("\n" + "="*70)
print("TESTING MTG EXPERT MODEL")
print("="*70 + "\n")

questions = [
    # Card knowledge
    "What does Lightning Bolt do?",
    "Is Sol Ring legal in Commander?",
    "What are the colors of Atraxa, Praetors' Voice?",
    
    # Strategy
    "How many lands should I run in Commander?",
    "What are good creatures for a token strategy?",
    
    # Combos
    "What's the Splinter Twin combo?",
    "How does Thassa's Oracle win?",
    
    # Rules
    "How does the stack work?",
    "Can I respond to playing a land?",
    
    # Format advice
    "What are the best removal spells in Modern?",
]

for q in questions:
    print(f"Q: {q}")
    print(f"A: {ask_question(q)}\n")
    print("-" * 70 + "\n")
```

```bash
# Run the test
python test_mtg_model.py

# ============================================
# STEP 5: Iterate and Improve
# ============================================

# If you want more coverage, regenerate with more examples:

python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 5000 \
  --output mtg_cards_large.jsonl

python convert_edhrec_data.py \
  --num-commanders 100 \
  --output edhrec_large.jsonl

# Add your own knowledge to convert_curated_mtg.py
# Then regenerate:
python convert_curated_mtg.py --output curated_knowledge_v2.jsonl

# Combine and retrain
cat mtg_cards_large.jsonl edhrec_large.jsonl curated_knowledge_v2.jsonl > complete_mtg_v2.jsonl

python finetune_qwen.py \
  --dataset file \
  --data-file complete_mtg_v2.jsonl \
  --epochs 3 \
  --lora-r 48 \
  --output-dir ./qwen-mtg-expert-v2
```

---

### Quick Test Workflow (10 minutes)

```bash
# 1. Generate small test dataset
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 500 --output test.jsonl

# 2. Train quickly
python finetune_qwen.py --dataset file --data-file test.jsonl --epochs 2 --output-dir ./qwen-test

# 3. Ask it questions
# (Use test script above)
```

---

### Production Workflow (3-4 hours)

```bash
# 1. Maximum card coverage
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 10000 \
  --output mtg_max.jsonl

# 2. Extensive EDHREC data
python convert_edhrec_data.py \
  --num-commanders 200 \
  --output edhrec_max.jsonl

# 3. Curated knowledge (consider expanding first!)
python convert_curated_mtg.py \
  --output curated_max.jsonl

# 4. Combine
cat mtg_max.jsonl edhrec_max.jsonl curated_max.jsonl > ultimate_mtg.jsonl

# 5. Train with optimal settings
python finetune_qwen.py \
  --dataset file \
  --data-file ultimate_mtg.jsonl \
  --epochs 2 \
  --lora-r 48 \
  --lora-alpha 96 \
  --batch-size 4 \
  --gradient-accumulation 4 \
  --output-dir ./qwen-mtg-ultimate
```

## Questions You Can Ask the Trained Model

After training on all three data sources, you can ask:

### Card Knowledge Questions
- "What does [card name] do?"
- "What type of card is [card name]?"
- "What's the mana cost of [card name]?"
- "What colors is [card name]?"
- "Is [card name] legal in [format]?"
- "What are the power and toughness of [creature]?"
- "What creature types does [creature] have?"

### Deck Building Questions
- "What are good cards for a [commander] deck?"
- "What creatures should I include in [commander]?"
- "What artifacts work well with [commander]?"
- "What themes work with [commander]?"
- "How many lands should I run in Commander?"
- "What's a good mana curve for [deck type]?"
- "How much removal should I include?"
- "What's the rule of 8 in Commander?"

### Combo Questions
- "What's the [combo name] combo?"
- "How does [card] combo work?"
- "What combos with [card name]?"
- "How do I win with [card]?"
- "What's an infinite mana combo?"
- "What are the best combos in [format]?"

### Rules Questions
- "How does the stack work?"
- "Can I respond to [action]?"
- "What happens when [situation]?"
- "How does [keyword] work?"
- "What's the legend rule?"
- "Can you counterspell [thing]?"
- "What's the difference between destroy and sacrifice?"

### Strategy Questions  
- "When can I cast [card name]?"
- "How can I use [card] in combat?"
- "How do I beat [deck archetype]?"
- "What's a tempo deck?"
- "What's the difference between aggro and midrange?"
- "How should I sideboard against [deck type]?"

### Format Questions
- "What are the best removal spells in [format]?"
- "What are the best counterspells in Legacy?"
- "What lands should every Commander deck run?"
- "What makes a card good in Commander vs Standard?"
- "What are the top decks in [format]?"

### Draft Questions
- "What's the BREAD method?"
- "How many creatures should I draft?"
- "What's a good mana curve for Limited?"
- "Should I pick [card A] or [card B]?"

The more examples you generate (especially from EDHREC and curated), the better the model gets at these questions!

## Next Steps

### 1. **Start with the Recommended Approach**
   ```bash
   # Generate all three data sources
   python convert_mtg_data.py --data-file AllPrintings.json --num-examples 3000 --output cards.jsonl
   python convert_edhrec_data.py --num-commanders 50 --output strategy.jsonl
   python convert_curated_mtg.py --output knowledge.jsonl
   
   # Combine them
   cat cards.jsonl strategy.jsonl knowledge.jsonl > complete.jsonl
   
   # Train
   python finetune_qwen.py --dataset file --data-file complete.jsonl --epochs 3 --lora-r 32 --output-dir ./qwen-mtg
   ```

### 2. **Test Your Model**
   Use the test script from the Example Workflow section to ask questions

### 3. **Evaluate What's Missing**
   - Does it know enough cards? → Increase `--num-examples` in convert_mtg_data.py
   - Need more strategy? → Increase `--num-commanders` in convert_edhrec_data.py  
   - Want specific combos? → Add them to convert_curated_mtg.py

### 4. **Add Your Own Knowledge**
   Edit `convert_curated_mtg.py` to add:
   - Your favorite combos
   - Your local meta knowledge
   - Your deck strategies
   - Format-specific advice you know

### 5. **Retrain with Expanded Data**
   ```bash
   # Regenerate curated knowledge with your additions
   python convert_curated_mtg.py --output knowledge_v2.jsonl
   
   # Combine and retrain
   cat cards.jsonl strategy.jsonl knowledge_v2.jsonl > complete_v2.jsonl
   python finetune_qwen.py --dataset file --data-file complete_v2.jsonl --epochs 3 --output-dir ./qwen-mtg-v2
   ```

### 6. **Share Your Knowledge**
   Once you have a great model, you could:
   - Share your expanded curated_mtg.py with other players
   - Upload your trained model to Hugging Face
   - Create a chat interface for your playgroup

Happy training! 🎴✨

---

## Summary: Your Three Scripts

| Script | Purpose | Examples | Time to Run | Easy to Expand? |
|--------|---------|----------|-------------|-----------------|
| `convert_mtg_data.py` | Card facts from MTGJSON | 1000-10000 | 1-2 min | Moderate |
| `convert_edhrec_data.py` | Commander strategy from EDHREC | 300-2000 | 1-5 min | Hard |
| `convert_curated_mtg.py` | High-quality expert knowledge | 30-50 | Instant | **Very Easy!** |

**Pro Tip:** Start with the curated script for custom knowledge since it's the easiest to modify!

---

## Troubleshooting

### "EDHREC script is slow"
- It's rate-limited to be respectful to their servers
- ~1 second per commander is normal
- Start with 25-50 commanders, expand later

### "Model doesn't know specific cards"
- Increase `--num-examples` in convert_mtg_data.py
- 10,000 examples covers most playable cards

### "Model doesn't know my favorite combo"
- Add it to convert_curated_mtg.py (super easy!)
- See the "Customizing Your Training Data" section

### "Training is taking too long"
- Reduce `--num-examples` for testing
- You can always retrain with more data later

### "Model gives wrong information"
- More training data usually helps
- Check if contradictory info in different sources
- Increase epochs or LoRA rank

### "Out of Memory during training"
- Reduce `--batch-size` to 2
- Reduce `--max-seq-length` to 256
- See USAGE.md for memory optimization tips

---

## Additional Resources

- **MTGJSON Documentation**: https://mtgjson.com/
- **EDHREC**: https://edhrec.com/
- **Commander Spellbook**: https://commanderspellbook.com/ (for more combos)
- **Scryfall API**: https://scryfall.com/docs/api (for additional card data)
- **MTG_DATA_SOURCES_GUIDE.md**: Complete guide to all data sources