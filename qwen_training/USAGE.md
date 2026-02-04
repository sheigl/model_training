# Qwen Fine-tuning Script - Complete Usage Guide

## Table of Contents
- [Quick Start](#quick-start)
- [Understanding the Options](#understanding-the-options)
- [Dataset Options Explained](#dataset-options-explained)
- [LoRA Configuration Deep Dive](#lora-configuration-deep-dive)
- [Training Parameters Explained](#training-parameters-explained)
- [Memory Management](#memory-management)
- [Real-World Examples](#real-world-examples)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Simplest Possible Usage
```bash
# This uses built-in sample data and default settings
python finetune_qwen.py --dataset sample
```

That's it! This will:
- Use 100 sample Q&A pairs
- Train for 3 epochs
- Save to `./qwen-finetuned/`
- Show test generations at the end

### Your First Real Training
```bash
# Use a real dataset (52K instruction examples)
python finetune_qwen.py --dataset hf --hf-dataset yahma/alpaca-cleaned
```

This takes about 30-60 minutes on your Arc B580 and produces a genuinely useful instruction-following model!

---

## Understanding the Options

Every option in this script has a purpose. Let's understand what each one does and when to use it.

### The `--dataset` Option: Where Your Training Data Comes From

**What it does:** Tells the script where to get training examples.

**Three choices:**

#### 1. `--dataset sample` (Built-in test data)
```bash
python finetune_qwen.py --dataset sample
```

**What this is:** 100 simple Q&A pairs that come with the script (like "What is the capital of France?" → "Paris")

**When to use:**
- ✅ Testing your setup for the first time
- ✅ Making sure everything works before using real data
- ✅ Quick experiments (trains in ~5 minutes)
- ❌ Don't use for production - it's just demonstration data

**Example output:** Model learns to answer basic questions but has very limited knowledge since there are only 100 examples repeated.

#### 2. `--dataset hf` (Hugging Face datasets)
```bash
python finetune_qwen.py --dataset hf --hf-dataset yahma/alpaca-cleaned
```

**What this is:** Downloads instruction datasets from Hugging Face's repository. These are professionally curated datasets with thousands of examples.

**When to use:**
- ✅ You want a production-quality model
- ✅ You don't have your own data yet
- ✅ You want to learn general instruction-following
- ✅ You want diverse examples across many topics

**Popular datasets:**

| Dataset | Size | Description | Best For |
|---------|------|-------------|----------|
| `yahma/alpaca-cleaned` | 52K | General instructions, cleaned version | **Start here!** Good all-around dataset |
| `vicgalle/alpaca-gpt4` | 52K | GPT-4 generated, higher quality | Better responses, takes same time |
| `tatsu-lab/alpaca` | 52K | Original Alpaca, some noise | Historical reference |
| `Open-Orca/OpenOrca` | 1M+ | Massive dataset | Advanced users only |

**Example:**
```bash
# Good first choice - high quality, reasonable size
python finetune_qwen.py --dataset hf --hf-dataset vicgalle/alpaca-gpt4
```

#### 3. `--dataset file` (Your own custom data)
```bash
python finetune_qwen.py --dataset file --data-file my_custom_data.jsonl
```

**What this is:** Use your own instruction-response pairs that you've created or collected.

**When to use:**
- ✅ You have domain-specific knowledge (medical, legal, technical)
- ✅ You want a specific personality or tone
- ✅ You're building a specialized assistant
- ✅ You have proprietary data

**Data format required (JSONL):**

Each line is one JSON object with a "messages" array:

```json
{"messages": [{"role": "user", "content": "What is photosynthesis?"}, {"role": "assistant", "content": "Photosynthesis is the process by which plants convert sunlight into chemical energy..."}]}
```

**Creating your data file:**

```python
import json

# Your training examples
examples = [
    {
        "messages": [
            {"role": "user", "content": "How do I debug a Python function?"},
            {"role": "assistant", "content": "To debug a Python function, you can:\n1. Use print() statements\n2. Use Python's debugger (pdb)\n3. Use an IDE's debugging tools"}
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "Explain list comprehensions"},
            {"role": "assistant", "content": "List comprehensions are a concise way to create lists in Python. Syntax: [expression for item in iterable if condition]"}
        ]
    }
]

# Save to JSONL (JSON Lines format - one JSON per line)
with open('my_data.jsonl', 'w') as f:
    for example in examples:
        f.write(json.dumps(example) + '\n')
```

**Quality matters more than quantity:**
- 50 excellent examples > 500 mediocre examples
- Make sure responses are accurate
- Use natural, conversational language
- Cover the topics you care about

---

## LoRA Configuration Deep Dive

LoRA (Low-Rank Adaptation) is the technique that makes fine-tuning possible on consumer hardware. Understanding these parameters helps you get better results.

### `--lora-r` (The Rank)

**What it is:** Controls how many parameters are trainable. Higher rank = more capacity to learn.

**The math:** With r=16, you're training about 2M parameters instead of 500M. That's 0.4% of the model!

**How to choose:**

```bash
# Small dataset (< 100 examples) or simple task
python finetune_qwen.py --lora-r 8

# Medium dataset (100-1000 examples) - DEFAULT
python finetune_qwen.py --lora-r 16

# Large dataset (1000+ examples) or complex task
python finetune_qwen.py --lora-r 32

# Very large dataset or highly specialized task
python finetune_qwen.py --lora-r 64
```

**Trade-offs:**
- **Lower rank (8):**
  - ✅ Faster training
  - ✅ Less memory
  - ✅ Less likely to overfit on small data
  - ❌ May not capture complex patterns
  
- **Higher rank (32-64):**
  - ✅ Can learn more complex patterns
  - ✅ Better for large datasets
  - ✅ Better for specialized domains
  - ❌ Slower training
  - ❌ Uses more memory
  - ❌ Can overfit on small datasets

**Real example:**
If you're teaching the model your company's specific coding style with 200 examples, use r=16. If you're training on 10,000 medical Q&As, use r=32.

### `--lora-alpha` (The Scaling Factor)

**What it is:** Controls how much influence the LoRA adapter has compared to the base model.

**Rule of thumb:** Set to 2x your rank (this is the standard)

```bash
# If r=16, use alpha=32
python finetune_qwen.py --lora-r 16 --lora-alpha 32

# If r=32, use alpha=64
python finetune_qwen.py --lora-r 32 --lora-alpha 64
```

**When to adjust:**
- **Higher alpha (3x or 4x rank):** Your training data is very different from what the model knows
  - Example: Training on a very specific technical jargon or fictional language
- **Lower alpha (1x rank):** You want to make small adjustments without changing the model much
  - Example: Fine-tuning tone/style but keeping general knowledge

**Most people can ignore this and use the 2x rule.**

### `--lora-dropout` (Regularization)

**What it is:** Randomly "drops out" some connections during training to prevent overfitting.

**Default:** 0.05 (5% dropout)

```bash
# More dropout if you're overfitting
python finetune_qwen.py --lora-dropout 0.1

# Less dropout if you're underfitting
python finetune_qwen.py --lora-dropout 0.01
```

**How to tell if you need to adjust:**
- **Overfitting signs:**
  - Training loss keeps decreasing
  - Validation loss starts increasing or plateaus
  - Model gives great answers on training data, poor on new questions
  - **Solution:** Increase dropout to 0.1 or 0.15

- **Underfitting signs:**
  - Both training and validation loss stay high
  - Model responses are poor quality
  - **Solution:** Decrease dropout to 0.01 or increase LoRA rank

---

## Training Parameters Explained

### `--epochs` (How Many Times to See the Data)

**What it is:** Number of complete passes through your dataset.

**How to choose:**

```bash
# Small dataset (< 100 examples)
python finetune_qwen.py --epochs 5

# Medium dataset (100-1000 examples) - DEFAULT
python finetune_qwen.py --epochs 3

# Large dataset (5000+ examples)
python finetune_qwen.py --epochs 1
```

**The principle:** More data = fewer epochs needed.

**Why?** 
- 100 examples × 5 epochs = model sees 500 training instances
- 10,000 examples × 1 epoch = model sees 10,000 training instances

**Watch the validation loss:**
- If it keeps improving: You can train longer
- If it plateaus: You're done
- If it increases: You're overfitting, reduce epochs

**Time estimate (Arc B580):**
- Sample data (100 examples): ~2 min/epoch
- Alpaca (52K examples): ~20 min/epoch

### `--batch-size` (How Many Examples at Once)

**What it is:** Number of examples processed simultaneously on your GPU.

**Memory vs Speed trade-off:**

```bash
# Conservative (always works on Arc B580)
python finetune_qwen.py --batch-size 2

# Balanced - DEFAULT
python finetune_qwen.py --batch-size 4

# Aggressive (if you have memory)
python finetune_qwen.py --batch-size 8

# Maximum (might OOM)
python finetune_qwen.py --batch-size 16
```

**How to find your optimal batch size:**
1. Start with 4
2. If you get "out of memory" errors, reduce to 2
3. If training seems to have memory to spare, try 8
4. Keep increasing until you hit OOM, then back off

**Important:** The effective batch size is `batch-size × gradient-accumulation`

### `--gradient-accumulation` (Simulating Larger Batches)

**What it is:** Accumulates gradients over multiple small batches before updating weights.

**Why this matters:** It lets you simulate a large batch size without the memory cost.

```bash
# Effective batch size = 4 × 4 = 16 (DEFAULT)
python finetune_qwen.py --batch-size 4 --gradient-accumulation 4

# Want effective batch size of 32 but only have memory for batch-size 4?
python finetune_qwen.py --batch-size 4 --gradient-accumulation 8

# Or with smaller batches:
python finetune_qwen.py --batch-size 2 --gradient-accumulation 16
```

**General advice:**
- Keep effective batch size between 16-64
- If you get OOM: Reduce batch-size, increase gradient-accumulation to compensate
- If training is stable: Increase batch-size, decrease gradient-accumulation

**Example scenarios:**

| Your VRAM | batch-size | gradient-accumulation | Effective Batch |
|-----------|------------|----------------------|-----------------|
| Low (OOM errors) | 2 | 8 | 16 |
| Medium (Arc B580) | 4 | 4 | 16 |
| High (no issues) | 8 | 4 | 32 |

### `--learning-rate` (Step Size for Updates)

**What it is:** How big of a step to take when adjusting the model.

**Default:** 2e-4 (0.0002) - works for most cases

```bash
# Lower learning rate (more conservative)
python finetune_qwen.py --learning-rate 1e-4

# Default - good starting point
python finetune_qwen.py --learning-rate 2e-4

# Higher learning rate (more aggressive)
python finetune_qwen.py --learning-rate 5e-4
```

**When to adjust:**

**Use LOWER learning rate (1e-4 or 5e-5) when:**
- Your model's loss is unstable (jumping around)
- You're fine-tuning for a very specific task
- You want to make minimal changes to base model
- Training seems to "forget" general knowledge

**Use HIGHER learning rate (3e-4 or 5e-4) when:**
- Loss decreases too slowly
- You have a large dataset
- Your task is very different from the base model's training
- Training feels stuck

**Warning signs:**
- **Loss = NaN:** Learning rate is WAY too high, reduce by 10x
- **Loss not decreasing after 100 steps:** Try increasing learning rate by 2x
- **Loss oscillating wildly:** Reduce learning rate by 2x

### `--max-seq-length` (Maximum Context Length)

**What it is:** Maximum number of tokens (roughly words) in any training example.

**How to choose:**

```bash
# Short conversations (saves memory)
python finetune_qwen.py --max-seq-length 256

# Balanced - DEFAULT
python finetune_qwen.py --max-seq-length 512

# Longer context (uses more memory)
python finetune_qwen.py --max-seq-length 1024

# Maximum context (experimental, lots of memory)
python finetune_qwen.py --max-seq-length 2048
```

**Consider your data:**
- If most examples are short Q&As: 256-512 is fine
- If you have longer explanations: 1024
- If you have multi-turn conversations: 1024-2048

**Memory impact:** Doubling sequence length roughly doubles memory usage!

**Token counting tip:**
- 1 token ≈ 0.75 words (in English)
- 512 tokens ≈ 380 words
- "What is photosynthesis?" = ~5 tokens
- A paragraph = ~100 tokens

### `--use-4bit` (Memory Reduction) ✅ **CONFIRMED ON INTEL ARC B580**

**What it is:** Enables 4-bit quantization during training to reduce memory usage.

**Memory savings:** ~50-60% reduction in VRAM usage!

```bash
# Train with 4-bit quantization
python finetune_qwen.py --use-4bit

# Combine with other memory-saving options
python finetune_qwen.py \
  --use-4bit \
  --batch-size 4 \
  --max-seq-length 512 \
  --lora-r 32
```

**When to use:**
- ✅ You're hitting OOM errors
- ✅ Want to use larger batch sizes
- ✅ GPU has limited VRAM
- ✅ Want faster training with minimal quality loss

**Memory comparison:**

| Configuration | Normal | With --use-4bit |
|--------------|--------|-----------------|
| batch 4, seq 512, r32 | ~6-7GB | ~3-4GB |
| batch 2, seq 512, r32 | ~3-4GB | ~2GB |
| batch 4, seq 1024, r32 | ~12GB+ | ~6-7GB |

**Quality impact:** <1% difference in most tasks - minimal and acceptable!

**Tested on:** Intel Arc B580 with XPU drivers (confirmed working)

**Pro tip:** Enable this first before reducing other parameters. It's the easiest way to fit larger models in limited memory!

---

## Memory Management

Understanding memory usage helps you avoid "Out of Memory" (OOM) errors.

### What Uses Memory?

1. **Base model:** ~1GB (Qwen 0.5B in bfloat16)
2. **LoRA adapters:** Small (~10-50MB depending on rank)
3. **Batch size × sequence length:** This is the big one!
4. **Optimizer states:** Roughly 2x the trainable parameters

### Memory Usage Calculator

**Formula:** 
```
Memory ≈ 1GB (model) + batch_size × max_seq_length × 0.002GB
```

**Examples (Arc B580 has 12GB):**

| batch-size | max-seq-length | Est. Memory | Status |
|------------|----------------|-------------|---------|
| 4 | 512 | ~5GB | ✅ Safe |
| 8 | 512 | ~9GB | ✅ Should work |
| 4 | 1024 | ~9GB | ✅ Should work |
| 8 | 1024 | ~17GB | ❌ Will OOM |
| 16 | 512 | ~17GB | ❌ Will OOM |

### OOM? Try This Progression:

1. **First:** Reduce batch-size to 2, increase gradient-accumulation to 8
```bash
python finetune_qwen.py --batch-size 2 --gradient-accumulation 8
```

2. **Still OOM?** Reduce sequence length
```bash
python finetune_qwen.py --batch-size 2 --gradient-accumulation 8 --max-seq-length 256
```

3. **Still OOM?** Try 4-bit quantization (✅ **CONFIRMED WORKING ON INTEL ARC B580!**)
```bash
python finetune_qwen.py --batch-size 2 --gradient-accumulation 8 --use-4bit
```
**Memory savings:** ~50-60% reduction  
**Quality impact:** Minimal for most tasks  
**Tested on:** Intel Arc B580 with XPU drivers

4. **Still OOM?** Your data might have unusually long examples. Check your dataset.

### Using 4-Bit Quantization (Intel Arc B580)

**Good news:** 4-bit quantization works on Intel Arc B580 with XPU drivers!

**Enable it:**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --use-4bit \
  --output-dir ./model
```

**Benefits:**
- 🎯 **~50-60% memory reduction** (6GB → 2-3GB)
- 🚀 Allows larger batch sizes or longer sequences
- ✅ Minimal quality impact for most tasks
- ⚡ Slightly faster training

**Memory comparison:**

| Configuration | Without 4-bit | With 4-bit |
|--------------|---------------|------------|
| batch 4, seq 512, r32 | ~6-7GB | ~3-4GB |
| batch 2, seq 512, r32 | ~3-4GB | ~2GB |
| batch 4, seq 512, r24 | ~5GB | ~2.5-3GB |

**When to use 4-bit:**
- ✅ You're hitting OOM errors
- ✅ You want to use larger batch sizes
- ✅ Your GPU has limited VRAM (<8GB)
- ✅ You want faster training

**When NOT to use 4-bit:**
- ❌ You have plenty of VRAM and want maximum quality
- ❌ You're doing research where precision matters
- ❌ Your task requires extreme accuracy

**Combine with other settings:**
```bash
# Maximum memory efficiency
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --use-4bit \
  --batch-size 4 \
  --max-seq-length 512 \
  --lora-r 32 \
  --output-dir ./model
  
# This runs in ~3-4GB instead of ~6-7GB!
```

**Quality impact:** In practice, 4-bit quantization has minimal impact on final model quality for instruction following tasks. You may see <1% difference in performance, which is acceptable for most use cases.

**Note:** This was confirmed working by a user on Intel Arc B580 with XPU drivers. If you're on a different setup, test with a small dataset first.

---

## Real-World Examples

### Example 1: Customer Support Bot
**Goal:** Train a model to answer questions about your company's product

**Dataset:** 500 Q&As about your product

**Command:**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file customer_support.jsonl \
  --epochs 5 \
  --lora-r 16 \
  --batch-size 4 \
  --output-dir ./support-bot
```

**Why these settings:**
- 500 examples = medium dataset → r=16, epochs=5
- Standard batch size works fine
- Specific output dir for easy deployment

**Expected time:** ~15 minutes on Arc B580

### Example 2: Code Assistant
**Goal:** Model that helps with Python programming

**Dataset:** Use the Alpaca dataset (has lots of coding examples)

**Command:**
```bash
python finetune_qwen.py \
  --dataset hf \
  --hf-dataset yahma/alpaca-cleaned \
  --epochs 3 \
  --lora-r 32 \
  --lora-alpha 64 \
  --max-seq-length 1024 \
  --batch-size 4 \
  --output-dir ./code-assistant
```

**Why these settings:**
- 52K examples = large dataset → r=32
- Code often needs longer context → max-seq-length 1024
- Keep batch-size modest due to longer sequences

**Expected time:** ~60 minutes on Arc B580

### Example 3: Domain Expert (Medical)
**Goal:** Medical Q&A assistant

**Dataset:** Custom medical Q&As (1000 examples)

**Command:**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file medical_qa.jsonl \
  --epochs 4 \
  --lora-r 32 \
  --lora-dropout 0.1 \
  --learning-rate 1e-4 \
  --batch-size 4 \
  --output-dir ./medical-assistant
```

**Why these settings:**
- 1000 examples, specialized domain → r=32
- Higher dropout to prevent overfitting on medical jargon
- Lower learning rate to preserve general knowledge while learning domain
- 4 epochs for medium dataset

**Expected time:** ~25 minutes on Arc B580

### Example 4: Quick Personality Adjustment
**Goal:** Make the model friendlier and more casual

**Dataset:** 100 examples showing desired tone

**Command:**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file friendly_tone.jsonl \
  --epochs 8 \
  --lora-r 8 \
  --lora-alpha 16 \
  --learning-rate 3e-4 \
  --batch-size 8
```

**Why these settings:**
- Small dataset (100 examples) → r=8, many epochs
- Style adjustment → lower alpha (1:2 ratio)
- Higher learning rate for quick adaptation
- Can use larger batch since examples are short

**Expected time:** ~10 minutes on Arc B580

---

## Troubleshooting

### Training Issues

#### "CUDA/XPU out of memory"
**Symptoms:** Error message about memory, training crashes

**Solutions (try in order):**
1. Reduce batch size: `--batch-size 2`
2. Reduce sequence length: `--max-seq-length 256`
3. Increase gradient accumulation: `--gradient-accumulation 8`
4. Check for extremely long examples in your dataset

**Prevention:** Start conservative and increase gradually

#### "Loss is NaN" or "Loss explodes"
**Symptoms:** Loss shows as NaN or jumps to very high numbers

**Solutions:**
1. Reduce learning rate by 10x: `--learning-rate 2e-5`
2. Check your data for corrupted examples
3. Reduce batch size: `--batch-size 2`
4. Ensure data is properly formatted

#### "Loss not decreasing"
**Symptoms:** Loss stays flat or decreases very slowly

**Solutions:**
1. Increase learning rate: `--learning-rate 5e-4`
2. Increase LoRA rank: `--lora-r 32`
3. Train for more epochs: `--epochs 5`
4. Check that data is diverse and high-quality
5. Make sure GPU is being used (should say "Using Intel GPU (XPU)")

#### "Model overfitting"
**Symptoms:** Training loss decreases but validation loss increases

**Solutions:**
1. Reduce epochs: `--epochs 2`
2. Increase dropout: `--lora-dropout 0.1`
3. Get more diverse training data
4. Reduce LoRA rank: `--lora-r 8`

### Data Issues

#### "FileNotFoundError: data.jsonl"
**Problem:** Can't find your data file

**Solution:**
```bash
# Make sure file exists
ls my_data.jsonl

# Use full path if needed
python finetune_qwen.py --dataset file --data-file /full/path/to/my_data.jsonl
```

#### "JSONDecodeError"
**Problem:** Data file is not properly formatted

**Solution:** Check your JSONL format:
- Each line must be valid JSON
- Each line must have a "messages" field
- Use a JSON validator online

**Test your file:**
```python
import json

with open('my_data.jsonl', 'r') as f:
    for i, line in enumerate(f):
        try:
            data = json.loads(line)
            assert "messages" in data
        except Exception as e:
            print(f"Error on line {i+1}: {e}")
```

### Performance Issues

#### "Training is very slow"
**Symptoms:** Taking hours instead of minutes

**Checks:**
1. Verify GPU is being used:
   ```python
   import torch
   print(torch.xpu.is_available())  # Should be True
   ```
2. Check if you're accidentally using CPU
3. Reduce max-seq-length if examples are very long
4. Check system resources (RAM, not just VRAM)

#### "GPU not detected"
**Symptoms:** Says "Using CPU" instead of "Using Intel GPU (XPU)"

**Solutions:**
1. Check PyTorch installation:
   ```python
   import torch
   print(torch.__version__)
   print(torch.xpu.is_available())
   ```
2. Reinstall PyTorch with XPU support:
   ```bash
   pip install --pre torch --index-url https://download.pytorch.org/whl/nightly/xpu
   ```
3. Check Intel GPU drivers are installed

---

## Understanding Checkpoints

### What Are Checkpoints?

During training, the script automatically saves **checkpoints** - snapshots of your model at regular intervals:

```
qwen-mtg-expert/
├── checkpoint-100/     # After 100 training steps
├── checkpoint-200/     # After 200 training steps
├── checkpoint-300/     # After 300 training steps
├── ...
└── checkpoint-657/     # Final checkpoint
```

### Why Multiple Checkpoints?

1. **Safety Net**: If training crashes, you don't lose everything
2. **Find Best Model**: Sometimes an earlier checkpoint performs better
3. **Resume Training**: Continue from any checkpoint if needed

### What's Inside Each Checkpoint?

```
checkpoint-100/
├── adapter_model.safetensors    # LoRA weights (~50MB) ⭐ IMPORTANT
├── adapter_config.json          # LoRA configuration ⭐ IMPORTANT
├── optimizer.pt                 # Optimizer state (~100-200MB)
├── rng_state.pth               # Random number state
├── scheduler.pt                # Learning rate scheduler
├── trainer_state.json          # Training progress
└── training_args.bin           # Training arguments
```

**The essential files:** `adapter_model.safetensors` and `adapter_config.json`

### How Training Steps Work

**Example calculation:**
```
Dataset: 3,500 examples
Batch size: 2
Gradient accumulation: 8
Epochs: 3

Examples per step = 2 × 8 = 16
Steps per epoch = 3,500 / 16 = 219 steps
Total steps = 219 × 3 = 657 steps

Checkpoints (saved every 100 steps by default):
- checkpoint-100  (Epoch 1, 46% complete)
- checkpoint-200  (Epoch 1, 91% complete)
- checkpoint-300  (Epoch 2, 37% complete)
- checkpoint-400  (Epoch 2, 83% complete)
- checkpoint-500  (Epoch 3, 28% complete)
- checkpoint-600  (Epoch 3, 74% complete)
- checkpoint-657  (Final, 100% complete)
```

### Which Checkpoint Should You Use?

**Default: Use the last checkpoint**
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

base_model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
model = PeftModel.from_pretrained(base_model, "./qwen-mtg-expert")
# Automatically loads the latest checkpoint
```

**Specify a checkpoint:**
```python
# Load a specific checkpoint
model = PeftModel.from_pretrained(base_model, "./qwen-mtg-expert/checkpoint-400")
```

**When to use an earlier checkpoint:**
- Final model seems overtrained
- Earlier checkpoint gives better answers on test questions
- Training loss decreased but answer quality got worse (overfitting)

### Controlling Checkpoint Behavior

**Save checkpoints less frequently (default is every 100 steps):**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --save-steps 200 \
  --output-dir ./model
```

**Keep only the last N checkpoints (saves disk space):**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --save-total-limit 2 \
  --output-dir ./model
```

**Only save at the end of each epoch:**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --save-strategy "epoch" \
  --output-dir ./model
```

### Resuming Training from a Checkpoint

```bash
# Continue training from checkpoint-400
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --resume-from-checkpoint ./model/checkpoint-400 \
  --epochs 5 \
  --output-dir ./model-continued
```

### Cleaning Up Checkpoints

**After training completes, you can save disk space:**

**Option 1: Keep only the final checkpoint**
```bash
# Delete intermediate checkpoints
cd qwen-mtg-expert
rm -rf checkpoint-{100,200,300,400,500,600}
# Keep only checkpoint-657 (or whatever the final one is)
```

**Option 2: Delete training-only files from each checkpoint**
```bash
# In each checkpoint, keep only:
# - adapter_model.safetensors (your trained model)
# - adapter_config.json (model configuration)
#
# Delete (only needed to resume training):
# - optimizer.pt
# - scheduler.pt
# - rng_state.pth
# - trainer_state.json
# - training_args.bin

cd checkpoint-657
rm optimizer.pt scheduler.pt rng_state.pth trainer_state.json training_args.bin
```

**Space savings:**
- Full checkpoint: ~160-260MB each
- Cleaned checkpoint: ~50MB each
- Final model only: ~50MB total

### Testing Multiple Checkpoints

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-0.5B-Instruct",
    device_map="auto",
    torch_dtype=torch.bfloat16
)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")

def test_checkpoint(ckpt_path, question):
    """Test a checkpoint with a question"""
    model = PeftModel.from_pretrained(base_model, ckpt_path)
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=150)
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    return response

# Test different checkpoints
checkpoints = ["checkpoint-200", "checkpoint-400", "checkpoint-600", "checkpoint-657"]
test_question = "What does Lightning Bolt do?"

for ckpt in checkpoints:
    print(f"\n{'='*60}")
    print(f"{ckpt}:")
    print(test_checkpoint(f"./qwen-mtg-expert/{ckpt}", test_question))
```

### Signs of Overfitting

Monitor answer quality across checkpoints:

**Good progression (no overfitting):**
```
checkpoint-100: Basic answers, still learning
checkpoint-300: Good answers, getting better
checkpoint-500: Excellent, accurate answers
checkpoint-657: Excellent, accurate answers ✓
```

**Overfitting detected:**
```
checkpoint-100: Basic answers
checkpoint-300: Good answers
checkpoint-500: Excellent answers ⭐ BEST CHECKPOINT
checkpoint-657: Worse than 500, too specific, hallucinations
```

**If overfitting occurs:** Use an earlier checkpoint (like checkpoint-500 in this example)

### Checkpoint Configuration Options

You can add these to your training command:

| Option | Default | Description |
|--------|---------|-------------|
| `--save-steps N` | 100 | Save checkpoint every N steps |
| `--save-total-limit N` | None | Keep only last N checkpoints |
| `--save-strategy "X"` | "steps" | "steps", "epoch", or "no" |
| `--load-best-model-at-end` | False | Load best checkpoint at end |
| `--metric-for-best-model "X"` | "loss" | Metric to determine best |

**Example with all options:**
```bash
python finetune_qwen.py \
  --dataset file \
  --data-file data.jsonl \
  --save-steps 200 \
  --save-total-limit 3 \
  --load-best-model-at-end \
  --output-dir ./model
```

### Checkpoint Summary

| Aspect | Details |
|--------|---------|
| **Frequency** | Every 100 steps (default), configurable |
| **Size** | ~160-260MB each (full), ~50MB (cleaned) |
| **Purpose** | Safety, resume training, find best model |
| **Recommended** | Keep final + delete optimizer files |
| **Use** | Load with `PeftModel.from_pretrained(base, checkpoint_path)` |
| **Delete** | Intermediate checkpoints after confirming final works |

**Pro Tip:** After training completes and you've verified the model works, keep only the final checkpoint's `adapter_model.safetensors` and `adapter_config.json` files. This reduces storage from ~1.5GB to ~50MB!

---

## Getting Help

```bash
# See all options
python finetune_qwen.py --help

# See what datasets are available on Hugging Face
# Visit: https://huggingface.co/datasets

# Test your setup first
python finetune_qwen.py --dataset sample --epochs 1 --no-test
```

---

## Quick Reference Table

| Use Case | Dataset | epochs | lora-r | batch-size | 4-bit | Memory | Time (B580) |
|----------|---------|--------|--------|------------|-------|--------|-------------|
| Test setup | sample | 1 | 8 | 4 | No | ~2GB | 2 min |
| Small dataset | file | 5 | 8 | 4 | No | ~3GB | 10 min |
| Medium dataset | file | 3 | 16 | 4 | No | ~4GB | 20 min |
| Large dataset (HF) | hf | 3 | 32 | 4 | No | ~6GB | 60 min |
| **Large + Low Memory** | **hf** | **3** | **32** | **4** | **Yes** | **~3GB** | **55 min** |
| Style adjustment | file | 8 | 8 | 8 | No | ~4GB | 10 min |
| Domain expert | file | 4 | 32 | 4 | No | ~5GB | 30 min |
| **Domain expert + Low Memory** | **file** | **4** | **32** | **4** | **Yes** | **~2.5GB** | **28 min** |
| Max quality | hf | 3 | 64 | 4 | No | ~8GB | 90 min |

**New! 4-bit quantization confirmed working on Intel Arc B580** - Add `--use-4bit` to any command to cut memory usage in half!

Remember: These are starting points. Monitor your validation loss and adjust!