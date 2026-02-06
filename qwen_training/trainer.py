"""
Training configuration and trainer creation.

This module handles creating the training configuration (SFTConfig) and
instantiating the trainer with optional GaLore optimizer support.

The SFTTrainer ties everything together: model, data, tokenizer, and config.
It handles the entire training loop:
  1. Tokenize each batch of examples using the chat template
  2. Feed tokens through the model to get predictions
  3. Calculate the loss (how wrong the predictions were)
  4. Backpropagate to compute gradients (which direction to adjust weights)
  5. Update the LoRA weights using the optimizer
  6. Repeat for all batches across all epochs

Real-world analogy: The trainer is like a personal coach. You give them
the athlete (model), the training plan (config), and the exercises (data),
and they handle running each drill, tracking progress, and adjusting
intensity. With GaLore, you're giving the coach special equipment (the
projection matrices) that makes the workouts more memory-efficient.
"""

from trl import SFTTrainer, SFTConfig
from .model import GALORE_AVAILABLE, GaLoreAdamW


def create_training_config(
    output_dir,
    num_epochs=3,
    batch_size=4,
    gradient_accumulation=4,
    learning_rate=2e-4,
    max_seq_length=512,
    device='cpu'
):
    """
    Create the training configuration (SFTConfig).

    SFTConfig (Supervised Fine-Tuning Config) bundles all training settings
    into one object. This is the "control panel" for the training loop.

    Args:
        output_dir: Directory to save checkpoints and final model.
        num_epochs: Number of training epochs.
        batch_size: Examples per step (per GPU).
        gradient_accumulation: Steps to accumulate before updating.
        learning_rate: Step size for weight updates.
        max_seq_length: Max tokens per example.
        device: Training device ('cuda', 'xpu', or 'cpu').

    Returns:
        SFTConfig: The training configuration object.
    """
    print("\nConfiguring training...")

    training_args = SFTConfig(
        # Where to save checkpoints and the final model
        output_dir=output_dir,

        # --- Core training settings ---
        num_train_epochs=num_epochs,               # How many times to go through all data
        per_device_train_batch_size=batch_size,     # Examples per step (per GPU)
        per_device_eval_batch_size=batch_size,      # Examples per eval step
        gradient_accumulation_steps=gradient_accumulation,  # Accumulate before updating
        learning_rate=learning_rate,               # Step size for weight updates
        max_length=max_seq_length,                 # Max tokens per example (truncates longer ones)

        # --- Optimizer settings ---
        # When using GaLore, we'll override the optimizer manually. For now, we
        # specify adamw_torch as a placeholder. AdamW is the standard optimizer
        # for transformers. "W" means it includes weight decay, which penalizes
        # large weights to prevent overfitting.
        #
        # Real-world analogy: The optimizer is like the navigation system telling
        # you which direction to adjust. Adam is a smart navigator that:
        # - Remembers which direction worked well recently (momentum)
        # - Adjusts step size per-parameter (some weights need big steps, some small)
        # - Weight decay adds "friction" that gently pulls weights toward zero,
        #   preventing any single weight from dominating.
        #
        # With GaLore, we replace AdamW with GaLoreAdamW, which adds gradient
        # projection for memory efficiency. The core algorithm is still Adam.
        optim="adamw_torch",  # Will be overridden if using GaLore

        # Weight decay coefficient. 0.01 means "add a tiny penalty proportional
        # to the size of each weight." This is a form of regularization that
        # prevents overfitting.
        weight_decay=0.01,

        # Warmup: start with a very small learning rate and gradually increase
        # it during the first 3% of training. This prevents the model from making
        # wild updates early on when gradients are noisy.
        #
        # Real-world analogy: Like warming up before exercise -- you don't sprint
        # at full speed immediately, you ease into it. With large models, starting
        # with a high learning rate can cause training instability or divergence.
        # Warmup gives the model time to "find its footing" before ramping up.
        warmup_ratio=0.03,

        # --- Evaluation and logging ---
        # These control how often we check progress and save snapshots.

        # eval_strategy="epoch" means "evaluate at the end of each epoch."
        # This is a good balance -- frequent enough to catch problems, but not
        # so frequent that it slows training. For very large datasets (100k+
        # examples), you might want "steps" instead to evaluate more frequently.
        eval_strategy="epoch",

        # logging_steps controls how often to print training loss to the console.
        # Every 10 steps means you'll see updates frequently enough to monitor
        # progress without flooding the screen.
        logging_steps=10,

        # save_strategy="steps" means save a checkpoint every N training steps.
        # This is critical for long training runs (48+ hours for 8B models) because:
        # 1. If training crashes, you can resume from the last checkpoint
        # 2. You can stop training early if you see the model is already good
        # 3. Saving checkpoints forces memory cleanup, preventing memory leaks
        save_strategy="steps",
        save_steps=200,        # Save every 200 steps

        # save_total_limit=3 means "keep only the 3 most recent checkpoints."
        # Each checkpoint can be 200MB-1GB depending on model size, so this
        # prevents filling your disk. Older checkpoints are automatically deleted.
        #
        # Real-world analogy: Like video game auto-saves that only keep the last
        # 3 saves. You don't need every single checkpoint from the entire training
        # run -- just recent ones in case you need to roll back.
        save_total_limit=3,

        # --- Performance flags ---
        # bf16=True tells PyTorch to use bfloat16 (16-bit) math on the GPU.
        # This is faster than float32 and uses half the memory, with minimal
        # accuracy loss. Intel Arc GPUs and NVIDIA Ampere+ have excellent bfloat16
        # support.
        #
        # We only enable this for GPU backends (CUDA, XPU). CPU training should
        # stay in float32 for accuracy.
        bf16=True if device in ['cuda', 'xpu'] else False,

        # Gradient checkpointing is a memory-saving technique. Normally, all
        # intermediate computations (activations) are kept in memory for the
        # backward pass. With checkpointing, some are discarded and recomputed
        # when needed. This trades ~30% compute time for ~40% memory savings.
        #
        # Real-world analogy: Like a GPS that only remembers major intersections
        # instead of every meter of the route. If you need to backtrack, you
        # drive back to the last intersection and recalculate from there. Slightly
        # slower, but you don't need to remember the entire route at once.
        #
        # This is ESSENTIAL for training large models on consumer GPUs. Without
        # it, 8B models won't fit even with 4-bit + GaLore.
        gradient_checkpointing=True,

        # --- Other settings ---
        # report_to="none" means don't send metrics to external tracking services.
        # If you want beautiful training dashboards, change to "wandb" (Weights &
        # Biases) or "tensorboard" and they'll automatically log everything.
        report_to="none",

        # load_best_model_at_end=False means "use the last checkpoint as the final
        # model, not the one with lowest eval loss." For most fine-tuning tasks,
        # the last checkpoint is fine. If you're doing heavy hyperparameter tuning
        # or have overfitting concerns, set this to True (but it requires eval_strategy
        # to match save_strategy).
        load_best_model_at_end=False,

        # packing=False means "don't concatenate multiple short examples into one
        # sequence." Packing can speed up training by filling sequences to max_length
        # more efficiently, but it can confuse the model about conversation boundaries
        # in chat data. We keep it False for cleaner training.
        packing=False,
    )

    return training_args


def create_trainer(
    model,
    tokenizer,
    train_dataset,
    eval_dataset,
    training_args,
    use_galore=False,
    galore_rank=128,
    galore_update_proj_gap=200,
    galore_scale=0.25,
    learning_rate=2e-4
):
    """
    Create the SFTTrainer with optional GaLore optimizer.

    If using GaLore, we manually create a custom optimizer that wraps the
    standard Adam optimizer with gradient projection. This optimizer gets
    passed to the trainer, overriding the default one.

    Args:
        model: The model with LoRA adapters applied.
        tokenizer: The tokenizer for the model.
        train_dataset: Training dataset.
        eval_dataset: Evaluation dataset.
        training_args: SFTConfig with training settings.
        use_galore: Whether to use GaLore optimizer.
        galore_rank: GaLore projection rank.
        galore_update_proj_gap: Steps between projection updates.
        galore_scale: GaLore scaling factor.
        learning_rate: Learning rate for the optimizer.

    Returns:
        SFTTrainer: The configured trainer ready for training.
    """
    print("\nCreating trainer...")

    if use_galore:
        if not GALORE_AVAILABLE:
            raise RuntimeError(
                "GaLore requested but not installed! "
                "Install with: pip install galore-torch"
            )

        # GaLore optimizer path
        print(f"Using GaLore optimizer:")
        print(f"  Rank: {galore_rank}")
        print(f"  Update projection gap: {galore_update_proj_gap} steps")
        print(f"  Scale: {galore_scale}")

        # Create GaLoreAdamW optimizer.
        # This is a drop-in replacement for the standard AdamW optimizer,
        # but with gradient low-rank projection added.
        #
        # How it works:
        # 1. Compute gradients normally during backpropagation
        # 2. Project gradients to a low-rank subspace (rank=128 or 256)
        # 3. Accumulate optimizer states (momentum, variance) in this low-rank space
        # 4. Project back to full space when updating weights
        #
        # Memory savings: Instead of storing optimizer states for all 8B parameters
        # (~16GB), we only store them for the projected space (~1GB with rank 128).
        # That's a 94% reduction in optimizer memory!
        #
        # The projection matrices are updated every `update_proj_gap` steps to
        # track the changing gradient distribution. Think of it like recalibrating
        # your compression algorithm periodically to adapt to new data.

        # NEW API: GaLore now requires parameter groups where GaLore-specific params
        # (rank, update_proj_gap, scale, proj_type) are specified per group.
        # We apply GaLore to all trainable parameters (LoRA adapters).
        galore_params = [p for p in model.parameters() if p.requires_grad]

        param_groups = [
            {
                'params': galore_params,
                'rank': galore_rank,
                'update_proj_gap': galore_update_proj_gap,
                'scale': galore_scale,
                'proj_type': 'std'  # Standard projection type
            }
        ]

        optimizer = GaLoreAdamW(
            param_groups,           # Parameter groups with GaLore config
            lr=learning_rate,       # Learning rate
            weight_decay=0.01,      # L2 regularization
        )

        # Create trainer with the custom GaLore optimizer.
        # The optimizers=(optimizer, None) syntax means:
        #   - Use 'optimizer' for the optimizer
        #   - Use None for the learning rate scheduler (let the trainer create one)
        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            processing_class=tokenizer,
            optimizers=(optimizer, None),  # Pass our custom GaLore optimizer
        )
    else:
        # Standard training path (no GaLore)
        # The trainer will create a regular AdamW optimizer based on training_args.
        print("Using standard AdamW optimizer")

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            processing_class=tokenizer,
        )

    return trainer
