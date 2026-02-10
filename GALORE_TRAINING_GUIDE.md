# GaLore Training Optimization Guide

Complete guide for training your MTG expert model with GaLore (Gradient Low-Rank Projection).

## 🎯 Recommended Command (Conservative)

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
  --warmup-steps 50 \
  > training.log 2>&1
```

**Training Stats:**
- Time: ~20-22 hours on Intel B580
- Memory: ~10-11GB VRAM
- Quality: Excellent for 140K examples

## 📊 Parameter Breakdown

### Core Parameters

#### `--lora-r 32`
**LoRA Rank** - Controls adapter capacity
- **Too Low (16):** Underfits on large datasets
- **Sweet Spot (32):** Good for 140K examples
- **Too High (128):** Overfits, longer training

**Rule of thumb:** `lora_r = dataset_size / 5000`
- 50K examples → r=16
- 140K examples → r=32
- 500K examples → r=64

#### `--galore-rank 256`
**GaLore Subspace Rank** - Controls gradient compression
- **Must be > lora-r** (typically 4-8x larger)
- **256:** Good balance for 3B model
- **512:** Maximum quality (slower)

**Relationship:**
```
lora-r=32  → galore-rank=256  (8x, recommended)
lora-r=64  → galore-rank=512  (8x, high quality)
lora-r=16  → galore-rank=128  (8x, small datasets)
```

#### `--learning-rate 5e-5`
**Learning Rate** - How fast the model learns
- **With GaLore:** Use 50% of normal LR
- **Without GaLore:** 1e-4 is typical
- **With GaLore:** 5e-5 is stable

**Why lower with GaLore?**
- GaLore compresses gradients → more stable updates
- Lower LR prevents overshooting
- Better convergence on large datasets

#### `--batch-size 4` + `--gradient-accumulation 4`
**Effective Batch Size = 16**

```
Effective Batch Size = batch_size × gradient_accumulation × num_gpus
                     = 4 × 4 × 1 = 16
```

**Memory vs Speed Trade-offs:**
```
Config A: batch=4, accum=4  → 16 examples, moderate speed
Config B: batch=8, accum=2  → 16 examples, faster (if memory allows)
Config C: batch=2, accum=8  → 16 examples, slower but safe
```

#### `--epochs 3`
**Number of Passes Over Dataset**
- **1 epoch:** Quick test, likely underfit
- **3 epochs:** Standard, good coverage of 140K examples
- **5 epochs:** Risk of overfitting

**Calculate training steps:**
```
Steps per epoch = dataset_size / effective_batch_size
                = 140,000 / 16 = 8,750 steps
Total steps = 8,750 × 3 = 26,250 steps
```

#### `--save-steps 500`
**Checkpoint Frequency**
- Saves model every 500 steps
- ~52 checkpoints over full training
- Allows recovery if training crashes
- Can test intermediate checkpoints

#### `--warmup-steps 50`
**Learning Rate Warmup**
- Gradually increases LR from 0 to target
- Stabilizes training start
- Prevents early gradient explosions

**Warmup schedule:**
```
Steps 0-50:    LR ramps from 0 to 5e-5
Steps 50+:     LR stays at 5e-5 (or decays if using scheduler)
```

## 🚀 Alternative Configurations

### Fast Training (Lower Quality)
```bash
python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 16 \
  --use-galore \
  --galore-rank 128 \
  --batch-size 8 \
  --learning-rate 8e-5 \
  --gradient-accumulation 2 \
  --epochs 2 \
  --output-dir ./qwen-3b-mtg-expert-fast \
  --save-steps 1000 \
  > training.log 2>&1
```

**Stats:**
- Time: ~12-14 hours
- Quality: Good for quick iteration
- Use case: Testing, rapid prototyping

### Maximum Quality (Slower)
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
  --output-dir ./qwen-3b-mtg-expert-hq \
  --save-steps 500 \
  --warmup-steps 100 \
  > training.log 2>&1
```

**Stats:**
- Time: ~26-28 hours
- Quality: Maximum
- Use case: Production model, final version

### Balanced (Recommended Start)
The conservative command at the top of this guide.

## 🔧 Troubleshooting

### Out of Memory (OOM)

**Symptom:**
```
RuntimeError: CUDA out of memory
```

**Solutions (try in order):**

1. **Reduce batch size:**
```bash
--batch-size 2 \
--gradient-accumulation 8 \
```

2. **Lower ranks:**
```bash
--lora-r 24 \
--galore-rank 192 \
```

3. **Enable gradient checkpointing** (if not already):
```bash
--gradient-checkpointing \
```

### NaN Loss

**Symptom:**
```
Step 1000: loss = nan
```

**Solutions:**

1. **Lower learning rate:**
```bash
--learning-rate 3e-5 \
```

2. **Increase warmup:**
```bash
--warmup-steps 100 \
```

3. **Check data quality:**
```bash
# Sample your training data
head -100 mongodb_mtg_training.jsonl | python -m json.tool
```

### Training Too Slow

**Symptom:**
```
Step 100/26250 [00:30, 3.33s/it]
# Would take 24+ hours
```

**Solutions:**

1. **Increase batch size** (if memory allows):
```bash
--batch-size 8 \
--gradient-accumulation 2 \
```

2. **Reduce save frequency:**
```bash
--save-steps 1000 \
```

3. **Consider mixed precision** (if not already):
```bash
--fp16 \  # or --bf16 for newer GPUs
```

### Loss Not Decreasing

**Symptom:**
```
Epoch 1: loss stays at 2.0
```

**Solutions:**

1. **Increase learning rate:**
```bash
--learning-rate 1e-4 \
```

2. **Check if frozen by accident:**
```bash
# Verify LoRA is enabled
--lora-r 32 \
```

3. **Increase model capacity:**
```bash
--lora-r 48 \
--galore-rank 384 \
```

## 📊 Monitoring Training

### Watch Log in Real-Time
```bash
tail -f training.log
```

### What to Look For

**Good Training:**
```
Step 100: loss=1.8234, lr=5e-5
Step 200: loss=1.6891, lr=5e-5
Step 300: loss=1.5023, lr=5e-5  # ✓ Decreasing
Step 400: loss=1.3456, lr=5e-5
```

**Bad Training:**
```
Step 100: loss=2.0123, lr=5e-5
Step 200: loss=2.0098, lr=5e-5
Step 300: loss=2.0134, lr=5e-5  # ✗ Not decreasing
Step 400: loss=2.0089, lr=5e-5
```

**Overfitting:**
```
Epoch 1: loss=1.5 → 0.8  # ✓ Good
Epoch 2: loss=0.8 → 0.4  # ✓ Good
Epoch 3: loss=0.4 → 0.2  # ⚠️ Might be overfitting
```

### Check Checkpoints
```bash
# Load a checkpoint and test
python test_model.py --checkpoint ./qwen-3b-mtg-expert/checkpoint-10000

# Compare multiple checkpoints
python compare_checkpoints.py \
  --checkpoints checkpoint-5000 checkpoint-10000 checkpoint-15000
```

## ⏱️ Time Estimates by Hardware

### Intel ARC B580 (12GB)
```
Conservative (r=32):  ~20-22 hours
Fast (r=16):         ~12-14 hours
High Quality (r=64):  ~26-28 hours
```

### NVIDIA RTX 4090 (24GB)
```
Conservative (r=32):  ~15-18 hours
Fast (r=16):         ~9-11 hours
High Quality (r=64):  ~20-22 hours
```

### NVIDIA RTX 3090 (24GB)
```
Conservative (r=32):  ~22-25 hours
Fast (r=16):         ~14-16 hours
High Quality (r=64):  ~28-32 hours
```

## 💾 Memory Usage

### Configuration Memory Map

```
Base Model (4-bit):           ~2.5 GB
LoRA Adapters (r=32):         ~0.5 GB
GaLore Optimizer (rank=256):  ~3.0 GB
Activations & Gradients:      ~4.0 GB
────────────────────────────────────
Total:                        ~10 GB

With r=64, galore=512:        ~12 GB
```

### Memory Optimization Tips

1. **Enable gradient checkpointing:**
```bash
--gradient-checkpointing \
```
Saves ~2GB but 10-15% slower

2. **Lower precision:**
```bash
--fp16 \  # or --bf16
```
Saves ~20% memory

3. **Offload optimizer:**
```bash
--cpu-offload \
```
Saves GPU memory but slower

## 🎯 Recommended Workflow

### Step 1: Test Run (2 hours)
```bash
# Quick sanity check
python finetune_qwen.py \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --dataset file \
  --data-file mongodb_mtg_training.jsonl \
  --use-4bit \
  --lora-r 16 \
  --use-galore \
  --galore-rank 128 \
  --batch-size 4 \
  --learning-rate 5e-5 \
  --gradient-accumulation 4 \
  --epochs 1 \
  --output-dir ./test-run \
  --save-steps 500
```

**Check:**
- ✓ No OOM errors
- ✓ Loss decreasing
- ✓ Can load checkpoints

### Step 2: Full Training (20-22 hours)
```bash
# Use recommended conservative settings
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
  --warmup-steps 50 \
  > training.log 2>&1
```

### Step 3: Evaluate
```bash
# Test the final model
python test_model.py --model ./qwen-3b-mtg-expert

# Test intermediate checkpoints if final seems off
python test_model.py --model ./qwen-3b-mtg-expert/checkpoint-20000
```

### Step 4: Optional - High Quality Retrain
If results are good but want even better:
```bash
# Use high-quality settings
python finetune_qwen.py \
  [... high quality config from above ...]
```

## 📈 Expected Loss Trajectory

### Good Training (Conservative Settings)
```
Epoch 1:
  Start: loss ~2.0
  End:   loss ~0.8
  
Epoch 2:
  Start: loss ~0.8
  End:   loss ~0.5
  
Epoch 3:
  Start: loss ~0.5
  End:   loss ~0.3-0.4
```

If final loss < 0.3, you're likely overfitting.
If final loss > 0.6, consider training longer or increasing capacity.

## ✅ Final Checklist

Before starting training:
- [ ] Generated training data (140K examples)
- [ ] Verified JSONL format is valid
- [ ] Have 12GB+ VRAM available
- [ ] Training will run uninterrupted (20+ hours)
- [ ] Logging configured (2>&1 redirect)
- [ ] Enough disk space (~10GB for checkpoints)

During training:
- [ ] Monitor first 1000 steps for issues
- [ ] Check loss is decreasing
- [ ] No NaN values appearing
- [ ] Memory usage stable

After training:
- [ ] Test with sample questions
- [ ] Compare against base model
- [ ] Evaluate on hold-out examples
- [ ] Check for overfitting signs

## 🚀 Ready to Train!

Use the **conservative command** at the top of this guide for best results. Good luck! 🎯
