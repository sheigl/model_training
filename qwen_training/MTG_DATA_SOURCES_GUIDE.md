# MTG Training Data Sources & Conversion Guide

This guide shows you **where to get MTG data** and **how to convert it** for training your model.

## Overview: Three Approaches

1. **Card Data** - Facts about individual cards (MTGJSON)
2. **Strategy Data** - Synergies, combos, deck building (EDHREC, curated)
3. **Community Knowledge** - Rules, combos, archetype knowledge (manually curated)

You'll want to **combine all three** for a comprehensive model!

---

## Approach 1: Card Facts (MTGJSON)

### What You Get
- Card names, types, costs, abilities
- Power/toughness, loyalty
- Color identity
- Format legality
- Subtypes

### Data Source
**MTGJSON** - https://mtgjson.com
- AtomicCards.json (~50MB) - One entry per unique card
- AllPrintings.json (~150MB) - Every printing of every card
- **YOU ALREADY HAVE THIS!**

### How to Convert

```bash
# Use your existing AllPrintings.json
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 3000 \
  --output mtg_cards.jsonl
```

### What Questions It Generates
- "What does Lightning Bolt do?"
- "What's the mana cost of Counterspell?"
- "Is Sol Ring legal in Commander?"
- "What are the power and toughness of Tarmogoyf?"

### Training Time
- 3000 examples ≈ 30 minutes on Arc B580

---

## Approach 2: Commander Strategy (EDHREC)

### What You Get
- Popular cards for each commander
- Card synergies and recommendations
- Theme-based suggestions
- Cards that go well together
- Commander-specific strategy

### Data Source
**EDHREC** - https://edhrec.com
- They have JSON endpoints (no official API but accessible)
- Provides data on:
  - Popular commanders
  - Card recommendations by commander
  - Synergy scores
  - Theme pages
  - Combo data

### How to Convert

```bash
# Generate EDHREC-based training data
python convert_edhrec_data.py \
  --num-commanders 50 \
  --output edhrec_training.jsonl
```

**Note:** This script is rate-limited and will take time (~50-60 seconds for 50 commanders)

### What Questions It Generates
- "What are good creatures for a Atraxa deck?"
- "What artifacts should I run in Urza?"
- "What themes work well with Krark?"
- "How many lands should I run in Commander?"
- "What's the best ramp package for Commander?"

### Training Time
- 50 commanders ≈ 300-500 examples ≈ 10-15 minutes training

### Python Library Available
You can also use `pyedhrec` library:
```bash
pip install pyedhrec
```

---

## Approach 3: Curated Knowledge (High Quality)

### What You Get
- Well-known combos explained
- Rules interactions
- Format staples
- Deck archetypes
- Draft strategy
- Sideboard guides

### Data Source
**Manually Curated** - Built from community knowledge
- Classic combos (Splinter Twin, Thassa's Oracle, etc.)
- Rules questions (stack, priority, etc.)
- Format-specific advice
- Archetype explanations

### How to Convert

```bash
# Generate curated high-quality data
python convert_curated_mtg.py \
  --output curated_mtg.jsonl
```

### What Questions It Generates
- "What's the Splinter Twin combo?"
- "How does the stack work?"
- "What's the difference between aggro and midrange?"
- "How do I beat control decks?"
- "What are the best removal spells in Modern?"

### Training Time
- ~30-40 examples ≈ 5 minutes training

### Expansion Opportunities
You can **easily expand** this file with your own knowledge:
- Your local meta combos
- Cards you play frequently
- Specific deck strategies you know
- Rules interactions you've encountered

---

## Additional Data Sources

### 4. Commander Spellbook (Combos)

**What:** Database of MTG combos
**URL:** https://commanderspellbook.com/
**Data:** JSON API with combo information

**How to use:**
```python
import requests

# Get all combos
response = requests.get('https://commanderspellbook.com/api/combos/')
combos = response.json()

# Each combo has:
# - Cards involved
# - How it works
# - Colors needed
# - Prerequisites
```

### 5. Scryfall (Card Database)

**What:** Comprehensive card database with search API
**URL:** https://scryfall.com/docs/api
**Data:** Every card with rulings, legalities, prices

**How to use:**
```python
import requests

# Search for cards
response = requests.get('https://api.scryfall.com/cards/search?q=t:legendary+t:creature+c:red')
cards = response.json()
```

### 6. MTG Goldfish (Metagame Data)

**What:** Popular decks and metagame analysis
**URL:** https://www.mtggoldfish.com/
**Data:** Deck lists, card prices, format meta

**Note:** No official API, but you could scrape it (be respectful of rate limits)

### 7. MTGTop8 (Tournament Data)

**What:** Tournament winning decklists
**URL:** https://www.mtgtop8.com/
**Data:** Competitive deck lists by format

**Note:** Great for competitive/cEDH knowledge

### 8. Reddit & Forums

**What:** Community discussions, strategy posts
**Sources:**
- r/EDH
- r/spikes
- r/magicTCG
- MTGSalvation forums

**How to use:** Could scrape high-quality strategy posts (requires more work)

---

## Recommended Workflow: Combine Everything!

### Step 1: Generate All Datasets

```bash
# 1. Card facts (YOUR EXISTING DATA)
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 3000 \
  --output mtg_cards.jsonl

# 2. Commander strategy
python convert_edhrec_data.py \
  --num-commanders 50 \
  --output edhrec_strategy.jsonl

# 3. Curated knowledge
python convert_curated_mtg.py \
  --output curated_knowledge.jsonl
```

### Step 2: Combine Datasets

```bash
# Combine all three files
cat mtg_cards.jsonl > combined_mtg.jsonl
cat edhrec_strategy.jsonl >> combined_mtg.jsonl
cat curated_knowledge.jsonl >> combined_mtg.jsonl

# Count total examples
wc -l combined_mtg.jsonl
```

### Step 3: Train on Combined Data

```bash
python finetune_qwen.py \
  --dataset file \
  --data-file combined_mtg.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --batch-size 4 \
  --output-dir ./qwen-mtg-complete
```

### Expected Results

**Total Training Data:**
- Card facts: ~3000 examples
- EDHREC strategy: ~300-500 examples
- Curated knowledge: ~30-40 examples
- **Total: ~3500 examples**

**Training Time:** ~40-50 minutes on Arc B580

**Model Capabilities:**
✅ Answer card-specific questions  
✅ Provide deck building advice  
✅ Explain combos and interactions  
✅ Discuss format strategy  
✅ Help with draft picks  
✅ Explain rules  

---

## Expanding the Curated Knowledge

The `convert_curated_mtg.py` script is the easiest to expand. Just add more questions!

### Example: Add More Combos

```python
def get_combo_questions():
    return [
        # ... existing combos ...
        {
            "user": "How does Protean Hulk combo work?",
            "assistant": "Protean Hulk dies and searches for creatures totaling 6 CMC or less. Common lines:\n\n1. Get Viscera Seer + Karmic Guide\n2. Karmic Guide returns Hulk\n3. Sacrifice Hulk again\n4. Get more combo pieces\n5. Assemble your win condition\n\nPopular targets: Mikaeus + Walking Ballista, or various 2-card combos."
        },
        # Add more!
    ]
```

### Example: Add Format Advice

```python
def get_pioneer_questions():
    return [
        {
            "user": "What are the best decks in Pioneer?",
            "assistant": "Top Pioneer decks (current meta):\n\n1. Rakdos Midrange - Efficient removal + value creatures\n2. Mono-Green Devotion - Ramp into Karn + big payoffs\n3. Izzet Phoenix - Recursive threats + cheap spells\n4. Lotus Field Combo - Win with Thespian's Stage\n5. Azorius Control - Counterspells + Supreme Verdict\n\nMeta shifts frequently, check MTGGoldfish for latest."
        }
    ]
```

### Example: Add Your Personal Knowledge

```python
def get_local_meta_questions():
    """Add knowledge about your playgroup's meta"""
    return [
        {
            "user": "What cards are popular in my local Commander meta?",
            "assistant": "Based on your playgroup:\n- Heavy graveyard strategies (bring Rest in Peace)\n- Lots of tribal decks (board wipes are key)\n- Combo-light (more focus on value)\n- High-power but not cEDH\n\nBest generic answers: Beast Within, Generous Gift, Cyclonic Rift"
        },
        {
            "user": "What's good against my friend's Ur-Dragon deck?",
            "assistant": "Against Ur-Dragon:\n- Early pressure (they're slow)\n- Graveyard hate (prevent Scion reanimation)\n- Counterspells for big dragons\n- Removal for Ur-Dragon itself\n- Board wipes (Wrath of God, Damnation)\n- Faster combo (race them)"
        }
    ]
```

---

## Quality vs Quantity

### High-Quality Data (Recommended)
- 3000-5000 total examples
- Mix of card facts + strategy + combos
- Train for 3-4 epochs
- **Result:** Accurate, helpful model

### Maximum Coverage
- 10,000+ examples
- All card facts + extensive strategy
- Train for 2-3 epochs (more data = fewer epochs)
- **Result:** Knows more cards, slightly less focused

### Minimal but Powerful
- 500-1000 carefully curated examples
- Focus on high-value knowledge
- Train for 5-6 epochs
- **Result:** Expert at specific topics

---

## Dealing with Large Datasets

If you want to train on everything:

```bash
# Generate massive card dataset
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 10000 \
  --output mtg_cards_large.jsonl

# Generate extensive EDHREC data
python convert_edhrec_data.py \
  --num-commanders 200 \
  --output edhrec_large.jsonl

# Combine
cat mtg_cards_large.jsonl > massive_mtg.jsonl
cat edhrec_large.jsonl >> massive_mtg.jsonl
cat curated_knowledge.jsonl >> massive_mtg.jsonl

# Train with adjusted settings
python finetune_qwen.py \
  --dataset file \
  --data-file massive_mtg.jsonl \
  --epochs 2 \
  --lora-r 48 \
  --lora-alpha 96 \
  --batch-size 4 \
  --gradient-accumulation 4 \
  --output-dir ./qwen-mtg-massive
```

**Training Time:** 2-3 hours for 15,000+ examples

---

## Next Steps

1. **Start Simple:**
   ```bash
   python convert_mtg_data.py --data-file AllPrintings.json --num-examples 2000 --output test.jsonl
   python finetune_qwen.py --dataset file --data-file test.jsonl
   ```

2. **Test Your Model:**
   Ask it questions and see what it knows

3. **Add More Data:**
   Run the EDHREC and curated scripts, combine datasets

4. **Iterate:**
   Add your own questions to `convert_curated_mtg.py`

5. **Retrain:**
   Train on the expanded dataset

---

## Summary: What Script Does What

| Script | Purpose | Examples Generated | Time to Run |
|--------|---------|-------------------|-------------|
| `convert_mtg_data.py` | Card facts from MTGJSON | 1000-10000 | 1-2 minutes |
| `convert_edhrec_data.py` | Commander strategy | 300-2000 | 1-5 minutes |
| `convert_curated_mtg.py` | High-quality combos/rules | 30-50 | Instant |

**Combined Result:** A model that's an MTG expert! 🎴✨

---

## Common Questions

**Q: Do I need to use all three scripts?**  
A: No, but combining them gives the best results. Start with card data, then add strategy.

**Q: Can I add my own questions?**  
A: Yes! Edit `convert_curated_mtg.py` and add your knowledge.

**Q: How often should I regenerate data?**  
A: MTGJSON updates daily. EDHREC updates constantly. Regenerate when new sets release or meta shifts.

**Q: What if I only care about Commander?**  
A: Use all three scripts but focus EDHREC data on Commander. Skip Modern/Legacy questions in curated data.

**Q: Can I train on competitive cEDH knowledge?**  
A: Yes! Add cEDH-specific combos and staples to `convert_curated_mtg.py`.

**Q: What about limited/draft?**  
A: The curated script has draft strategy. You could expand it with set-specific advice.

---

## Your Mission

```bash
# 1. Generate your datasets
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 3000 --output cards.jsonl
python convert_edhrec_data.py --num-commanders 50 --output strategy.jsonl  
python convert_curated_mtg.py --output knowledge.jsonl

# 2. Combine them
cat cards.jsonl strategy.jsonl knowledge.jsonl > complete_mtg.jsonl

# 3. Train your MTG expert
python finetune_qwen.py --dataset file --data-file complete_mtg.jsonl --epochs 3 --lora-r 32 --output-dir ./qwen-mtg-expert

# 4. Ask it ANYTHING about Magic!
```

You're building an MTG encyclopedia that can actually talk to you! 🚀
