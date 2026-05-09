# Model Training Repository - Agent Skill Reference

> Comprehensive guide to fine-tuning Qwen models for Magic: The Gathering expertise. Optimized for AI agents to understand, operate, and extend this pipeline.

---

## 1. Repository Structure

```
model_training/
├── qwen_training/                    # Core fine-tuning pipeline
│   ├── finetune_qwen.py             # Main fine-tuning script (~775 lines)
│   ├── run_training.sh              # Shell wrapper for training
│   ├── merge_model.py               # Merge LoRA + export GGUF (21 lines)
│   ├── test_checkpoint.py           # Load checkpoint + test Q&A
│   ├── test_model_unsloth.py        # Unsloth-loaded inference test
│   ├── test_model.py                # Standard transformer test
│   ├── test_cpu.py                  # CPU-only inference validation
│   ├── test_frequency.py            # Frequency analysis on outputs
│   ├── batch_test.py                # Batch evaluation on multiple prompts
│   ├── USAGE.md                     # Detailed usage guide
│   ├── MTG_TRAINING_GUIDE.md        # MTG-specific training guide
│   ├── MTG_DATA_SOURCES_GUIDE.md    # Data source documentation
│   └── unsloth_compiled_cache/      # Cached compiled Unsloth trainers
├── training_data/                    # Data generation & management
│   ├── convert_mtg_data.py          # Card facts from MTGJSON
│   ├── convert_edhrec_data.py       # Commander strategy from EDHREC
│   ├── convert_curated_mtg.py       # Curated expert knowledge
│   ├── extract_training_data.py     # Configurable extraction from MongoDB (1069 lines)
│   ├── balance_dataset.py           # Balance card vs strategic data (40/30/20/10)
│   ├── dedup_synthetic_queries.py   # Deduplicate synthetic queries via MongoDB aggregation
│   ├── analyze_card_frequency.py    # Identify low-exposure cards via regex
│   ├── check_jsonl.py               # Validate JSONL format
│   ├── generate_with_api.py         # Generate Q&A via OpenAI/Claude API (215 lines)
│   ├── import_rules_to_mongo.py     # Parse MTG rules TXT, save to MongoDB (542 lines)
│   ├── inspect_mongodb.py           # Explore MTG database (223 lines)
│   └── generate_synthetic_data/     # Synthetic generator suite (31 generators)
│       ├── main.py                  # Orchestrator - saves to MongoDB (514 lines)
│       ├── query_model.py           # Ollama/Anthropic/OpenAI API wrapper (388 lines)
│       ├── generate_*.py            # 31 specialized generators
│       ├── run_combos.sh            # Shell runner for combo generation
│       ├── run_rules.sh             # Shell runner for rules generation
│       ├── scryfall_mongodb.py      # Scryfall query parser + MongoDB sync (814 lines)
│       ├── common.py                # Prompt builders + validation helpers (910 lines)
│       ├── models.py                # Pydantic-like data classes
│       ├── constants.py             # MTG notation, system messages, scoring
│       └── logger.py                # Rich-formatted logging
├── training.py                       # Standard vs Unsloth benchmark script (380 lines)
├── tiny_gpt/                         # Minimal GPT implementation (experimental)
├── pyproject.toml                    # Project config (Python >=3.10, PyTorch XPU)
├── .venv/                            # Virtual environment
├── mongodb.compose.yml               # Docker Compose for MongoDB
├── GALORE_TRAINING_GUIDE.md          # GaLore memory optimization guide
└── training_data/data/               # Final JSONL training datasets
```

---

## 2. Core Training Pipeline

### 2.1 `finetune_qwen.py` — Main Fine-Tuning Script

**Framework stack:** Unsloth `FastLanguageModel` + TRL `SFTTrainer` + (optional) GaLore `GaLoreAdamW`

**Execution flow:**
```
parse_args()
  → detect_device()                    # XPU → CUDA → CPU priority
  → load_model()                       # Unsloth FastLanguageModel.from_pretrained()
  → apply_lora()                       # FastLanguageModel.get_peft_model()
  → load_dataset()                     # sample / hf / file (JSONL)
  → prepare_dataset_for_unsloth()      # Convert messages → text column via chat template
  → create_training_config()           # SFTConfig construction
  → create_trainer()                   # SFTTrainer instantiation
  → trainer.train()                    # Training loop
  → model.save_pretrained()            # Save LoRA adapter
  → test_model()                       # Inference test with default MTG prompts
```

**Critical implementation details:**
- **Do NOT call `prepare_model_for_kbit_training()`** — Unsloth handles k-bit setup internally in `from_pretrained()`. Calling it afterward corrupts dtypes.
- Dataset must be pre-formatted to `text` column (not `formatting_func`) — avoids dtype mismatches with Unsloth's patched layers.
- Chat template: `chatml` (Qwen's native format, applied via `get_chat_template`).
- LoRA target modules: `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj` (all attention + MLP layers).
- `prepare_dataset_for_unsloth()` applies the tokenizer's chat template to each `messages` list, stores result in a flat `text` column. Dataset is then passed as `dataset_text_field="text"` to `SFTTrainer`.

**Training config (SFTConfig):**
| Parameter | Default | Notes |
|-----------|---------|-------|
| `optim` | `adamw_8bit` | 8-bit Adam saves ~50% optimizer memory |
| `bf16` | `True` | Required for modern GPUs (XPU/CUDA) |
| `gradient_checkpointing` | `True` | Uses Unsloth's optimized version |
| `save_strategy` | `steps` | Every 200 steps, keeps 3 latest checkpoints |
| `eval_strategy` | `epoch` | Eval at end of each epoch |
| `packing` | `False` | Each sequence is independent (required for chat templates) |
| `report_to` | `none` | Set to `wandb` or `tensorboard` for logging |
| `warmup_ratio` | `0.03` | 3% of total steps |
| `weight_decay` | `0.01` | Standard regularization |

**GaLore integration (lines 99-109 in finetune_qwen.py):**
```python
try:
    from galore_torch import GaLoreAdamW, GaLoreAdamW8bit
    from galore_torch.galore_projector import GaLoreProjector
    GALORE_AVAILABLE = True
    torch.serialization.add_safe_globals([GaLoreProjector])
except ImportError:
    GALORE_AVAILABLE = False
```
- Install: `pip install galore-torch`
- GaLore reduces optimizer memory ~60-70% by projecting gradients to low-rank space
- **Essential for 7B+ models on <12GB GPUs**
- Default: `galore-rank=128`, `galore-update-proj-gap=200`, `galore-scale=0.25`
- Uses `GaLoreAdamW8bit` when both `--use-4bit` and `--use-galore` are set

**`prepare_dataset_for_unsloth()` function:**
```python
def prepare_dataset_for_unsloth(dataset, tokenizer):
    """Convert messages column to text column using chat template."""
    def convert_to_text(examples):
        texts = []
        for messages in examples['messages']:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
            texts.append(text)
        return {"text": texts}
    return dataset.map(convert_to_text, batched=True)
```

### 2.2 `run_training.sh` — Shell Wrapper

Full command executed:
```bash
~/code/model_training/.venv/bin/python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-7B-Instruct \
  --dataset file \
  --data-file ~/code/model_training/training_data/data/mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 32 --lora-alpha 64 --lora-dropout 0 \
  --batch-size 2 --learning-rate 2e-4 \
  --gradient-accumulation 8 \
  --epochs 3 --max-seq-length 2048 \
  --resume-from-checkpoint ./output/checkpoint-43443 \
  --output-dir ~/code/model_training/qwen_training/output-7b-mtg-unsloth
```

**Effective batch size:** `2 * 8 = 16`
**Total training steps:** `(dataset_size / 16) * 3`
**Checkpoint resumption path:** Must point to an existing `checkpoint-XXXXX` directory.

### 2.3 `merge_model.py` — Model Export

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="./output-7b-mtg-unsloth",  # your LoRA output dir
    dtype=None,
    load_in_4bit=True,
)

# Full 16-bit merged model
model.save_pretrained_merged(
    "./output-7b-mtg-unsloth-merged",
    tokenizer,
    save_method="merged_16bit",  # or "merged_4bit" for smaller file
)

# GGUF for llama.cpp / LLM.cpp
model.save_pretrained_gguf(
    "./output-7b-mtg-unsloth-merged-gguf",
    tokenizer,
    quantization_method="q5_k_m"  # good quality/size balance
)
```

**Export options:**
- `merged_16bit` — Full precision, no quantization (largest file, highest quality)
- `merged_4bit` — 4-bit quantized merged model
- `gguf` with `q5_k_m` — GGUF format for llama.cpp inference, ~5-bit quantization

### 2.4 Evaluation Scripts

| Script | Purpose |
|--------|---------|
| `test_checkpoint.py` | Load checkpoint + base model, run Q&A test (3 default prompts) |
| `test_model_unsloth.py` | Test Unsloth-loaded model inference with chat template |
| `test_model.py` | Standard transformers + Peft model test |
| `test_cpu.py` | CPU-only inference validation |
| `test_frequency.py` | Frequency analysis on generated outputs |
| `batch_test.py` | Batch evaluation on multiple prompts |

### 2.5 `training.py` — Benchmark Script (Comparison Only)

Compares standard TRL training vs Unsloth on Qwen2.5-0.5B:
- Unsloth: ~4.5x faster, ~50% less GPU memory
- Standard: uses `prepare_model_for_kbit_training()` + manual LoRAConfig
- Dataset: `mlabonne/guanaco-llama2-1k` (1K Alpaca-style examples)
- Uses `check_gpu()`, `get_gpu_memory()`, `get_peak_memory()` for profiling

---

## 3. Data Generation Pipeline

### 3.1 Quick Extract (Simple Scripts)

Three standalone scripts for straightforward data generation:

| Script | Source | Examples | Time |
|--------|--------|----------|------|
| `convert_mtg_data.py` | MTGJSON (AtomicCards/AllPrintings) | 1K-10K | 1-2 min |
| `convert_edhrec_data.py` | EDHREC JSON API | 300-2K | 1-5 min |
| `convert_curated_mtg.py` | Hand-curated | 30-50 | Instant |

**Usage:**
```bash
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 3000 --output mtg_cards.jsonl
python convert_edhrec_data.py --num-commanders 50 --output edhrec_strategy.jsonl
python convert_curated_mtg.py --output curated_knowledge.jsonl
```
**Combine:** `cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > complete_mtg.jsonl`

### 3.2 Synthetic Data Generation Suite (`generate_synthetic_data/`)

**31 specialized generators** for comprehensive MTG knowledge coverage:

| Generator | Category | Output |
|-----------|----------|--------|
| `generate_archetypes.py` | Deck archetypes | Tempo, control, aggro, combo, midrange descriptions |
| `generate_article_qa.py` | Articles | FAQ-style Q&A from MTG articles |
| `generate_budget_alternatives.py` | Budget | Affordable alternatives to expensive cards |
| `generate_card_search_queries.py` | Search | Natural language card search queries |
| `generate_color_identity_questions.py` | Colors | Color identity for Commander legality |
| `generate_color_staples.py` | Staples | Best cards per color per format |
| `generate_combo_queries.py` | Combos | Combo interactions and win conditions (targets 5000) |
| `generate_commander_building.py` | Commander | Deck building advice per commander |
| `generate_commander_knowledge.py` | Commander | Commander rules, history, mechanics |
| `generate_comparison_questions.py` | Comparisons | Card vs card comparisons |
| `generate_deckbuilding_theory.py` | Theory | Mana curves, card advantage, resource management |
| `generate_game_theory.py` | Strategy | Game theory, probability, decision trees |
| `generate_glossary_with_examples.py` | Glossary | MTG terminology with examples |
| `generate_guide_qa.py` | Guides | Beginner/intermediate/advanced guides |
| `generate_meta_knowledge.py` | Meta | Metagame analysis, format health |
| `generate_multi_card_usage.py` | Multi-card | Cards that interact with each other |
| `generate_quick_guidelines.py` | Guidelines | Quick rules/tips |
| `generate_reverse_lookup_questions.py` | Lookup | "Which cards have [ability]?" |
| `generate_rule_edge_cases.py` | Rules | Edge cases, corner cases (targets 5000) |
| `generate_rule_explanations.py` | Rules | Core rules explained |
| `generate_rule_interactions.py` | Rules | Rules interactions between cards (targets 5000) |
| `generate_rule_why_questions.py` | Rules | "Why does this rule exist?" |
| `generate_rules_scenarios.py` | Rules | Scenario-based rule applications |
| `generate_salt_questions.py` | Salt | Common pain points, rules frustrations |
| `generate_staple_analysis.py` | Staples | Why cards are staples in competitive play |
| `generate_synergy_questions.py` | Synergy | Card synergies and combos |
| `generate_terminology_questions.py` | Terminology | MTG terminology |

**Generator architecture:** Each generator class takes MongoDB collections, Scryfall client, model configs, and a `save_item` callback. Uses `rich` for progress/status output.

**Model providers supported:**
- **Ollama** (local, `ollama` Python library) — Default, used by `main.py`. Models specified as `"ollama,qwen:14b"` format.
- **Anthropic Claude** (streaming API) — Used by `query_model.py`. Uses `Anthropic.messages.stream()` with 1s rate limit delay.
- **OpenAI GPT** (API) — Used by `generate_with_api.py`. Set `USE_OPENAI = True/False`.

**Model class (`models.py`):**
```python
class QuestionAnswerEnhanced:
    question, answer, category, source_data, validated, validation_score
    needs_review, suggested_fix, content_hash, generated_at, version
```

**MongoDB schema for synthetic queries:**
```json
{
  "question": "What combos can I do with Pitiless Plunderer?",
  "answer": "Pitiless Plunderer combos with...",
  "category": "combo_query",
  "source_data": ["pitiless_plunderer"],
  "validated": true,
  "needs_review": false,
  "generated_at": "2026-02-13T..."
}
```

**Validation flow:** Each generator produces candidate Q&A, scores them against `VALIDATION_SCORING_GUIDE` in `constants.py`, loops with suggested fixes via `validate_and_loop_with_suggested_fix()`. Output goes to `synthetic_queries.queries` collection.

**Run via:** `python generate_synthetic_data/main.py --source all` or `bash generate_synthetic_data/run_combos.sh`

**`common.py` key functions (910 lines):**
- `build_commander_prompt()` — Commander rules with MTG notation guide
- `build_multi_card_usage_prompt(card1, card2, description)` — Multi-card interaction prompts
- `build_card_detail(card)` — Extract card details for prompts
- `validate_and_loop_with_suggested_fix()` — Retry loop for failed validations
- `MTG_NOTATION_LEGEND` — Mana symbol notation reference

**`scryfall_mongodb.py` key features (814 lines):**
- Custom Scryfall query parser: tokenizes `t:creature`, `cmc<=3`, `o:"trample"`, `!Lightning Bolt`
- Supports parentheses grouping, AND/OR/NOT operators
- Syncs search results to MongoDB for generator use

### 3.3 API-Based Generation (`generate_with_api.py`, 215 lines)

Uses OpenAI or Anthropic Claude for highest quality strategic content:

```python
USE_OPENAI = True  # or False for Anthropic

# Categories covered:
# - Mechanics explanations (stack, combat, lifelink, trample, ward)
# - Strategic concepts (card advantage, tempo, graveyard hate, ramp, board wipes)
# - Specific popular cards (Lightning Bolt, Counterspell, fetch lands, Sol Ring)
# - Format explanations (Modern, Commander, Legacy, Standard, Pauper)
# - Budget alternatives
```

### 3.4 MongoDB Integration

**Purpose:** Centralized storage for all MTG data sources, enabling scalable extraction and dataset balancing.

**Collections (from `import_rules_to_mongo.py` and `scryfall_mongodb.py`):**
| Collection | Source | Description |
|------------|--------|-------------|
| `cards` | MTGJSON/Scryfall | Card database with legalities, colors, mana cost |
| `combos` | Curated/manual | Combo interactions between cards |
| `rules` | Comprehensive rules TXT | Structured by rule number (100.1, 200.1, etc.) |
| `glossary` | Rules file | MTG terminology definitions |
| `strategic` | EDHREC, articles | Strategy content |
| `articles` | MTG articles | FAQ-style Q&A |
| `synthetic_queries.queries` | LLM generation | Synthetic Q&A from Ollama/Anthropic/OpenAI |
| `commanders` | EDHREC | Commander-specific data (popular cards, synergies) |

**MongoDB setup (`mongodb.compose.yml`):**
```yaml
services:
  mongodb:
    image: mongo
    ports: ["27017:27017"]
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: password
```

**Connect:**
```python
from pymongo import MongoClient
client = MongoClient("mongodb://admin:password@localhost:27017/", authSource='admin')
db = client['mtg_database']
```

**`import_rules_to_mongo.py` (542 lines):**
- Parses MTG comprehensive rules TXT file
- Extracts metadata (effective date)
- Finds rules section (starts at `100.1`) and glossary section
- Stores rules by number, glossary terms separately
- Handles multi-level rule hierarchy (100 → 101 → 101.1)

### 3.5 Configurable Extraction from MongoDB (`extract_training_data.py`)

**1069-line script** with full control over dataset composition:

**Presets:**
| Preset | Total Examples | Cards | Training Time | Quality |
|--------|---------------|-------|---------------|---------|
| `quick` | 50,000 | 2,000 | ~4 hours | 93-95% |
| `balanced` | 155,000 | 5,000 | ~37 hours | 96-97% (recommended) |
| `comprehensive` | 615,000 | 10,000 | ~185 hours | Max |
| `card-master` | 400,000 | 8,000 | ~120 hours | Card-focused |

**Tier system:**
| Tier | Cards | Examples per Card | Description |
|------|-------|-------------------|-------------|
| Tier 1 | 800-6000 | 15-30 | Most popular/playable cards |
| Tier 2 | 800-3000 | 10-20 | Commonly played cards |
| Tier 3 | 400-1000 | 5-15 | Niche/specialty cards |

**Source distribution:**
| Source | Quick | Balanced | Comprehensive |
|--------|-------|----------|---------------|
| Cards | 60% | 48% | 49% |
| Combos | 20% | 20% | 16% |
| Rules | 15% | 20% | 17% |
| Articles | 5% | 7% | 10% |
| Strategic | 0% | 3% | 6% |
| Synthetic | 0% | 2% | 2% |

**Usage:**
```bash
python extract_training_data.py --preset balanced
# Or custom:
python extract_training_data.py \
  --total 300000 --cards 8000 --examples-per-card 25 \
  --card-pct 50 --combo-pct 20 --rules-pct 20 --articles-pct 8 --strategic-pct 2
```

### 3.6 Data Quality Utilities

| Script | Purpose | Key Logic |
|--------|---------|-----------|
| `analyze_card_frequency.py` | Identify low-exposure cards needing more examples | Regex extraction of card names from Q&A pairs using 6+ patterns |
| `balance_dataset.py` | Merge card database with strategic data | Configurable ratios: 40% cards, 30% mechanics, 20% strategy, 10% format |
| `dedup_synthetic_queries.py` | Remove duplicate (question, answer) pairs | MongoDB aggregation pipeline: `$group` by (question, answer), `$min` ObjectId to keep oldest |
| `check_jsonl.py` | Validate JSONL format | Checks `messages` key exists, is non-empty list, each msg has `role`+`content`, role is user/assistant |
| `inspect_mongodb.py` | Explore database | Lists collections with counts, samples documents, schema analysis on first 1000 docs, key frequency |

---

## 4. Model Sizing & Hardware Requirements

### 4.1 Model Comparison (Updated for 32GB GPU)

| Model | Params | 4-bit Memory | 4-bit+LoRA | 4-bit+LoRA+GaLore | Training Time (50K ex) | Training Time (155K ex) |
|-------|--------|-------------|------------|--------------------|------------------------|-------------------------|
| Qwen2.5-0.5B | 0.5B | ~2GB | ~2.5GB | N/A | ~8 hours | ~20 hours |
| Qwen2.5-1.5B | 1.5B | ~3-4GB | ~4GB | N/A | ~12 hours | ~30 hours |
| Qwen2.5-3B | 3B | ~6GB | ~7GB | Optional | ~20 hours | ~50 hours |
| **Qwen2.5-7B** | **7B** | **~5-6GB** | **~7GB** | **~6-7GB** | **~48 hours** | **~120 hours** |
| **Qwen3-8B** | **8B** | **~6GB** | **~7GB** | **~6-7GB** | **~60 hours** | **~150 hours** |
| Qwen14B | 14B | ~9-10GB | ~11GB | ~9-10GB | ~100 hours | ~300 hours |

**With 32GB GPU:** All models fit comfortably. 14B is viable without GaLore if needed for speed.

### 4.2 Hardware Detection (`detect_device()` in finetune_qwen.py)

```python
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    device = 'xpu'          # Intel Arc (primary target)
elif torch.cuda.is_available():
    device = 'cuda'         # NVIDIA GPU
else:
    device = 'cpu'          # Falls back (VERY slow)
```

**PyTorch XPU index** configured in `pyproject.toml`:
```toml
[[tool.uv.index]]
name = "pytorch-nightly-xpu"
url = "https://download.pytorch.org/whl/nightly/xpu"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-nightly-xpu" }
torchvision = { index = "pytorch-nightly-xpu" }
torchaudio = { index = "pytorch-nightly-xpu" }
```

### 4.3 Memory Optimization Progression

**OOM? Apply in order:**
1. `--use-4bit` (saves ~75% model memory)
2. `--use-galore` + `--batch-size 2` (saves ~60-70% optimizer memory)
3. Reduce `--max-seq-length` (384 → 256, saves ~30% sequence memory)
4. Reduce `--lora-r` (32 → 24 → 16, saves ~10% adapter memory)
5. Reduce `--galore-rank` (128 → 64, saves ~10% GaLore overhead)

### 4.4 LoRA Configuration by Model Size

| Model Size | LoRA r | LoRA alpha | GaLore Needed? | Memory (4-bit) |
|------------|--------|------------|----------------|----------------|
| 0.5B-1B | 16 | 32 | No | ~2-3GB |
| 1.5B-3B | 24 | 48 | Optional | ~4-7GB |
| 7B-8B | 32-64 | 64-128 | **Required** | ~6-7GB |
| 14B+ | 64-128 | 128-256 | Recommended | ~10-12GB |

### 4.5 Learning Rate by Model Size

| Model Size | Learning Rate |
|------------|--------------|
| 0.5B-1B | 2e-4 |
| 1.5B-3B | 1e-4 |
| 7B-8B | 1e-4 to 2e-4 |
| 14B+ | 5e-5 to 1e-4 |

---

## 5. Complete Workflow Examples

### 5.1 Quick Test (5 minutes)

```bash
# Generate small dataset
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 500 --output test.jsonl

# Train 0.5B model
python finetune_qwen.py --dataset file --data-file test.jsonl --epochs 2 --output-dir ./qwen-test

# Or use built-in sample:
python finetune_qwen.py --dataset sample --epochs 1
```

### 5.2 Standard MTG Expert (30GB+ GPU, 1-2 hours)

```bash
# Generate all three data sources
python convert_mtg_data.py --data-file AllPrintings.json --num-examples 3000 --output mtg_cards.jsonl
python convert_edhrec_data.py --num-commanders 50 --output edhrec_strategy.jsonl
python convert_curated_mtg.py --output curated_knowledge.jsonl

# Combine
cat mtg_cards.jsonl edhrec_strategy.jsonl curated_knowledge.jsonl > complete_mtg.jsonl

# Train
python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-7B-Instruct \
  --dataset file \
  --data-file complete_mtg.jsonl \
  --use-4bit \
  --lora-r 32 --lora-alpha 64 \
  --batch-size 4 \
  --gradient-accumulation 4 \
  --epochs 3 \
  --max-seq-length 2048 \
  --learning-rate 2e-4 \
  --output-dir ./qwen-mtg-expert

# Merge and export
python merge_model.py  # Update model_name path first
```

### 5.3 Production-Quality with MongoDB Data (32GB GPU)

```bash
# 1. Extract comprehensive dataset from MongoDB
python extract_training_data.py --preset balanced

# 2. Verify data
python check_jsonl.py training_data/data/extracted_mtg_data.jsonl

# 3. (Optional) Analyze card coverage
python analyze_card_frequency.py --data-file training_data/data/extracted_mtg_data.jsonl

# 4. Train 8B model with GaLore
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --dataset file \
  --data-file training_data/data/extracted_mtg_data.jsonl \
  --use-4bit \
  --use-galore \
  --galore-rank 128 \
  --galore-update-proj-gap 200 \
  --galore-scale 0.25 \
  --lora-r 32 --lora-alpha 64 \
  --batch-size 2 \
  --gradient-accumulation 8 \
  --epochs 3 \
  --max-seq-length 2048 \
  --learning-rate 1e-4 \
  --output-dir ./qwen3-8b-mtg-production

# 5. Merge
python merge_model.py
```

### 5.4 Resuming Training (for multi-day runs)

```bash
# Check what checkpoints exist
ls ./output/
# → checkpoint-1000, checkpoint-2000, ... checkpoint-5000

# Resume from last checkpoint
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --dataset file \
  --data-file complete_mtg.jsonl \
  --use-4bit \
  --use-galore \
  --resume-from-checkpoint ./output/checkpoint-5000 \
  --output-dir ./qwen3-8b-mtg-production
  # ... all other args must match original ...
```

**CRITICAL:** All args must match the original training run when resuming. The script reconstructs the same configuration from CLI args.

### 5.5 Synthetic Data Pipeline (Advanced)

```bash
# 1. Start MongoDB
docker-compose -f mongodb.compose.yml up -d

# 2. Import rules
python import_rules_to_mongo.py /path/to/comprehensive_rules.txt

# 3. Generate synthetic queries (uses Ollama Qwen 14B locally)
python generate_synthetic_data/main.py --source all

# 4. Run specific generators
bash generate_synthetic_data/run_combos.sh
bash generate_synthetic_data/run_rules.sh

# 5. Deduplicate
python dedup_synthetic_queries.py --uri mongodb://admin:password@localhost:27017/

# 6. Extract combined dataset
python extract_training_data.py --preset comprehensive

# 7. Balance if needed
python balance_dataset.py mtg_cards.jsonl strategic_data.jsonl balanced.jsonl
```

---

## 6. Deployment Options

### 6.1 Unsloth (Recommended — Fastest Inference)

```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="./output-7b-mtg-unsloth",
    dtype=None,
    load_in_4bit=True,
    device_map="balanced"
)

# Inference
FastLanguageModel.for_inference(model)
messages = [{"role": "user", "content": "What does deathtouch do?"}]
text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(text, return_tensors="pt").to("xpu")
outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.7)
response = tokenizer.decode(outputs[0], skip_special_tokens=True)
```

### 6.2 Standard Transformers + PEFT

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    device_map="auto",
    torch_dtype=torch.bfloat16
)
model = PeftModel.from_pretrained(base_model, "./output-7b-mtg-unsloth")
tokenizer = AutoTokenizer.from_pretrained("./output-7b-mtg-unsloth")
```

### 6.3 GGUF / llama.cpp (Quantized, CPU/GPU)

```bash
# Exported via merge_model.py
python merge_model.py  # Creates output-7b-mtg-unsloth-merged-gguf/

# Use with llama.cpp
llama-cli -m output-7b-mtg-unsloth-merged-gguf/model-q5_k_m.gguf \
  -p "User: What does deathtouch do?\nAssistant:" \
  -n 256
```

---

## 7. Configuration Reference

### 7.1 `finetune_qwen.py` — All CLI Arguments

```
--dataset {sample,hf,file}    Dataset source (default: sample)
--hf-dataset NAME             HF dataset name (default: yahma/alpaca-cleaned)
--data-file PATH              JSONL file path (when --dataset=file)

--model-name NAME             Base model (default: Qwen/Qwen2.5-0.5B-Instruct)
--hf-token TOKEN              HuggingFace token for gated models
--output-dir PATH             Output directory (default: ./qwen-finetuned)

--lora-r INT                  LoRA rank (default: 16, range: 8-64)
--lora-alpha INT              LoRA alpha (default: 32, typically 2x rank)
--lora-dropout FLOAT          LoRA dropout (default: 0)

--use-galore                  Enable GaLore optimizer (required for 7B+)
--galore-rank INT             GaLore projection rank (default: 128)
--galore-update-proj-gap INT  GaLore update frequency (default: 200 steps)
--galore-scale FLOAT          GaLore scaling factor (default: 0.25)

--epochs INT                  Training epochs (default: 3)
--batch-size INT              Batch size per device (default: 4)
--gradient-accumulation INT   Gradient accumulation steps (default: 4)
--learning-rate FLOAT         Learning rate (default: 2e-4)
--max-seq-length INT          Max sequence length (default: 512)

--use-4bit                    4-bit quantization (recommended for large models)
--no-test                     Skip test generation after training
--resume-from-checkpoint PATH Resume from checkpoint directory
```

### 7.2 `extract_training_data.py` — All CLI Arguments

```
--preset {quick,balanced,comprehensive,card-master}  Preset config
--total INT                Total examples desired
--cards INT                Number of unique cards (tier1+tier2+tier3)
--examples-per-card INT    Default examples per card
--tier1-cards INT          Tier 1 card count
--tier2-cards INT          Tier 2 card count
--tier3-cards INT          Tier 3 card count
--tier1-examples INT       Examples per tier 1 card
--tier2-examples INT       Examples per tier 2 card
--tier3-examples INT       Examples per tier 3 card
--card-pct INT             Cards source percentage
--combo-pct INT            Combos source percentage
--rules-pct INT            Rules source percentage
--articles-pct INT         Articles source percentage
--strategic-pct INT        Strategic source percentage
--synthetic-pct INT        Synthetic source percentage
```

### 7.3 `pyproject.toml` — Project Configuration

```toml
[project]
name = "qwen-finetuning"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "torch",
    "torchaudio",
    "torchvision",
]

[project.optional-dependencies]
logging = [
    "wandb",
    "tensorboard",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# PyTorch nightly XPU index for Intel Arc GPUs
[[tool.uv.index]]
name = "pytorch-nightly-xpu"
url = "https://download.pytorch.org/whl/nightly/xpu"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-nightly-xpu" }
torchvision = { index = "pytorch-nightly-xpu" }
torchaudio = { index = "pytorch-nightly-xpu" }
```

---

## 8. Training Data Schema

### 8.1 JSONL Format (Input to `finetune_qwen.py`)

Each line is a JSON object with a `messages` array:

```json
{"messages": [
  {"role": "user", "content": "What does Lightning Bolt do?"},
  {"role": "assistant", "content": "Lightning Bolt deals 3 damage to any target."}
]}
```

**Validation rules (enforced by `check_jsonl.py`):**
- Must have `messages` key
- `messages` must be a non-empty list
- Each message must have `role` and `content`
- `role` must be `"user"` or `"assistant"`

### 8.2 MongoDB Collection Schemas

**Cards collection:**
```json
{
  "_id": ObjectId,
  "name": "Lightning Bolt",
  "mana_cost": "{R}",
  "type": "Instant",
  "text": "Lightning Bolt deals 3 damage to any target.",
  "colors": ["R"],
  "power": null,
  "toughness": null,
  "legalities": {"commander": "legal", "modern": "legal"}
}
```

**Rules collection (structured by rule number):**
```json
{
  "_id": ObjectId,
  "rule_number": "100.1",
  "title": "Game Types",
  "text": "There are five types of games...",
  "parent": "100"
}
```

**Synthetic queries:**
```json
{
  "_id": ObjectId,
  "question": "What combos can I do with Pitiless Plunderer?",
  "answer": "Pitiless Plunderer combos with...",
  "category": "combo_query",
  "source_data": ["pitiless_plunderer"],
  "validated": true,
  "generated_at": "2026-02-13T12:00:00"
}
```

### 8.3 Synthetic Generator Prompt Templates

**`constants.py` key values:**
- `MTG_NOTATION_LEGEND` — Mana symbol reference (e.g., `{R}` = red mana, `{2}` = generic 2)
- `SYSTEM_MESSAGE` — Role definition for LLM generation
- `VALIDATION_CHECKLIST` — Criteria for scoring Q&A quality
- `VALIDATION_SCORING_GUIDE` — Numeric scoring rubric for automated validation

**Example prompt from `generate_commander_prompt()`:**
```
{MTG_NOTATION_LEGEND}

Based on Commander rules:
- 100-card singleton deck
- One legendary creature commander
- Commander determines color identity
- Starting life: 40
- Commander tax: +{2} each time cast
- Commander damage: 21 from one commander kills

Generate 20 common Commander questions with accurate answers.
Output JSON array. Keep answers 2-3 sentences, accurate and concise.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings.
```

**Example prompt from `build_multi_card_usage_prompt(card1, card2, description)`:**
```
{MTG_NOTATION_LEGEND}

Generate 2 usage questions for: {card1} and {card2}
How they work: {description}
Output JSON with natural questions like "How do I use X with Y?"
Explain the mechanics and why the combo is effective.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings.
```

### 8.4 `models.py` — Data Classes

```python
class QuestionAnswer:
    question: str
    answer: str

class QuestionAnswerEnhanced(QuestionAnswer):
    category: str | None          # e.g., "combo_query", "rule_interaction"
    source_data: list[str] | None # Cards/rules referenced
    validated: bool               # Passed validation check
    validation_score: float | None
    needs_review: bool            # True if manual review needed
    suggested_fix: str | None     # LLM-suggested correction
    content_hash: str | None      # Deduplication hash
    generated_at: datetime | None
    version: int                  # Incremented on fix

class ModelType(Enum):
    GENERATION = "generation"
    VALIDATION = "validation"

class ModelProvider(Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

class Model:
    name: str                     # Parsed model name
    type: ModelType
    provider: ModelProvider
    provider_url: str             # Host for non-local providers
```

### 8.5 `scryfall_mongodb.py` — Query Parser

Supports Scryfall-like query syntax:
| Pattern | Example | Meaning |
|---------|---------|---------|
| `t:cardtype` | `t:creature` | Card type filter |
| `cmc<=N` | `cmc<=3` | Converted mana cost |
| `o:text` | `o:"trample"` | Oracle text search |
| `!name` | `!Lightning Bolt` | Exact card name match |
| `"phrase"` | `"hexproof"` | Quoted phrase |
| `(A OR B)` | `(t:creature OR t:enchantment)` | Grouped logic |
| `NOT x` | `NOT t:land` | Exclusion |
[project.optional-dependencies]
logging = ["wandb", "tensorboard"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# PyTorch nightly XPU index for Intel Arc GPUs
[[tool.uv.index]]
name = "pytorch-nightly-xpu"
url = "https://download.pytorch.org/whl/nightly/xpu"
explicit = true

[tool.uv.sources]
torch = { index = "pytorch-nightly-xpu" }
torchvision = { index = "pytorch-nightly-xpu" }
torchaudio = { index = "pytorch-nightly-xpu" }
```

