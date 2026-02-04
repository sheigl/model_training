# Magic: The Gathering Training Data Guide

This guide shows you how to train a model on Magic: The Gathering card data so you can ask it questions about cards, mechanics, and strategy.

## Quick Start

### Option 1: Use Your Existing AllPrintings.json
```bash
# You already have AllPrintings.json, so just use it!
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 2000 --output mtg_training.jsonl

# Then train
python finetune_qwen.py --dataset file --data-file mtg_training.jsonl --epochs 4 --output-dir ./qwen-mtg
```

### Option 2: Download Fresh Data
```bash
# Download AtomicCards.json (smaller, faster)
python convert_mtg_data.py --download --file-type atomic --num-examples 2000 --output mtg_training.jsonl

# OR download fresh AllPrintings.json
python convert_mtg_data.py --download --file-type allprintings --num-examples 2000 --output mtg_training.jsonl

# Then train
python finetune_qwen.py --dataset file --data-file mtg_training.jsonl --epochs 4 --output-dir ./qwen-mtg
```

### Option 3: Auto-detect Existing Files
```bash
# Script will automatically find AllPrintings.json or AtomicCards.json in current directory
python convert_mtg_data.py --num-examples 2000 --output mtg_training.jsonl
```

That's it! After training (20-30 minutes on Arc B580), you'll have an MTG expert model.

## What the Conversion Script Does

The `convert_mtg_data.py` script:

1. **Loads MTG data** from MTGJSON (your existing file or downloads fresh)
2. **Extracts card information** (name, type, mana cost, abilities, etc.)
3. **Generates Q&A pairs** in various styles
4. **Saves to JSONL format** ready for training

### AtomicCards vs AllPrintings

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

### 1. Basic Information
```
Q: What type of card is Lightning Bolt?
A: Lightning Bolt is an Instant.

Q: What is the mana cost of Counterspell?
A: The mana cost of Counterspell is Blue Blue.

Q: What colors is Sol Ring?
A: Sol Ring is colorless.
```

### 2. Card Abilities
```
Q: What does Birds of Paradise do?
A: Birds of Paradise: Flying. {T}: Add one mana of any color.

Q: What does Llanowar Elves do?
A: Llanowar Elves: {T}: Add {G}.
```

### 3. Creature Stats
```
Q: What are the power and toughness of Tarmogoyf?
A: Tarmogoyf is a */*.

Q: What is the mana value of Mulldrifter?
A: Mulldrifter has a mana value of 5.
```

### 4. Subtypes and Tribes
```
Q: What creature type is Snapcaster Mage?
A: Snapcaster Mage is a Human Wizard.

Q: What are the subtypes of Arid Mesa?
A: The subtypes of Arid Mesa are: Plains, Mountain.
```

### 5. Format Legality
```
Q: Is Black Lotus legal in Commander?
A: No, Black Lotus is banned in Commander.

Q: Is Lightning Bolt legal in Modern?
A: Yes, Lightning Bolt is legal in Modern.
```

### 6. Strategy Questions
```
Q: How can I use Delver of Secrets in combat?
A: Delver of Secrets is a 1/1 creature. At the beginning of your upkeep, look at the top card of your library. You may reveal that card. If an instant or sorcery card is revealed this way, transform Delver of Secrets. Consider its power and toughness when deciding whether to attack or block.

Q: When can I cast Path to Exile?
A: Path to Exile is an instant. You can cast it at any time you have priority, including during combat or on your opponent's turn.
```

### 7. Card Comparisons
```
Q: Which costs more mana, Thoughtseize or Inquisition of Kozilek?
A: Thoughtseize costs more mana. Inquisition of Kozilek has a mana value of 1, while Thoughtseize has a mana value of 1.
```

## Command-Line Options

### `convert_mtg_data.py` Options

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

### Options Explained

**`--data-file PATH`**: Path to your existing MTGJSON file
- Use this if you already have AllPrintings.json or AtomicCards.json
- Example: `--data-file AllPrintings.json`
- Example: `--data-file /path/to/AtomicCards.json`
- If omitted, script auto-detects files in current directory

**`--download`**: Download fresh data from MTGJSON
- Use this to get the latest card data
- Requires `--file-type` to specify which file to download
- Downloads to current directory

**`--file-type {atomic,allprintings}`**: Which file to download (requires `--download`)
- **`atomic`**: Downloads AtomicCards.json (~50MB, 2-3 min)
  - Smaller, faster
  - One entry per unique card
  - Good for general training
- **`allprintings`**: Downloads AllPrintings.json (~150MB, 5-10 min)
  - Larger, more complete
  - All printings of all cards
  - Includes set-specific data

**`--num-examples N`**: How many Q&A pairs to generate
- **500**: Quick test (covers ~100 cards)
- **1000**: Good starting point (covers ~200 cards)
- **2000**: Better coverage (covers ~400 cards) - **RECOMMENDED**
- **5000**: Comprehensive (covers ~1000 cards)
- **10000+**: Maximum coverage (most of MTG)

**`--output FILE`**: Where to save the training data
- Default: `mtg_training.jsonl`
- Use different names for different dataset sizes

## Training Recommendations

### For Casual Play Knowledge (using your existing file)
```bash
# Generate moderate dataset from your AllPrintings.json
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 1500 \
  --output mtg_casual.jsonl

# Train with standard settings
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_casual.jsonl \
  --epochs 4 \
  --lora-r 16 \
  --output-dir ./qwen-mtg-casual
```

**Time:** ~20 minutes  
**Covers:** Major cards and mechanics  
**Good for:** General MTG questions

### For Competitive Knowledge
```bash
# Generate large dataset
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 5000 \
  --output mtg_competitive.jsonl

# Train with larger LoRA
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_competitive.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --lora-alpha 64 \
  --output-dir ./qwen-mtg-competitive
```

**Time:** ~60 minutes  
**Covers:** Extensive card pool  
**Good for:** Deck building, format questions

### For Commander Focus
```bash
# Generate Commander-focused data
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 3000 \
  --output mtg_commander.jsonl

# Train with balanced settings
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_commander.jsonl \
  --epochs 4 \
  --lora-r 24 \
  --output-dir ./qwen-mtg-commander
```

**Time:** ~35 minutes  
**Covers:** Commander staples and synergies  
**Good for:** Commander deck building

### Download Fresh Data (if you want the latest cards)
```bash
# Download latest AtomicCards
python convert_mtg_data.py \
  --download \
  --file-type atomic \
  --num-examples 2000 \
  --output mtg_latest.jsonl
  
# Train
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_latest.jsonl \
  --epochs 4 \
  --output-dir ./qwen-mtg-latest
```

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

## Adding Custom Questions

You can edit `convert_mtg_data.py` to add your own question types. For example, to add combo questions:

```python
def generate_combo_questions(card_name, card):
    """Generate questions about card combos"""
    questions = []
    
    # Add your combo knowledge
    combos = {
        "Splinter Twin": "Splinter Twin combos with Pestermite or Deceiver Exarch to create infinite creatures.",
        "Thassa's Oracle": "Thassa's Oracle wins the game with Demonic Consultation or Tainted Pact.",
    }
    
    if card_name in combos:
        questions.append({
            "user": f"What combos with {card_name}?",
            "assistant": combos[card_name]
        })
    
    return questions
```

Then add it to the `generate_training_data` function:
```python
questions.extend(generate_combo_questions(card_name, card))
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

## Example Workflow

### Using Your Existing AllPrintings.json

```bash
# 1. Generate training data from your existing file
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 2000 \
  --output mtg_2k.jsonl

# 2. Train the model
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_2k.jsonl \
  --epochs 4 \
  --lora-r 24 \
  --batch-size 4 \
  --output-dir ./qwen-mtg-2k

# 3. Test it (wait for training to complete)
# Use the test code from the guide

# 4. Generate more examples for better coverage
python convert_mtg_data.py \
  --data-file AllPrintings.json \
  --num-examples 5000 \
  --output mtg_5k.jsonl

# 5. Train a better model
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_5k.jsonl \
  --epochs 3 \
  --lora-r 32 \
  --output-dir ./qwen-mtg-5k
```

### Downloading Fresh Data

```bash
# 1. Download latest AtomicCards (smaller, faster)
python convert_mtg_data.py \
  --download \
  --file-type atomic \
  --num-examples 2000 \
  --output mtg_fresh.jsonl

# 2. Or download AllPrintings (more complete)
python convert_mtg_data.py \
  --download \
  --file-type allprintings \
  --num-examples 2000 \
  --output mtg_complete.jsonl

# 3. Train on the fresh data
python finetune_qwen.py \
  --dataset file \
  --data-file mtg_fresh.jsonl \
  --epochs 4 \
  --output-dir ./qwen-mtg-fresh
```

## Questions You Can Ask the Trained Model

After training, you can ask:
- "What does [card name] do?"
- "What type of card is [card name]?"
- "What's the mana cost of [card name]?"
- "What colors is [card name]?"
- "Is [card name] legal in [format]?"
- "What are the power and toughness of [creature]?"
- "What creature types does [creature] have?"
- "When can I cast [card name]?"
- "How can I use [card name] in combat?"

The more examples you generate, the more cards it will know!

## Next Steps

1. **Start small**: Generate 1000 examples and train to test
2. **Evaluate**: Ask it questions about cards you know
3. **Scale up**: If it works well, generate 5000+ examples
4. **Customize**: Add your own question types for specific needs
5. **Iterate**: Retrain with more data or different settings

Happy training! 🎴✨