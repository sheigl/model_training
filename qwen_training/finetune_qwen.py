"""
Fine-tune Qwen 2.5 0.5B / Qwen3 8B with LoRA and optional GaLore
=================================================================

WHAT THIS SCRIPT DOES:
    This script takes a pre-trained language model (Qwen 2.5 0.5B or Qwen3 8B) and
    teaches it new behavior using your custom data. This is called "fine-tuning."

    Real-world analogy: Imagine hiring someone who already has a college degree
    (the pre-trained model). They know how to read, write, and reason. Now you're
    giving them specialized on-the-job training (fine-tuning) to become an expert
    in YOUR specific field -- in this case, Magic: The Gathering.

WHY LoRA (Low-Rank Adaptation)?
    Normally, fine-tuning means updating ALL of a model's parameters (weights).
    For a 0.5 billion parameter model, that requires a LOT of GPU memory.
    For an 8 billion parameter model, it's impossible on consumer hardware.

    LoRA is a shortcut: instead of rewriting the entire textbook, you add small
    sticky notes (adapters) to specific pages. The original book stays the same,
    and the sticky notes teach the new behavior. This uses ~10x less memory.

    Real-world analogy: Instead of rebuilding an entire car engine to go faster,
    you bolt on a turbocharger. The engine stays the same, but the turbo (LoRA
    adapter) changes its behavior. You can even swap turbos (adapters) for
    different tasks without touching the engine.

WHY GaLore (Gradient Low-Rank Projection)?
    GaLore goes one step further than LoRA by also reducing optimizer memory.

    The problem: When training with Adam optimizer, you need to store:
    - Model weights (8B params = 16GB in bfloat16)
    - Optimizer states (2x the params = 32GB!)
    - Gradients (8B params = 16GB)
    Total: ~64GB for 8B model -- impossible on consumer GPUs!

    GaLore's solution: Project gradients to a low-rank space before updating.
    This reduces optimizer memory by ~60-70%, making 8B model training possible
    on 12GB consumer GPUs when combined with 4-bit quantization and LoRA.

    Real-world analogy: Instead of storing a full HD movie (model gradients),
    you store a compressed version (low-rank projection) that captures the
    important information in a smaller size. When you need to watch it, you
    decompress just enough to see the picture clearly.

    Memory savings with GaLore:
    - Qwen 0.5B: 5GB → 4GB (not critical, but helps)
    - Qwen3 8B: 16GB → 6-7GB (critical! makes it possible)

WHEN TO USE WHAT:
    For Qwen 0.5B - 2B models:
    - LoRA + 4-bit is sufficient
    - GaLore optional (adds complexity without much benefit)

    For Qwen3 8B+ models:
    - LoRA + 4-bit + GaLore is ESSENTIAL
    - Without GaLore: Won't fit in 12GB
    - With GaLore: Fits comfortably in 12GB

WHAT YOU NEED:
    - A GPU (this script supports Intel Arc via XPU, NVIDIA via CUDA, or CPU)
    - Training data in JSONL format (conversations with user/assistant messages)
    - The dependencies in pyproject.toml installed via: uv sync
    - For GaLore: pip install galore-torch

Usage:
    # Qwen 0.5B with LoRA (simple, fast)
    python finetune_qwen.py --dataset file --data-file my_data.jsonl

    # Qwen3 8B with LoRA + 4-bit + GaLore (advanced, better quality)
    python finetune_qwen.py \
        --model-name Qwen/Qwen3-8B \
        --dataset file \
        --data-file my_data.jsonl \
        --use-4bit \
        --use-galore \
        --batch-size 2 \
        --gradient-accumulation 8

    # With checkpoint resumption
    python finetune_qwen.py \
        --dataset file \
        --data-file my_data.jsonl \
        --resume-from-checkpoint ./output/checkpoint-1000
"""

import os

# Import from our modular components
from cli import parse_args
from data import create_sample_dataset, load_custom_dataset, load_hf_dataset
from model import (
    GALORE_AVAILABLE,
    detect_device,
    load_model,
    load_tokenizer,
    apply_lora,
)
from trainer import create_training_config, create_trainer
from inference import test_model


def main():
    """Main entry point for fine-tuning."""

    # ==========================================================================
    # PARSE ARGUMENTS
    # ==========================================================================
    args = parse_args()

    # ==========================================================================
    # VALIDATE GALORE AVAILABILITY
    # ==========================================================================
    # If the user requested GaLore but it's not installed, we need to fail early
    # with a helpful error message rather than continuing and crashing later.
    if args.use_galore and not GALORE_AVAILABLE:
        print("\n" + "="*70)
        print("ERROR: GaLore requested but not installed!")
        print("="*70)
        print("\nYou used --use-galore but the galore-torch library is not available.")
        print("\nTo install GaLore:")
        print("  pip install galore-torch --break-system-packages")
        print("\nOr run without --use-galore (only works for small models <3B)")
        print("="*70 + "\n")
        exit(1)

    # ==========================================================================
    # PRINT CONFIGURATION
    # ==========================================================================
    # Print out all the settings so you can verify what you're about to run.
    # This is like a pre-flight checklist before takeoff -- catch mistakes early.
    print("\n" + "="*70)
    print("CONFIGURATION")
    print("="*70)
    print(f"Dataset: {args.dataset}")
    if args.dataset == "hf":
        print(f"  HF Dataset: {args.hf_dataset}")
    elif args.dataset == "file":
        print(f"  Data file: {args.data_file}")
    print(f"Model: {args.model_name}")
    print(f"Output directory: {args.output_dir}")
    print(f"\nLoRA Config:")
    print(f"  r={args.lora_r}, alpha={args.lora_alpha}, dropout={args.lora_dropout}")
    print(f"\nTraining Config:")
    print(f"  Epochs={args.epochs}, Batch size={args.batch_size}")
    print(f"  Gradient accumulation={args.gradient_accumulation}")
    print(f"  Effective batch size={args.batch_size * args.gradient_accumulation}")
    print(f"  Learning rate={args.learning_rate}")
    print(f"  Max sequence length={args.max_seq_length}")
    print(f"\nMemory Optimization:")
    print(f"  Use 4-bit quantization: {args.use_4bit}")
    print(f"  Use GaLore optimizer: {args.use_galore}")
    if args.use_galore:
        print(f"    GaLore rank: {args.galore_rank}")
        print(f"    Update projection gap: {args.galore_update_proj_gap} steps")
        print(f"    Scaling factor: {args.galore_scale}")
    if args.resume_from_checkpoint:
        print(f"\nResume from checkpoint: {args.resume_from_checkpoint}")
    print("="*70 + "\n")

    # Warn user about training time for large models
    if "8B" in args.model_name or "7B" in args.model_name:
        print("⚠️  WARNING: You're training a large model (7B-8B parameters)")
        print("   Expected training time on consumer GPU: 48-72 hours")
        if not args.use_galore:
            print("   ⚠️  You should probably use --use-galore for memory efficiency!")
        if not args.use_4bit:
            print("   ⚠️  You should use --use-4bit for large models!")
        print()

    # ==========================================================================
    # DETECT DEVICE
    # ==========================================================================
    device = detect_device()

    # ==========================================================================
    # LOAD MODEL AND TOKENIZER
    # ==========================================================================
    print("\nLoading model and tokenizer...")

    model = load_model(
        model_name=args.model_name,
        use_4bit=args.use_4bit,
        device=device,
        hf_token=args.hf_token
    )

    tokenizer = load_tokenizer(args.model_name)

    # ==========================================================================
    # APPLY LoRA
    # ==========================================================================
    model, trainable_params, total_params = apply_lora(
        model,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout
    )

    # ==========================================================================
    # PREPARE DATASET
    # ==========================================================================
    print("\nPreparing dataset...")

    # Load dataset based on user selection
    if args.dataset == "sample":
        print("Using built-in sample dataset")
        train_dataset = create_sample_dataset()
    elif args.dataset == "hf":
        print(f"Loading Hugging Face dataset: {args.hf_dataset}")
        train_dataset = load_hf_dataset(args.hf_dataset)
    elif args.dataset == "file":
        print(f"Loading data from file: {args.data_file}")
        if not os.path.exists(args.data_file):
            raise FileNotFoundError(f"Data file not found: {args.data_file}")
        train_dataset = load_custom_dataset(args.data_file)
    else:
        raise ValueError(f"Unknown dataset type: {args.dataset}")

    # Split the dataset into training (90%) and evaluation (10%) sets.
    # The evaluation set is data the model NEVER trains on -- it's used to
    # measure how well the model generalizes to unseen examples.
    #
    # Real-world analogy: Like a practice test vs the real exam. You study
    # (train) using the practice tests, then take the real exam (evaluation)
    # to see if you actually learned the material vs just memorizing answers.
    # If you do well on practice but poorly on the exam, you've overfit.
    train_test_split = train_dataset.train_test_split(test_size=0.1)
    train_dataset = train_test_split["train"]
    eval_dataset = train_test_split["test"]

    print(f"Training examples: {len(train_dataset)}")
    print(f"Evaluation examples: {len(eval_dataset)}")

    # Calculate training time estimate
    # This is a rough estimate based on typical speeds
    steps_per_epoch = len(train_dataset) // (args.batch_size * args.gradient_accumulation)
    total_steps = steps_per_epoch * args.epochs

    # Rough speed estimates (steps per second) by model size and hardware
    if "8B" in args.model_name or "7B" in args.model_name:
        if args.use_galore:
            speed_estimate = 1.4  # With GaLore on Arc B580
        else:
            speed_estimate = 0.5  # Without GaLore (if it even fits)
    elif "1.5B" in args.model_name or "3B" in args.model_name:
        speed_estimate = 2.0
    else:  # 0.5B-1B
        speed_estimate = 3.0

    estimated_time_hours = total_steps / speed_estimate / 3600
    print(f"\nEstimated training time: ~{estimated_time_hours:.1f} hours")
    print(f"  ({total_steps} steps at ~{speed_estimate:.1f} steps/sec)")

    # ==========================================================================
    # CONFIGURE TRAINING
    # ==========================================================================
    training_args = create_training_config(
        output_dir=args.output_dir,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        max_seq_length=args.max_seq_length,
        device=device
    )

    # ==========================================================================
    # CREATE TRAINER
    # ==========================================================================
    trainer = create_trainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        training_args=training_args,
        use_galore=args.use_galore,
        galore_rank=args.galore_rank,
        galore_update_proj_gap=args.galore_update_proj_gap,
        galore_scale=args.galore_scale,
        learning_rate=args.learning_rate
    )

    # ==========================================================================
    # TRAIN!
    # ==========================================================================
    # This is where the actual learning happens. The trainer.train() call starts
    # the training loop. Depending on your data size and hardware, this could
    # take minutes to days.
    #
    # What you'll see in the output:
    #   - Loss: How wrong the model's predictions are (lower = better)
    #     The loss should generally decrease over time.
    #   - Eval loss: Same thing but on the held-out evaluation data.
    #     If train loss goes down but eval loss goes UP, you're overfitting.
    #   - Learning rate: Changes over time due to warmup and scheduling.
    #   - Steps/second: Training speed. With GaLore on 8B models, expect 1-2 it/s.
    #
    # Real-world analogy: Watching the loss decrease is like watching a student's
    # test scores improve over the semester. You want both homework scores (train
    # loss) and exam scores (eval loss) to improve together. If homework scores
    # improve but exam scores don't, the student is just memorizing homework
    # answers instead of understanding the material (overfitting).

    print("\n" + "="*70)
    print("STARTING TRAINING")
    if args.resume_from_checkpoint:
        print(f"  Resuming from checkpoint: {args.resume_from_checkpoint}")
    if args.use_galore:
        print(f"  Using GaLore for memory efficiency")
    print("="*70 + "\n")

    # If --resume-from-checkpoint was provided, pass that path to trainer.train().
    # The trainer will load the saved optimizer state, scheduler state, and model
    # weights from the checkpoint directory and continue training from that point.
    # If no checkpoint is specified, training starts fresh from the beginning.
    #
    # IMPORTANT with GaLore: When resuming, the GaLore projection matrices are
    # also loaded from the checkpoint. Make sure you use the same GaLore settings
    # (rank, update_proj_gap, scale) as the original training run, or the
    # projection matrices won't match and training will fail or produce poor results.
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    print("\n" + "="*70)
    print("TRAINING COMPLETE!")
    print("="*70 + "\n")

    # ==========================================================================
    # SAVE MODEL
    # ==========================================================================
    # Save the trained LoRA adapter weights and tokenizer.
    #
    # IMPORTANT: This only saves the LoRA adapter (~10-50MB), NOT the full base
    # model (~1-16GB). To use the model later, you need:
    #   1. Load the base model (Qwen 2.5 0.5B or Qwen3 8B)
    #   2. Load the LoRA adapter on top
    #
    # This is one of the big advantages of LoRA: your saved adapters are tiny.
    # You can train multiple specializations (MTG, cooking, coding) as separate
    # adapters and swap them onto the same base model.
    #
    # Real-world analogy: Like saving a "mod" for a video game instead of saving
    # a whole copy of the game. The mod file is small and changes the game's
    # behavior, but you still need the base game installed.

    print("Saving model...")

    model.save_pretrained(args.output_dir)      # Save LoRA adapter weights
    tokenizer.save_pretrained(args.output_dir)  # Save tokenizer (needed for inference)

    print(f"Model saved to {args.output_dir}")
    print(f"Adapter size: ~{trainable_params * 2 / 1024**2:.1f} MB")

    # ==========================================================================
    # TEST THE MODEL
    # ==========================================================================
    if not args.no_test:
        test_model(model, tokenizer, device)
    else:
        print("\nSkipping test generation (--no-test flag set)")

    # ==========================================================================
    # DONE!
    # ==========================================================================
    print("\nDone! Your fine-tuned model is ready to use.")
    print(f"\nTo use your model:")
    print(f"  from transformers import AutoModelForCausalLM")
    print(f"  from peft import PeftModel")
    print(f"  ")
    print(f"  base_model = AutoModelForCausalLM.from_pretrained('{args.model_name}')")
    print(f"  model = PeftModel.from_pretrained(base_model, '{args.output_dir}')")
    print(f"\nAdapter size: ~{trainable_params * 2 / 1024**2:.1f} MB")
    if args.use_galore:
        print(f"\nMemory efficiency achieved with GaLore!")
        print(f"  Without GaLore: Would need ~{trainable_params * 16 / 1024**3:.1f} GB")
        print(f"  With GaLore: Used ~{trainable_params * 4 / 1024**3:.1f} GB")


if __name__ == "__main__":
    main()
