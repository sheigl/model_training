# Quick Reference - MTG Rules Import

## MongoDB Credentials
All scripts now use these MongoDB credentials:
- **Username:** `root`
- **Password:** `whatever`
- **Auth Database:** `admin`

## Script Usage

### 1. Test the Parser
```bash
# With default filename (comprehensive_rules.txt)
python test_rules_parser.py

# With custom file path
python test_rules_parser.py ./data/MagicCompRules\ 20260116.txt
```

### 2. Import Rules to MongoDB
```bash
# With default filename (comprehensive_rules.txt)
python import_rules_to_mongo.py

# With custom file path
python import_rules_to_mongo.py ./data/MagicCompRules\ 20260116.txt
```

### 3. Generate Training Data
```bash
# Extracts from all MongoDB sources (no file path needed)
python extract_training_data.py
```

## Full Workflow Example

```bash
# Step 1: Download rules from https://magic.wizards.com/en/rules
# Save to: ./data/MagicCompRules 20260116.txt

# Step 2: Test parser
python test_rules_parser.py ./data/MagicCompRules\ 20260116.txt

# Expected output:
# ✓ File loaded: 9257 lines
# ✓ Estimated 1157 rules in file
# ✓ All tests passed!

# Step 3: Import to MongoDB
python import_rules_to_mongo.py ./data/MagicCompRules\ 20260116.txt

# Expected output:
# Found '1. Game Concepts' at line 12
# Found 'Glossary' at line 176
# Parsed 1157 individual rules
# Parsed 200+ glossary terms
# ✓ Rules successfully imported!

# Step 4: Generate training data
python extract_training_data.py

# Expected output:
# === Extracting Card Data ===
# === Extracting Combo Data ===
# === Extracting Comprehensive Rules Data ===
# ✓ Saved 50000 training examples to mongodb_mtg_training.jsonl

# Step 5: Train model
python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file mongodb_mtg_training.jsonl \
  --use-4bit \
  --batch-size 4 \
  --gradient-accumulation 4 \
  --lora-r 32 \
  --epochs 3 \
  --learning-rate 1e-4 \
  --output-dir ./qwen-3b-mtg-expert-v2
```

## MongoDB Databases

After import, you'll have these databases:

### mtg_rules
- **rules** collection: ~1157 rules with sections, categories
- **glossary** collection: ~200+ terms with definitions
- **meta** collection: version info (effective date: January 16, 2026)

### Existing databases (from your previous work):
- **mtg_json**: 108K cards, rulings
- **edhrec**: 928 articles, 26 guides
- **commander_spellbook**: 76K combos

## Verify Import

```bash
# Connect to MongoDB
mongosh -u root -p whatever --authenticationDatabase admin

# Check databases
use mtg_rules
db.rules.countDocuments()      // Should be ~1157
db.glossary.countDocuments()   // Should be ~200+
db.meta.findOne()              // Shows effective date

# Sample rules
db.rules.findOne({section: "702"})  // Keyword ability
db.rules.findOne({section: "100"})  // General rules
db.glossary.findOne()               // Glossary term

# Check categories
db.rules.aggregate([
  {$group: {_id: "$category", count: {$sum: 1}}},
  {$sort: {_id: 1}}
])
```

## Troubleshooting

### "0 rules parsed"
- Run test script first to validate file format
- Check that file is TXT format (not PDF or DOCX)
- Verify file has "1. Game Concepts" section marker

### "Authentication failed"
- Confirm MongoDB is running: `sudo systemctl status mongod`
- Check credentials are: root/whatever with authSource=admin
- Test connection: `mongosh -u root -p whatever --authenticationDatabase admin`

### "File not found"
- Use absolute or relative path with proper escaping
- Example: `./data/MagicCompRules\ 20260116.txt`
- Or quote the path: `"./data/MagicCompRules 20260116.txt"`

## File Locations

```
your_project/
├── training_data/
│   ├── test_rules_parser.py          # Test parser
│   ├── import_rules_to_mongo.py      # Import to MongoDB
│   ├── extract_training_data.py      # Generate JSONL
│   └── data/
│       └── MagicCompRules 20260116.txt   # Downloaded rules
└── mongodb_mtg_training.jsonl        # Generated training data
```

## What Gets Extracted

From rules database, ~4000 training examples:

1. **Keyword Abilities** (from section 702)
   - "What is deathtouch?" → [CR 702.2] full rule text
   - "How does flying work?" → [CR 702.9] explanation

2. **Game Concepts** (sections 100-199, 400-699)
   - "Explain the stack" → [CR 405] stack rules
   - "What is priority?" → [CR 117] timing rules

3. **Glossary Terms** (~200 examples)
   - "What is an ability in Magic?" → glossary definition
   - "What does 'target' mean?" → glossary explanation

4. **Random Rules** (~500 examples)
   - "What does rule 608.2 say?" → resolution rules
   - "What is rule 704.5?" → state-based actions

Combined with cards, combos, and strategy = 50K comprehensive examples!
