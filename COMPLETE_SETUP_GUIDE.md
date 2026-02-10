# Complete MTG Expert Model Training Pipeline

This guide walks you through creating a comprehensive Magic: The Gathering expert model that knows:
- ✅ All 108K+ cards and their abilities
- ✅ 76K+ combos from Commander Spellbook
- ✅ Strategic advice from EDHRec articles
- ✅ Comprehensive Rules (292 pages)
- ✅ When to admit uncertainty

## Prerequisites

1. **MongoDB running** on localhost:27017
2. **Python 3.8+** with required packages
3. **Intel ARC B580 GPU** (or CUDA GPU)
4. **Existing MongoDB databases** (from your previous work):
   - `mtg_json` - Card database
   - `edhrec` - Articles and guides
   - `commander_spellbook` - Combos

## Step 1: Download Comprehensive Rules

```bash
# Visit https://magic.wizards.com/en/rules
# Download the TXT version (latest: January 16, 2026)
# Save as: comprehensive_rules.txt
```

Or use wget if your network allows:
```bash
# Check the latest URL on the Magic rules page
wget -O comprehensive_rules.txt "https://media.wizards.com/2026/downloads/MagicCompRules%20YYYYMMDD.txt"
```

**Verify you have the file:**
```bash
ls -lh comprehensive_rules.txt
# Should show a file around 1-2 MB
```

## Step 1.5: Test the Parser (Recommended)

Before importing, validate the parser works with your file:

```bash
python test_rules_parser.py
```

This will:
- ✅ Confirm the file format is correct
- ✅ Show estimated rule count (~3000+)
- ✅ Display sample rules from different sections
- ✅ Validate glossary detection

**Expected output:**
```
=== Testing Parser with Sample Content ===
✓ Effective Date: January 16, 2026
✓ Found '1. Game Concepts' at line X
✓ Found 'Glossary' at line Y
✓ Found 3241 rules
✓ File validation complete - ready for import!
```

## Step 2: Import Rules to MongoDB

```bash
python import_rules_to_mongo.py
```

This creates a new database `mtg_rules` with:
- `rules` collection (~3000+ individual rules)
- `glossary` collection (~200+ terms)
- `meta` collection (version info)

**Verify the import:**
```bash
mongosh
> use mtg_rules
> db.rules.countDocuments()  // Should be ~3000+
> db.glossary.countDocuments()  // Should be ~200+
> db.rules.findOne({section: "702"})  // Show a keyword ability
```

## Step 3: Generate Training Data

```bash
python extract_training_data.py
```

This creates `mongodb_mtg_training.jsonl` with ~50,000 examples:

**Data Distribution:**
- ~13,000 - Card facts (what cards do, mana costs, types)
- ~3,000 - Card rulings (official interactions)
- ~10,000 - Combo explanations (step-by-step)
- ~10,000 - Honesty examples (teaching limitations)
- ~5,000 - Strategic articles (deck building, meta)
- ~5,000 - EDHRec guides (how-to content)
- ~4,000 - Comprehensive Rules (keywords, game concepts, glossary)

**Sample output:**
```
=== Extracting Card Data ===
Processing 10000 cards...
Generated 30000 card training examples

=== Extracting Card Rulings ===
Processing 3000 rulings...
Generated 3000 ruling examples

=== Extracting Combo Data ===
Processing 5000 combos...
Generated 10000 combo examples

=== Creating Honesty Training Examples ===
Generated 10000 honesty training examples

=== Extracting Article Data ===
Processing 500 articles...
Generated 1000 article examples

=== Extracting Guide Data ===
Processing 26 guides...
Generated 5000 guide examples

=== Extracting Comprehensive Rules Data ===
Found 3241 rules in database
Extracting keyword abilities...
Extracting game concepts...
Extracting glossary terms...
Extracting general rules...
Generated 4000 rules examples

=== Balancing Dataset ===
Final dataset size: 50000

✓ Saved 50000 training examples to mongodb_mtg_training.jsonl
```

## Step 4: Train the Model

```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 32 \
  --use-galore \
  --galore-rank 256 \
  --batch-size 4 \
  --learning-rate 5e-5 \
  --gradient-accumulation 4 \
  --epochs 3 \
  --output-dir ./qwen-3b-mtg-expert \
  --save-steps 500 \
  --warmup-steps 50
```

**Training parameters explained:**
- `--use-4bit` - Memory efficient (fits on 12GB VRAM)
- `--use-galore` - Memory-efficient optimizer (reduces optimizer memory by 60%)
- `--galore-rank 256` - GaLore subspace rank (higher than LoRA for better gradients)
- `--lora-r 32` - LoRA rank (good capacity for 140K examples)
- `--learning-rate 5e-5` - Conservative learning rate (stable with GaLore)
- `--epochs 3` - Train for 3 passes over the full dataset
- `--save-steps 500` - Save checkpoint every 500 steps (enables recovery)
- `--warmup-steps 50` - Gradual LR warmup (improves stability)

**Expected training time:**
- ~20-22 hours on Intel ARC B580
- ~15-18 hours on RTX 4090
- ~22-25 hours on RTX 3090

**Monitor training:**
```bash
# If logging to file
tail -f training.log

# Watch for:
# - Loss starting around 2.0 and decreasing
# - No NaN values
# - Perplexity decreasing
```

**If you get Out of Memory:**
```bash
# Reduce batch size, increase gradient accumulation
--batch-size 2 \
--gradient-accumulation 8 \
```

**For maximum quality (if you have time):**
```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 64 \
  --use-galore \
  --galore-rank 512 \
  --batch-size 2 \
  --learning-rate 3e-5 \
  --gradient-accumulation 8 \
  --epochs 3 \
  --output-dir ./qwen-3b-mtg-expert-highrank \
  --save-steps 500 \
  --warmup-steps 100
```
*Trade-off: +30% training time (~26-28 hours) for higher quality*

## Step 5: Test the Model

```bash
python test_model.py
```

Create a simple test script:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load your trained model
model = AutoModelForCausalLM.from_pretrained(
    "./qwen-3b-mtg-expert-v2",
    device_map="auto",
    torch_dtype=torch.float16
)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")

def ask(question):
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.7)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Extract just the assistant's response
    return response.split("assistant\n")[-1]

# Test card knowledge
print("Q: What does Lightning Bolt do?")
print(ask("What does Lightning Bolt do?"))
print()

# Test rules knowledge
print("Q: What is deathtouch?")
print(ask("What is deathtouch?"))
print()

# Test combo knowledge
print("Q: How does Thassa's Oracle and Demonic Consultation work?")
print(ask("How does Thassa's Oracle and Demonic Consultation work?"))
print()

# Test honesty
print("Q: Do Fictitious Card A and Fictitious Card B combo?")
print(ask("Do Fictitious Card A and Fictitious Card B combo?"))
```

## Expected Results

### ✅ Card Knowledge
```
Q: What does Lightning Bolt do?
A: Lightning Bolt: Lightning Bolt deals 3 damage to any target.
```

### ✅ Rules Knowledge
```
Q: What is deathtouch?
A: [CR 702.2] Deathtouch is a static ability. Any nonzero amount of combat 
damage dealt by a source with deathtouch to a creature is considered to be 
lethal damage...
```

### ✅ Combo Knowledge
```
Q: How does Thassa's Oracle and Demonic Consultation work?
A: This is a well-known combo. Cast Demonic Consultation and name a card 
not in your deck, exiling your entire library. Then cast Thassa's Oracle. 
When it enters, since your library is empty, you win the game.
```

### ✅ Honest Uncertainty
```
Q: Do Fictitious Card A and Fictitious Card B combo?
A: I don't have information about a combo between those specific cards in 
my training data. To verify if they combo, I recommend checking Commander 
Spellbook (commanderspellbook.com)...
```

## Troubleshooting

### Issue: Rules database is empty
**Solution:** Make sure `comprehensive_rules.txt` is in the correct location and run `import_rules_to_mongo.py`

### Issue: Training runs out of memory
**Solutions:**
- Reduce `--batch-size` to 2 or 1
- Increase `--gradient-accumulation` to 8
- Use `--use-4bit` if not already

### Issue: Model gives wrong answers
**Possible causes:**
1. Training data quality - Check your MongoDB collections
2. Overfitting - Reduce epochs to 2
3. Learning rate too high - Try 5e-5

### Issue: Model still hallucinates combos
**Solution:** Increase the proportion of honesty examples in the dataset. Edit `create_honesty_examples()` to multiply templates by 100 instead of 50.

## Data Quality Checks

Before training, verify your data:

```bash
# Check training file exists and has examples
wc -l mongodb_mtg_training.jsonl  # Should show ~50,000

# Check for valid JSON
head -n 1 mongodb_mtg_training.jsonl | python -m json.tool

# Sample random examples
shuf mongodb_mtg_training.jsonl | head -n 5 | python -m json.tool
```

## Monitoring Training

Watch the training output for:
- **Loss decreasing** - Good sign (should go from ~2.0 to ~0.5)
- **Perplexity decreasing** - Model is learning
- **No NaN values** - If you see NaN, lower learning rate

## Next Steps

Once trained, you can:
1. **Quantize further** for deployment (GGUF format)
2. **Create a chat interface** (Gradio, Streamlit)
3. **Deploy as API** (FastAPI, vLLM)
4. **Iterate on data** - Add more edge cases if needed

## Database Schema Reference

### mtg_json.cards
- `name`, `text`, `type`, `manaCost`, `power`, `toughness`

### mtg_json.cardRulings
- `uuid`, `date`, `text`

### edhrec.articles
- `title`, `content`, `excerpt`, `tags`, `author`

### edhrec.guides
- `title`, `guide` (chapters/sections)

### commander_spellbook.variants
- `uses` (cards in combo), `produces` (results), `description`

### mtg_rules.rules
- `rule_number`, `section`, `text`, `category`

### mtg_rules.glossary
- `term`, `definition`

## Files Reference

- `test_rules_parser.py` - Test parser before full import (NEW!)
- `import_rules_to_mongo.py` - Import Comprehensive Rules to MongoDB
- `extract_training_data.py` - Generate training JSONL from all MongoDB sources
- `finetune_qwen.py` - Train the model (your existing script)
- `comprehensive_rules.txt` - Downloaded from Wizards (you provide)
- `mongodb_mtg_training.jsonl` - Generated training data (50K examples)

## Success Metrics

Your model should:
1. ✅ Correctly state Lightning Bolt deals 3 damage
2. ✅ Explain the stack and priority
3. ✅ Describe known combos accurately
4. ✅ Cite rules by number [CR XXX]
5. ✅ Admit when it doesn't know something
6. ✅ Recommend Commander Spellbook for verification
7. ✅ Understand keyword abilities (deathtouch, flying, etc.)
8. ✅ Give strategic advice on deck building

If all these pass, you have a world-class MTG expert model! 🎉
