"""
Command-line argument parsing for Qwen fine-tuning.

This module defines all the "knobs and dials" you can adjust when running
the fine-tuning script. Each argument has a name, type, default value, and help text.

Real-world analogy: Think of these like the controls on a mixing board in a
recording studio. Each slider controls a different aspect of the sound (training).
The defaults give you a reasonable starting point, but you can tweak them.
"""

import argparse


def parse_args():
    """
    Parse command-line arguments for fine-tuning configuration.

    Returns:
        argparse.Namespace: Parsed arguments containing all training configuration.
    """
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen models (0.5B to 8B+) with LoRA and optional GaLore"
    )

    # --- Dataset options ---
    # Where should the training data come from?
    parser.add_argument(
        "--dataset",
        type=str,
        choices=["sample", "hf", "file"],
        default="sample",
        # "sample" = built-in toy data (for testing the pipeline works)
        # "hf"     = download from Hugging Face Hub (community datasets)
        # "file"   = load from a local JSONL file (our MTG data)
        help="Dataset source: 'sample' (built-in), 'hf' (Hugging Face), or 'file' (custom JSONL)"
    )
    parser.add_argument(
        "--hf-dataset",
        type=str,
        default="yahma/alpaca-cleaned",
        # Only used when --dataset=hf. This is the name of a dataset on
        # huggingface.co/datasets. alpaca-cleaned is a popular instruction dataset.
        help="Hugging Face dataset name (when --dataset=hf)"
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default="data.jsonl",
        # Only used when --dataset=file. Points to your local JSONL file.
        # JSONL = one JSON object per line, like a spreadsheet where each row
        # is a complete JSON record.
        help="Path to JSONL data file (when --dataset=file)"
    )

    # --- Model and output ---
    parser.add_argument(
        "--model-name",
        type=str,
        default="Qwen/Qwen2.5-0.5B-Instruct",
        # This is the Hugging Face model ID. The first time you run this, it
        # downloads the model weights from huggingface.co. After that, it uses
        # the cached version.
        #
        # Recommended models:
        # - Qwen/Qwen2.5-0.5B-Instruct: Small, fast, fits easily (training: ~8 hours)
        # - Qwen/Qwen2.5-1.5B-Instruct: Medium, good quality (training: ~12 hours)
        # - Qwen/Qwen3-8B: Large, excellent quality, REQUIRES GaLore (training: ~48 hours)
        #
        # For 8B models, you MUST use --use-galore --use-4bit or it won't fit!
        help="Base model to fine-tune (0.5B to 8B supported)"
    )

    parser.add_argument(
        "--hf-token",
        type=str,
        default=None,
        help="Hugging Face token for accessing gated models"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./qwen-finetuned",
        # Where to save the trained LoRA adapter weights. This directory will
        # contain the adapter files (small, ~10-50MB) -- NOT a full copy of the model.
        # To use the model later, you load the base model + this adapter on top.
        help="Directory to save fine-tuned model"
    )

    # --- LoRA configuration ---
    # These control the LoRA adapter's size and behavior.
    # Think of these as controlling how big and how many "sticky notes" you add.
    parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        # "r" is the RANK of the LoRA matrices. Higher rank = more capacity to
        # learn new things, but uses more memory and risks overfitting.
        #
        # Real-world analogy: Imagine summarizing a book. Rank is like how many
        # bullet points you're allowed. r=8 gives you a brief summary, r=64 gives
        # you a detailed outline. For most tasks, 16-32 is the sweet spot.
        #
        # Technical detail: LoRA decomposes a large weight matrix (e.g., 1024x1024)
        # into two small matrices (1024x16 and 16x1024). Instead of updating
        # 1,048,576 parameters, you only update 32,768. That's 32x fewer!
        #
        # Recommendations by model size:
        # - 0.5B-1B models: r=16 (default)
        # - 1.5B-3B models: r=24-32
        # - 7B-8B models: r=32-64
        help="LoRA rank (8-64, higher = more capacity)"
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        # Alpha controls the "learning rate scaling" of LoRA. The effective
        # scaling factor is alpha/r. With r=16 and alpha=32, the scaling is 2x.
        #
        # Real-world analogy: If rank is how many sticky notes you add, alpha
        # is how bold the writing is on those notes. Higher alpha means the
        # new knowledge has more influence over the original model.
        #
        # Rule of thumb: Set alpha = 2 * rank for a good starting point.
        help="LoRA alpha (typically 2x the rank)"
    )
    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.05,
        # Dropout randomly disables some LoRA connections during training.
        # This prevents overfitting (the model memorizing training data instead
        # of learning general patterns).
        #
        # Real-world analogy: Like a basketball team practicing while randomly
        # benching a player each drill. This forces every player to step up,
        # making the team more resilient. 0.05 = 5% chance of "benching" each
        # connection per training step.
        help="LoRA dropout for regularization"
    )

    # --- GaLore configuration ---
    # GaLore is ESSENTIAL for training large models (7B+) on consumer GPUs.
    # It reduces optimizer memory by ~60-70% through gradient projection.
    parser.add_argument(
        "--use-galore",
        action="store_true",
        # "action=store_true" means this is a flag: just adding --use-galore
        # enables it (no value needed).
        #
        # When to use GaLore:
        # - Training models 7B+ on consumer GPUs (12-24GB VRAM)
        # - You're running out of memory even with 4-bit + LoRA
        # - You want to use larger batch sizes on big models
        #
        # When NOT to use GaLore:
        # - Training small models (0.5B-2B) that already fit comfortably
        # - You have plenty of VRAM (>40GB)
        #
        # Memory comparison for 8B model on 12GB GPU:
        # - LoRA + 4-bit: ~14GB (OOM!)
        # - LoRA + 4-bit + GaLore: ~6-7GB (fits!)
        help="Use GaLore optimizer for memory-efficient training (essential for 7B+ models)"
    )
    parser.add_argument(
        "--galore-rank",
        type=int,
        default=128,
        # The rank of the low-rank projection used by GaLore. This is different
        # from LoRA rank -- it controls how much to compress the gradients.
        #
        # Higher rank = more accurate gradient information but more memory.
        # Lower rank = more compression but potentially slower convergence.
        #
        # Real-world analogy: Like image compression quality. Rank 256 is like
        # saving at 95% quality (barely noticeable difference), rank 64 is like
        # 70% quality (visible artifacts but much smaller file).
        #
        # Recommendations:
        # - 7B-8B models: 128 (default, good balance)
        # - 13B+ models: 256 (less compression needed)
        # - Memory constrained: 64 (maximum compression)
        help="GaLore projection rank (64-256, higher = less compression)"
    )
    parser.add_argument(
        "--galore-update-proj-gap",
        type=int,
        default=200,
        # How often (in training steps) to update the GaLore projection subspace.
        # The projection is the "compression algorithm" used for gradients.
        #
        # Too frequent (e.g., every step): Wastes compute recomputing projection
        # Too infrequent (e.g., every 1000 steps): Projection becomes stale
        #
        # 200 steps is a good default that balances computation and freshness.
        # This typically aligns with checkpoint saving frequency.
        #
        # Real-world analogy: Like recalibrating a GPS. You don't recalibrate
        # every second (wasteful), but you also don't wait until you're completely
        # lost. Every few minutes (200 steps) is a good middle ground.
        help="Update GaLore projection every N steps (100-500 recommended)"
    )
    parser.add_argument(
        "--galore-scale",
        type=float,
        default=0.25,
        # Scaling factor for GaLore updates. This controls how aggressively the
        # low-rank projection influences the optimization.
        #
        # Lower scale (0.1-0.25): More conservative, safer for stability
        # Higher scale (0.5-1.0): More aggressive, faster convergence but risky
        #
        # 0.25 is well-tested and recommended by the GaLore paper authors.
        #
        # Real-world analogy: Like the gain knob on an amplifier. 0.25 gives you
        # a clear signal without distortion, while 1.0 might overdrive and cause
        # clipping (training instability).
        help="GaLore scaling factor (0.1-1.0, lower = more conservative)"
    )

    # --- Training configuration ---
    # These control the training loop itself.
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        # An "epoch" is one complete pass through all training data.
        # 3 epochs means the model sees every example 3 times.
        #
        # Real-world analogy: Like re-reading a textbook. Reading it once (1
        # epoch) gives you a basic understanding. Reading it 3 times helps it
        # sink in. But reading it 100 times and you just memorize it word-for-
        # word without understanding (overfitting).
        #
        # Guidelines:
        # - Small dataset (<1000 examples): 5-10 epochs
        # - Medium dataset (1000-10000): 3-5 epochs
        # - Large dataset (10000+): 1-3 epochs
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        # How many training examples the model processes simultaneously per step.
        # Larger batch = more stable training but uses more GPU memory.
        #
        # Real-world analogy: Like grading papers. Batch size 1 means you grade
        # one paper, adjust your rubric, then grade the next. Batch size 32 means
        # you grade 32 papers, think about common mistakes, then adjust your
        # rubric once. Larger batches give you a better picture of the overall
        # trend, but you need a bigger desk (GPU memory) to hold all the papers.
        #
        # Recommendations by model size:
        # - 0.5B-1B: batch_size=8 (or 4 with 4-bit)
        # - 1.5B-3B: batch_size=4
        # - 7B-8B: batch_size=2 (with 4-bit + GaLore)
        # - 13B+: batch_size=1 (with 4-bit + GaLore)
        help="Batch size per device"
    )
    parser.add_argument(
        "--gradient-accumulation",
        type=int,
        default=4,
        # A trick to simulate larger batch sizes without needing the GPU memory.
        # With batch_size=4 and gradient_accumulation=4, the model processes 4
        # examples at a time but accumulates gradients over 4 steps before
        # updating weights. Effective batch size = 4 * 4 = 16.
        #
        # Real-world analogy: Like taking notes during 4 separate meetings
        # before writing one summary report. You're gathering more information
        # before making a decision, without needing a bigger meeting room.
        #
        # Target effective batch size: 16-32 for most tasks
        # Formula: batch_size * gradient_accumulation = effective_batch_size
        help="Gradient accumulation steps"
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        # How much the model adjusts its weights in response to each batch.
        # 2e-4 = 0.0002. Too high and the model overshoots (like turning the
        # steering wheel too hard). Too low and training takes forever.
        #
        # Real-world analogy: Imagine tuning a guitar string. The learning rate
        # is how much you turn the tuning peg each time. Too much and you
        # overshoot the right pitch. Too little and you're turning forever.
        #
        # Recommendations:
        # - 0.5B-2B models: 2e-4 (default)
        # - 3B-7B models: 1e-4 (more conservative)
        # - 8B+ models: 5e-5 to 1e-4 (very conservative)
        # - With GaLore: Can use slightly higher (1.5-2x)
        help="Learning rate"
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=512,
        # Maximum number of tokens (word pieces) per training example.
        # Longer sequences use more memory. 512 tokens is roughly 350-400 words.
        #
        # Real-world analogy: Like the maximum essay length on an exam.
        # Anything longer gets truncated (cut off). For MTG card Q&A, 512 is
        # usually plenty. For longer strategy guides, you might want 1024+.
        #
        # Memory impact: Doubling sequence length roughly doubles memory usage!
        # Recommendations:
        # - Short Q&A: 256-512
        # - Longer conversations: 1024
        # - Very long documents: 2048 (but needs lots of VRAM)
        help="Maximum sequence length"
    )

    # --- Other options ---
    parser.add_argument(
        "--use-4bit",
        action="store_true",
        # "action=store_true" means this is a flag: just adding --use-4bit
        # enables it (no value needed). 4-bit quantization compresses the model
        # weights from 16 bits to 4 bits per number, using ~4x less memory.
        #
        # Real-world analogy: Like compressing a high-res photo to a thumbnail.
        # You lose some quality but it takes way less storage. For training
        # large models, this is ESSENTIAL.
        #
        # Memory savings:
        # - 0.5B model: 1GB → 0.25GB (helpful but not critical)
        # - 8B model: 16GB → 4GB (absolutely essential!)
        #
        # Quality impact: Minimal (<1% difference) for fine-tuning.
        # The base model knowledge is preserved; we're just adjusting LoRA adapters.
        #
        # NOTE: 4-bit quantization may not work on older Intel XPU (Arc GPUs) drivers.
        # The bitsandbytes library primarily targets NVIDIA CUDA GPUs, but newer
        # Intel drivers (2024+) have added support.
        help="Use 4-bit quantization (essential for large models, ~75% memory reduction)"
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        # Skip the test generation after training. Useful if you want to train
        # and evaluate separately, or if you're running automated pipelines.
        help="Skip test generation after training"
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        type=str,
        default=None,
        # Path to a training checkpoint directory to resume training from.
        # During training, the trainer periodically saves "checkpoints" -- full
        # snapshots of the training state including model weights, optimizer state,
        # learning rate scheduler state, and the random number generator states.
        #
        # Real-world analogy: Imagine you're writing a long essay and your computer
        # crashes. If you had auto-save enabled, you can reopen the document and
        # pick up right where you left off instead of starting from scratch. That's
        # exactly what checkpoint resumption does for model training.
        #
        # Checkpoints are saved to directories like "checkpoint-200" (where 200 is
        # the global step number). To resume, point this at that directory:
        #   --resume-from-checkpoint ./output/checkpoint-200
        #
        # Why this matters:
        #   - Training can take hours or days. If it crashes, you don't lose progress.
        #   - You can stop training, adjust hyperparameters, and continue.
        #   - Lets you extend training (e.g., train 3 more epochs from where you
        #     stopped) without repeating already-completed work.
        #
        # IMPORTANT with GaLore: If you're using --use-galore, you must resume
        # with the same GaLore settings (rank, update_proj_gap, scale). Changing
        # these will cause errors or poor results.
        #
        # NOTE: The checkpoint directory must match the same model and LoRA config
        # you're using. You can't resume a checkpoint from a different model.
        help="Path to a checkpoint directory to resume training from (e.g., ./output/checkpoint-200)"
    )

    return parser.parse_args()
