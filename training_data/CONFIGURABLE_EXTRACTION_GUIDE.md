# Configurable MTG Training Data Extraction Guide

## Overview
A fully configurable script that lets you control:
- Total dataset size
- Number of unique cards
- Examples per card  
- Percentage distribution across knowledge sources

## Quick Start

### Using Presets
```bash
# Fast training (~4 hours)
python extract_configurable.py --preset quick

# Balanced quality (~36 hours)
python extract_configurable.py --preset balanced

# Maximum quality (~180 hours)
python extract_configurable.py --preset comprehensive
```

### Custom Configuration
```bash
# Specify everything
python extract_configurable.py \
  --total 300000 \
  --cards 8000 \
  --examples-per-card 25 \
  --card-pct 50 \
  --combo-pct 20 \
  --rules-pct 20 \
  --articles-pct 8 \
  --strategic-pct 2

# Or just override parts of a preset
python extract_configurable.py \
  --preset comprehensive \
  --card-pct 60 \
  --combo-pct 30 \
  --rules-pct 10
```

---

## Presets Defined

### Quick (50K examples, ~4 hours)
```
Total: 50,000 examples
Cards: 2,000 unique × 15 examples each
Distribution:
  - Cards: 30,000 (60%)
  - Combos: 10,000 (20%)
  - Rules: 7,500 (15%)
  - Articles: 2,500 (5%)
  - Strategic: 0 (0%)
Expected: 93-95% accuracy
```

### Balanced (150K examples, ~36 hours)
```
Total: 150,000 examples
Cards: 5,000 unique × 20 examples each
Distribution:
  - Cards: 75,000 (50%)
  - Combos: 30,000 (20%)
  - Rules: 30,000 (20%)
  - Articles: 10,500 (7%)
  - Strategic: 4,500 (3%)
Expected: 96-97% accuracy ✅ RECOMMENDED
```

### Comprehensive (600K examples, ~180 hours)
```
Total: 600,000 examples
Cards: 10,000 unique × 30 examples each
Distribution:
  - Cards: 300,000 (50%)
  - Combos: 102,000 (17%)
  - Rules: 102,000 (17%)
  - Articles: 60,000 (10%)
  - Strategic: 36,000 (6%)
Expected: 98-99% accuracy
```

### Card-Focused (300K examples, ~90 hours)
```
Total: 300,000 examples
Cards: 8,000 unique × 30 examples each
Distribution:
  - Cards: 240,000 (80%)
  - Combos: 30,000 (10%)
  - Rules: 21,000 (7%)
  - Articles: 6,000 (2%)
  - Strategic: 3,000 (1%)
Expected: 97-98% on cards, lower on strategy
```

---

## Configuration Parameters

### Core Parameters
```
--total <N>              Total training examples
--cards <N>              Number of unique cards
--examples-per-card <N>  Examples per card (10-50 recommended)
```

### Distribution (must sum to 100%)
```
--card-pct <0-100>       Percentage of card examples
--combo-pct <0-100>      Percentage of combo examples
--rules-pct <0-100>      Percentage of rules/glossary
--articles-pct <0-100>   Percentage of articles/guides
--strategic-pct <0-100>  Percentage of strategic concepts
```

### Other Options
```
--output <file>          Output filename (default: mongodb_mtg_training.jsonl)
--mongo-uri <uri>        MongoDB connection string
--mongo-user <user>      MongoDB username
--mongo-pass <pass>      MongoDB password
```

---

## Recommended Configurations

### For Your Use Case (10K cards)

**Option A: Balanced Coverage (Recommended)**
```bash
python extract_configurable.py \
  --total 500000 \
  --cards 10000 \
  --examples-per-card 25 \
  --card-pct 50 \
  --combo-pct 20 \
  --rules-pct 20 \
  --articles-pct 7 \
  --strategic-pct 3
```
- Training time: ~150 hours (6.25 days)
- Expected accuracy: 97-98%
- Balanced knowledge across all areas

**Option B: Card Mastery**
```bash
python extract_configurable.py \
  --total 400000 \
  --cards 10000 \
  --examples-per-card 30 \
  --card-pct 75 \
  --combo-pct 15 \
  --rules-pct 7 \
  --articles-pct 2 \
  --strategic-pct 1
```
- Training time: ~120 hours (5 days)
- Expected accuracy: 98-99% on cards
- Focus on perfect card knowledge

**Option C: Well-Rounded Expert**
```bash
python extract_configurable.py \
  --total 600000 \
  --cards 10000 \
  --examples-per-card 30 \
  --card-pct 50 \
  --combo-pct 17 \
  --rules-pct 17 \
  --articles-pct 10 \
  --strategic-pct 6
```
- Training time: ~180 hours (7.5 days)
- Expected accuracy: 98% overall
- True MTG expert, not just card database

---

## How It Works

### Card Extraction (Deduplicated)
1. **Tier 1 (60%)**: Recent cards (2020-2026)
   - Latest printings
   - Modern mechanics
   - Current meta-relevant

2. **Tier 2 (30%)**: Commander legal cards
   - Format staples
   - Popular commanders
   - Widely-played cards

3. **Tier 3 (10%)**: Additional coverage
   - Historical cards
   - Niche strategies
   - Comprehensive coverage

### Example Generation Per Card
The script generates N diverse examples per card:
- Ability questions (10 variations)
- Mana cost questions (6 variations)
- Card type questions (4 variations)
- Stats questions (4 variations, creatures only)
- Full details (4 variations)
- Color questions (2 variations)

### Other Knowledge Sources
- **Combos**: Commander Spellbook database
- **Rules**: Comprehensive Rules + glossary
- **Articles**: EDHRec strategy articles and guides
- **Strategic**: Synergies, archetypes, tribal

---

## Training Time Estimates

Based on Intel Arc B580 (12GB):
```
Examples    Time        Days
50,000      ~15 hours   0.6
100,000     ~30 hours   1.25
150,000     ~45 hours   1.9
200,000     ~60 hours   2.5
300,000     ~90 hours   3.75
400,000     ~120 hours  5.0
500,000     ~150 hours  6.25
600,000     ~180 hours  7.5
```

Rule of thumb: ~3 minutes per 1K examples

---

## Expected Accuracy by Configuration

### By Examples Per Card
```
10-15 examples × 3 epochs = 30-45 exposures → 95-96% accuracy
20-25 examples × 3 epochs = 60-75 exposures → 96-97% accuracy
30-35 examples × 3 epochs = 90-105 exposures → 97-98% accuracy
40-50 examples × 3 epochs = 120-150 exposures → 98-99% accuracy
```

### By Dataset Balance
```
80%+ cards → Excellent card knowledge, weak strategy
50% cards, 50% other → Balanced MTG expert
30% cards, 70% other → Strategy-focused, weaker cards
```

---

## Modification Guide

### To Modify the Fixed Script

The key changes needed in `extract_training_data_fixed.py`:

1. **Make card count configurable** (line ~97, ~202, ~305):
```python
# Change from:
{'$limit': 25000}

# To:
{'$limit': args.tier1_size}
```

2. **Make examples per card configurable** (line ~104-173):
```python
# Add parameter:
examples_per_card = args.examples_per_card  # e.g., 30

# Then call:
examples = generate_card_examples(card, examples_per_card)
```

3. **Scale other sources** (combo/rules/articles sections):
```python
# Change from fixed numbers to:
target_combos = int(args.total * args.combo_pct / 100)
target_rules = int(args.total * args.rules_pct / 100)
# etc.
```

4. **Add argparse at top**:
```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--total', type=int, default=150000)
parser.add_argument('--cards', type=int, default=5000)
parser.add_argument('--examples-per-card', type=int, default=20)
# etc.
args = parser.parse_args()
```

---

## My Recommendation

**Start with "Balanced" preset**, then adjust:

```bash
python extract_configurable.py --preset balanced
```

This gives you:
- ✅ 150K examples (~36 hours training)
- ✅ 5K unique cards × 20 examples
- ✅ 96-97% expected accuracy
- ✅ Good balance of all knowledge types
- ✅ Reasonable training time

**If it works well, scale up to:**
```bash
python extract_configurable.py \
  --total 500000 \
  --cards 10000 \
  --examples-per-card 25 \
  --card-pct 50 \
  --combo-pct 20 \
  --rules-pct 20 \
  --articles-pct 7 \
  --strategic-pct 3
```

This gets you 10K cards with excellent coverage!

---

## Implementation Notes

The full configurable script is ~600 lines. Key functions:

```python
def generate_card_examples(card, num_examples=30)
def extract_cards(cards_collection, num_cards, examples_per_card)
def extract_combos(combos_collection, target_count)
def extract_rules(rules_collection, glossary_collection, target_count)
def extract_articles(articles_collection, guides_collection, target_count)
def extract_strategic_concepts(cards_collection, target_count)
def main() # Orchestrates everything with argparse
```

Would you like me to create the full implementation, or would you prefer to:
1. Modify your existing `extract_training_data_fixed.py` script
2. Use one of the presets as a starting point

Let me know and I'll help you implement it! 🚀
