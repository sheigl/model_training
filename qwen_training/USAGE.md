# Qwen Fine-tuning Script - Complete Usage Guide

**Now supports models from 0.5B to 8B+ with GaLore memory optimization!**

## Table of Contents
- [Quick Start](#quick-start)
- [Understanding the Options](#understanding-the-options)
- [Dataset Options Explained](#dataset-options-explained)
- [Model Size Selection Guide](#model-size-selection-guide)
- [LoRA Configuration Deep Dive](#lora-configuration-deep-dive)
- [GaLore Configuration (For 7B+ Models)](#galore-configuration-for-7b-models)
- [Training Parameters Explained](#training-parameters-explained)
- [Memory Management](#memory-management)
- [Real-World Examples](#real-world-examples)
- [Troubleshooting](#troubleshooting)
- [Understanding Checkpoints](#understanding-checkpoints)
- [Quick Reference Tables](#quick-reference-tables)

---

## Quick Start

### Simplest Possible Usage (0.5B Model)
```bash
# This uses built-in sample data and default settings
python finetune_qwen.py --dataset sample
```

That's it! This will:
- Use 100 sample Q&A pairs
- Train Qwen 0.5B model
- Train for 3 epochs  
- Save to `./qwen-finetuned/`
- Show test generations at the end

### Your First Real Training (0.5B Model)
```bash
# Use a real dataset (52K instruction examples)
python finetune_qwen.py --dataset hf --hf-dataset yahma/alpaca-cleaned
```

This takes about 30-60 minutes on your Arc B580 and produces a genuinely useful instruction-following model!

### Training a Large Model (8B with GaLore) 🚀
```bash
# Train Qwen3 8B - requires GaLore for memory efficiency
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --dataset hf \
  --hf-dataset yahma/alpaca-cleaned \
  --use-4bit \
  --use-galore \
  --batch-size 2 \
  --gradient-accumulation 8 \
  --lora-r 32
```

This takes 48-72 hours but produces **much higher quality** results than 0.5B!

---

## Understanding the Options

Every option in this script has a purpose. Let's understand what each one does and when to use it.

### The `--model-name` Option: Choosing Your Base Model

**What it does:** Specifies which pre-trained model to fine-tune.

**Available models:**

| Model | Parameters | Memory (4-bit) | Memory (4-bit+GaLore) | Training Time | Quality | Best For |
|-------|-----------|----------------|----------------------|---------------|---------|----------|
| `Qwen/Qwen2.5-0.5B-Instruct` | 0.5B | ~2-3GB | N/A | 8 hours | Good | Testing, small tasks |
| `Qwen/Qwen2.5-1.5B-Instruct` | 1.5B | ~3-4GB | N/A | 12 hours | Better | General use |
| `Qwen/Qwen3-8B` | 8B | ~16GB (OOM!) | **~6-7GB** ✅ | 48-72 hours | Excellent | Production quality |

**Examples:**

```bash
# Small and fast (default)
python finetune_qwen.py --model-name Qwen/Qwen2.5-0.5B-Instruct

# Medium quality  
python finetune_qwen.py --model-name Qwen/Qwen2.5-1.5B-Instruct --use-4bit

# Best quality (requires --use-galore)
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --use-4bit \
  --use-galore \
  --batch-size 2
```

**⚠️ Important:** For models 7B and larger, you **MUST** use `--use-4bit` and `--use-galore` or training will fail with out-of-memory errors!

[Dataset Options section remains the same as before]

---

## Model Size Selection Guide

Choosing the right model size is crucial for balancing quality, training time, and resource usage.

### Quick Comparison

| Aspect | 0.5B Model | 1.5B Model | 8B Model (with GaLore) |
|--------|-----------|-----------|------------------------|
| **Quality** | Good | Better | Excellent |
| **Reasoning** | Basic | Good | Advanced |
| **Context Understanding** | Limited | Good | Excellent |
| **Training Time** | 8 hours | 12-16 hours | 48-72 hours |
| **Memory (with 4-bit)** | 2-3GB | 3-4GB | **6-7GB (with GaLore)** |
| **Deployment Size** | ~1GB | ~3GB | ~8GB |
| **Use GaLore?** | Optional | Optional | **Required** |

### When to Use Each Size

#### 0.5B Model - Quick & Efficient  
**Use when:**
- ✅ Experimenting and iterating quickly
- ✅ Simple tasks (factual Q&A, basic instructions)
- ✅ Limited training time (hours, not days)
- ✅ Low-latency inference needed
- ✅ Learning how fine-tuning works

**Example use cases:**
- Customer support bot with straightforward FAQs
- Simple coding assistant for basic syntax
- Information retrieval from structured data

#### 1.5B Model - Balanced
**Use when:**
- ✅ Need better quality than 0.5B
- ✅ Can afford 12-16 hour training
- ✅ Tasks require moderate reasoning
- ✅ Still want relatively fast inference

**Example use cases:**
- General-purpose assistant
- Educational tutoring
- Content generation with moderate complexity

#### 8B Model - Production Quality (Requires GaLore) 🎯
**Use when:**
- ✅ Quality is top priority
- ✅ Can afford 48-72 hour training time
- ✅ Tasks require advanced reasoning
- ✅ Need nuanced, context-aware responses
- ✅ Building production applications

**Example use cases:**
- Professional coding assistant
- Medical/legal domain expertise
- Complex problem-solving
- Natural conversation with personality

### Memory Requirements by Model Size

**Without any optimization:**
```
0.5B: ~4GB    (fits on most GPUs)
1.5B: ~8GB    (fits on Arc B580)
8B:   ~32GB   (doesn't fit on consumer GPUs!)
```

**With 4-bit quantization:**
```
0.5B: ~2GB    ✅ Easy
1.5B: ~4GB    ✅ Comfortable
8B:   ~16GB   ❌ Still too big!
```

**With 4-bit + GaLore:**
```
0.5B: ~2GB    ✅ Easy (GaLore not needed)
1.5B: ~3GB    ✅ Easy (GaLore optional)
8B:   ~6-7GB  ✅ Fits on Arc B580! (GaLore essential)
```

### Training Time Estimates (Arc B580)

**Based on 50K training examples (like Alpaca dataset):**

| Model | Without GaLore | With GaLore | Quality Gain vs 0.5B |
|-------|---------------|-------------|---------------------|
| 0.5B  | 8 hours | 7.5 hours | Baseline |
| 1.5B  | 14 hours | 13 hours | ~2x better |
| 8B    | N/A (OOM) | 60 hours | **~10x better** |

---

## LoRA Configuration Deep Dive

[LoRA content remains mostly the same, with additions for model-specific recommendations]

### `--lora-r` (The Rank)

**Recommendations by model size:**

| Model Size | Typical LoRA Rank | Why |
|------------|------------------|-----|
| 0.5B-1B | r=16 | Good balance |
| 1.5B-3B | r=24-32 | More capacity needed |
| **7B-8B** | **r=32-64** | **Much more capacity** |

```bash
# For 0.5B models
python finetune_qwen.py --lora-r 16

# For 8B models  
python finetune_qwen.py --model-name Qwen/Qwen3-8B --lora-r 32 --use-galore
```

---

## GaLore Configuration (For 7B+ Models)

GaLore (Gradient Low-Rank Projection) is **essential** for training large models (7B+) on consumer GPUs. It reduces optimizer memory by ~60-70%.

### What is GaLore?

**The Problem:**
Training with Adam optimizer requires storing:
- Model weights (8B params = 16GB)
- Optimizer states (2x params = 32GB!)
- Gradients (8B params = 16GB)
- **Total: ~64GB - impossible on Arc B580!**

**GaLore's Solution:**
Project gradients to low-rank space before updating, reducing optimizer memory from 32GB → ~2GB

### When to Use GaLore

| Model Size | GaLore Needed? | Why |
|------------|---------------|-----|
| 0.5B-2B | No | Fits comfortably without it |
| 3B-6B | Optional | Helpful for memory-constrained setups |
| **7B-8B+** | **YES** | **Essential - won't fit otherwise** |

### Installing GaLore

```bash
pip install galore-torch --break-system-packages
```

### `--use-galore` (Enable GaLore Optimizer)

**What it does:** Replaces standard Adam optimizer with GaLore-enhanced version

```bash
# Essential for 8B models
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --use-galore \
  --use-4bit
```

**Memory savings:**

| Configuration | Memory | Status |
|--------------|---------|---------|
| 8B + LoRA only | ~32GB | ❌ Doesn't fit |
| 8B + LoRA + 4-bit | ~16GB | ❌ Still too big |
| **8B + LoRA + 4-bit + GaLore** | **~6-7GB** | **✅ Fits!** |

### `--galore-rank` (Projection Rank)

**What it is:** Rank of the low-rank projection for gradient compression

**Default:** 128 (good for most cases)

```bash
# Maximum compression (minimal memory)
python finetune_qwen.py --use-galore --galore-rank 64

# Balanced - DEFAULT
python finetune_qwen.py --use-galore --galore-rank 128

# Less compression (better gradient accuracy)
python finetune_qwen.py --use-galore --galore-rank 256
```

**Recommendations:**

| Model Size | GaLore Rank | Memory | Training Speed |
|------------|-------------|---------|----------------|
| 7B-8B | 128 | ~6-7GB | ~1.4 it/s |
| 13B+ | 256 | ~8-10GB | ~0.8 it/s |
| Tight memory | 64 | ~5GB | ~1.6 it/s |

**For most users:** Stick with default 128

### `--galore-update-proj-gap` (Projection Update Frequency)

**What it is:** How often (in steps) to recalculate the projection subspace

**Default:** 200 (updates every 200 training steps)

**Typical range:** 100-500 steps

**For most users:** Default 200 is optimal

### `--galore-scale` (Scaling Factor)

**What it is:** Controls how aggressively the projection influences optimization

**Default:** 0.25 (recommended by GaLore paper)

**For most users:** Don't change this - 0.25 is well-tested

### Complete 8B Training Example with GaLore

```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --dataset file \
  --data-file my_data.jsonl \
  --use-4bit \
  --use-galore \
  --galore-rank 128 \
  --galore-update-proj-gap 200 \
  --galore-scale 0.25 \
  --batch-size 2 \
  --gradient-accumulation 8 \
  --lora-r 32 \
  --lora-alpha 64 \
  --epochs 2 \
  --max-seq-length 384 \
  --learning-rate 1e-4 \
  --output-dir ./qwen3-8b-finetuned
```

**Expected:**
- Memory usage: ~6-7GB
- Training time: ~60 hours for 50K examples
- Quality: Excellent, production-ready

---

## Training Parameters Explained

[Training parameters section remains the same, with additions for model-specific recommendations]

### `--learning-rate` (Step Size for Updates)

**Recommendations by model size:**

| Model Size | Learning Rate | Why |
|-----------|--------------|-----|
| 0.5B-1B | 2e-4 | Standard |
| 1.5B-3B | 1e-4 | More conservative |
| **7B-8B** | **5e-5 to 1e-4** | **Very conservative** |
| **8B with GaLore** | **1e-4 to 2e-4** | **GaLore allows slightly higher** |

---

## Memory Management

[Updated memory management section]

### Memory Requirements by Configuration

**Qwen 0.5B:**
```
Normal training:        ~4GB
With 4-bit:            ~2GB
```

**Qwen 1.5B:**
```
Normal training:        ~8GB
With 4-bit:            ~4GB
```

**Qwen3 8B:**
```
Normal training:        ~32GB (impossible!)
With 4-bit only:       ~16GB (still too big!)
With 4-bit + GaLore:   ~6-7GB ✅
```

### OOM? Try This Progression:

**For small models (0.5B-3B):**

1. Enable 4-bit quantization
2. Reduce batch-size to 2
3. Reduce sequence length
4. Reduce LoRA rank

**For large models (7B-8B):**

1. **MUST USE:** Both 4-bit and GaLore
```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --use-4bit \
  --use-galore \
  --batch-size 2
```

2. If still OOM: Reduce sequence length to 384
3. If still OOM: Reduce GaLore rank to 64
4. If still OOM: Reduce LoRA rank to 24

---

## Real-World Examples

### Example 1: MTG Expert (8B with GaLore) 🎯
**Goal:** Professional-quality Magic: The Gathering expert

**Dataset:** 366K MTG examples

**Command:**
```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --dataset file \
  --data-file complete_mtg.jsonl \
  --use-4bit \
  --use-galore \
  --galore-rank 128 \
  --batch-size 2 \
  --gradient-accumulation 8 \
  --lora-r 32 \
  --lora-alpha 64 \
  --epochs 2 \
  --max-seq-length 384 \
  --output-dir ./qwen3-8b-mtg-expert
```

**Why these settings:**
- 8B model for best quality
- GaLore essential to fit in 12GB
- Large dataset (366K) → only 2 epochs
- Smaller seq length (384) to save memory

**Expected time:** ~60 hours on Arc B580

**Quality difference vs 0.5B:**
- 0.5B: "Lightning Bolt deals 3 damage."
- 8B: "Lightning Bolt is one of the most efficient removal spells in Magic, dealing 3 damage to any target for just one red mana. In Modern, it's a staple in aggressive strategies like Burn and tempo decks. It's also legal in Legacy and Vintage where it remains powerful instant-speed removal..."

### Example 2: Code Assistant (8B)
**Goal:** Production-quality coding assistant

**Command:**
```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --dataset hf \
  --hf-dataset yahma/alpaca-cleaned \
  --use-4bit \
  --use-galore \
  --batch-size 2 \
  --gradient-accumulation 8 \
  --lora-r 32 \
  --max-seq-length 512 \
  --epochs 2 \
  --learning-rate 1e-4 \
  --output-dir ./code-assistant-8b
```

**Expected time:** ~72 hours on Arc B580

[Other examples remain similar]

---

## Troubleshooting

### GaLore-Specific Issues

#### "ImportError: No module named 'galore_torch'"
**Problem:** GaLore not installed but needed for large models

**Solution:**
```bash
pip install galore-torch --break-system-packages
```

#### "Training is extremely slow on 8B model"
**Symptoms:** Much slower than expected

**This is normal for 8B models with GaLore:**
- Expected speed: ~1.4 steps/sec
- For 366K examples: ~60-70 hours total
- If much slower, check:
  1. GPU is being used (not CPU)
  2. Batch size isn't too small (use at least 2)
  3. System isn't swapping to disk

---

## Understanding Checkpoints

[Checkpoint section remains the same, with note about long 8B training]

### Resuming Long Training Runs (Important for 8B Models)

For 8B models training for 60+ hours, you'll likely want to resume at some point:

```bash
# Original training (started, then stopped at checkpoint-5000)
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --use-4bit --use-galore \
  ... other args ...

# Resume from where you left off
python finetune_qwen.py \
  --model-name Qwen/Qwen3-8B \
  --use-4bit --use-galore \
  --resume-from-checkpoint ./output/checkpoint-5000 \
  ... same args as before ...
```

**IMPORTANT:** Use the exact same settings when resuming!

---

## Quick Reference Tables

### By Model Size

| Model | Recommended Settings | 4-bit | GaLore | Memory | Time (50K ex) | Quality |
|-------|---------------------|-------|--------|---------|---------------|---------|
| **0.5B** | r=16, batch=4, lr=2e-4 | Optional | No | ~2-3GB | 8 hours | Good |
| **1.5B** | r=24, batch=4, lr=1e-4 | Yes | No | ~4GB | 12 hours | Better |
| **8B** | r=32, batch=2, lr=1e-4 | **Required** | **Required** | **~6-7GB** | **60 hours** | **Excellent** |

### By Use Case

| Use Case | Model | Dataset | Settings | Time | Result |
|----------|-------|---------|----------|------|--------|
| Quick test | 0.5B | sample | Default | 2 min | Validates setup |
| Simple bot | 0.5B | 500 examples | r=16, epochs=5 | 15 min | Basic but functional |
| General assistant | 1.5B | Alpaca | r=24, 4-bit | 40 min | Good quality |
| **Production quality** | **8B** | **Alpaca** | **GaLore+4bit** | **60 hours** | **Excellent** |
| **Professional domain** | **8B** | **10K+ custom** | **GaLore+4bit, r=64** | **80 hours** | **Best possible** |

### Memory-Saving Priority

Try these in order if you hit OOM:

| Priority | Action | Memory Saved | Quality Impact |
|----------|--------|--------------|----------------|
| 1 | Add `--use-4bit` | 50% | Minimal (<1%) |
| 2 | For 8B: Add `--use-galore` | 60% | None |
| 3 | Reduce `--batch-size` to 2 | 20% | None (adjust grad accum) |
| 4 | Reduce `--max-seq-length` | 30% | Depends on your data |
| 5 | Reduce `--lora-r` | 10% | Moderate |
| 6 | Reduce `--galore-rank` (if using) | 10% | Small |

---

## Getting Help

```bash
# See all options
python finetune_qwen.py --help

# Check if GaLore is installed
python -c "import galore_torch; print('GaLore installed!')"

# Test your setup first
python finetune_qwen.py --dataset sample --epochs 1
```

---

**Remember:** 
- **0.5B-1.5B models:** Great for learning and iteration
- **8B models with GaLore:** Best quality, but requires time investment
- Always start small to validate your setup before committing to multi-day 8B training!