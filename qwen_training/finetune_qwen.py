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

import argparse
import json
import os

import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTTrainer, SFTConfig


# =============================================================================
# GaLore IMPORTS AND SAFE GLOBALS REGISTRATION
# =============================================================================
try:
    from galore_torch import GaLoreAdamW, GaLoreAdamW8bit
    from galore_torch.galore_projector import GaLoreProjector
    GALORE_AVAILABLE = True
    torch.serialization.add_safe_globals([GaLoreProjector])
except ImportError:
    GaLoreAdamW = None
    GaLoreAdamW8bit = None
    GALORE_AVAILABLE = False


# =============================================================================
# CONSTANTS
# =============================================================================

# TARGET_MODULES defines which layers inside the model get LoRA adapters.
# q_proj = Query projection  ("What am I looking for?")
# k_proj = Key projection    ("What information do I have?")
# v_proj = Value projection   ("What's the actual content?")
# o_proj = Output projection  ("How do I combine everything?")
# This adds the MLP layers (gate_proj, up_proj, down_proj) which research shows significantly improves performance.

TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

DEFAULT_TEST_PROMPTS = [
    "What is machine learning?",
    "Explain photosynthesis simply.",
    "Write a short poem about the ocean.",
]


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    """Parse command-line arguments for fine-tuning configuration."""
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen models (0.5B to 8B+) with LoRA and optional GaLore"
    )

    # --- Dataset options ---
    parser.add_argument(
        "--dataset",
        type=str,
        choices=["sample", "hf", "file"],
        default="sample",
        help="Dataset source: 'sample' (built-in), 'hf' (Hugging Face), or 'file' (custom JSONL)"
    )
    parser.add_argument(
        "--hf-dataset",
        type=str,
        default="yahma/alpaca-cleaned",
        help="Hugging Face dataset name (when --dataset=hf)"
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default="data.jsonl",
        help="Path to JSONL data file (when --dataset=file)"
    )

    # --- Model and output ---
    parser.add_argument(
        "--model-name",
        type=str,
        default="Qwen/Qwen2.5-0.5B-Instruct",
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
        help="Directory to save fine-tuned model"
    )

    # --- LoRA configuration ---
    parser.add_argument(
        "--lora-r",
        type=int,
        default=16,
        help="LoRA rank (8-64, higher = more capacity)"
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="LoRA alpha (typically 2x the rank)"
    )
    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.05,
        help="LoRA dropout for regularization"
    )

    # --- GaLore configuration ---
    parser.add_argument(
        "--use-galore",
        action="store_true",
        help="Use GaLore optimizer for memory-efficient training (essential for 7B+ models)"
    )
    parser.add_argument(
        "--galore-rank",
        type=int,
        default=128,
        help="GaLore projection rank (64-256, higher = less compression)"
    )
    parser.add_argument(
        "--galore-update-proj-gap",
        type=int,
        default=200,
        help="Update GaLore projection every N steps (100-500 recommended)"
    )
    parser.add_argument(
        "--galore-scale",
        type=float,
        default=0.25,
        help="GaLore scaling factor (0.1-1.0, lower = more conservative)"
    )

    # --- Training configuration ---
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Batch size per device"
    )
    parser.add_argument(
        "--gradient-accumulation",
        type=int,
        default=4,
        help="Gradient accumulation steps"
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-4,
        help="Learning rate"
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=512,
        help="Maximum sequence length"
    )

    # --- Other options ---
    parser.add_argument(
        "--use-4bit",
        action="store_true",
        help="Use 4-bit quantization (essential for large models, ~75% memory reduction)"
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Skip test generation after training"
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        type=str,
        default=None,
        help="Path to a checkpoint directory to resume training from (e.g., ./output/checkpoint-200)"
    )

    return parser.parse_args()


# =============================================================================
# DATA
# =============================================================================

def create_sample_dataset():
    """Create a small sample instruction dataset for testing."""
    sample_data = [
        {
            "messages": [
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "assistant", "content": "The capital of France is Paris."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Explain quantum computing in simple terms."},
                {"role": "assistant", "content": "Quantum computing uses quantum mechanics principles to process information. Unlike classical computers that use bits (0 or 1), quantum computers use qubits that can be in multiple states simultaneously, allowing them to solve certain problems much faster."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Write a haiku about programming."},
                {"role": "assistant", "content": "Code flows like water\nBugs hide in silent shadows\nDebug brings the dawn"}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What are the three laws of robotics?"},
                {"role": "assistant", "content": "Isaac Asimov's Three Laws of Robotics are:\n1. A robot may not injure a human being or allow a human to come to harm\n2. A robot must obey human orders unless they conflict with the First Law\n3. A robot must protect its own existence unless it conflicts with the First or Second Law"}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "How do you make scrambled eggs?"},
                {"role": "assistant", "content": "Here's how to make scrambled eggs:\n1. Crack 2-3 eggs into a bowl\n2. Add a splash of milk and whisk\n3. Heat butter in a pan over medium heat\n4. Pour in eggs and gently stir with a spatula\n5. Cook until just set but still creamy\n6. Season with salt and pepper"}
            ]
        },
    ]

    expanded_data = sample_data * 20
    return Dataset.from_list(expanded_data)


def load_custom_dataset(file_path):
    """Load dataset from a JSONL file (JSON Lines format)."""
    with open(file_path, 'r') as f:
        data = [json.loads(line) for line in f]
    return Dataset.from_list(data)


def load_hf_dataset(dataset_name="yahma/alpaca-cleaned"):
    """Load a dataset from the Hugging Face Hub and convert to messages format."""
    dataset = load_dataset(dataset_name, split="train")

    def format_to_messages(example):
        return {
            "messages": [
                {"role": "user", "content": example["instruction"]},
                {"role": "assistant", "content": example["output"]}
            ]
        }

    return dataset.map(format_to_messages)


# =============================================================================
# MODEL
# =============================================================================

def detect_device():
    """Detect available hardware for training (XPU, CUDA, or CPU)."""
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        device = 'xpu'
        print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
    elif torch.cuda.is_available():
        device = 'cuda'
        print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
    else:
        device = 'cpu'
        print('Using CPU (training will be VERY slow!)')
        print('Consider using a GPU for training large models.')
    return device


def load_model(model_name, use_4bit=False, device='cpu', hf_token=None):
    """Load a pre-trained causal language model with optional 4-bit quantization."""
    print(f"Loading {model_name}...")
    if "8B" in model_name or "7B" in model_name:
        print("  (This is a large model - download may take several minutes)")

    quantization_config = None
    if use_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantization_config,
        device_map="auto" if device != 'xpu' else None,
        trust_remote_code=True,
        dtype=torch.bfloat16,
        token=hf_token,
    )

    if device == 'xpu':
        print("  Moving model to Intel XPU...")
        model = model.to(device)

    if use_4bit:
        print("  Preparing model for k-bit training...")
        model = prepare_model_for_kbit_training(model)

    print(f"Model loaded successfully!")
    return model


def load_tokenizer(model_name):
    """Load and configure the tokenizer for the specified model."""
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
    )
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def apply_lora(model, lora_r=16, lora_alpha=32, lora_dropout=0.05):
    """
    Apply LoRA (Low-Rank Adaptation) adapters to the model.

    Returns:
        tuple: (model_with_lora, trainable_params, total_params)
    """
    print("\nConfiguring LoRA...")

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=TARGET_MODULES,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)")
    print(f"Total parameters: {total_params:,}")

    return model, trainable_params, total_params


# =============================================================================
# TRAINER
# =============================================================================

def create_training_config(
    output_dir,
    num_epochs=3,
    batch_size=4,
    gradient_accumulation=4,
    learning_rate=2e-4,
    max_seq_length=512,
    device='cpu'
):
    """Create the SFTConfig training configuration."""
    print("\nConfiguring training...")

    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation,
        learning_rate=learning_rate,
        max_length=max_seq_length,
        optim="adamw_torch",
        weight_decay=0.01,
        warmup_ratio=0.03,
        eval_strategy="epoch",
        logging_steps=10,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=3,
        bf16=True if device in ['cuda', 'xpu'] else False,
        gradient_checkpointing=True,
        report_to="none",
        load_best_model_at_end=False,
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
    """Create the SFTTrainer with optional GaLore optimizer."""
    print("\nCreating trainer...")

    if use_galore:
        if not GALORE_AVAILABLE:
            raise RuntimeError(
                "GaLore requested but not installed! "
                "Install with: pip install galore-torch"
            )

        print(f"Using GaLore optimizer:")
        print(f"  Rank: {galore_rank}")
        print(f"  Update projection gap: {galore_update_proj_gap} steps")
        print(f"  Scale: {galore_scale}")

        galore_params = [p for p in model.parameters() if p.requires_grad]

        param_groups = [
            {
                'params': galore_params,
                'rank': galore_rank,
                'update_proj_gap': galore_update_proj_gap,
                'scale': galore_scale,
                'proj_type': 'std'
            }
        ]

        optimizer = GaLoreAdamW(
            param_groups,
            lr=learning_rate,
            weight_decay=0.01,
        )

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            processing_class=tokenizer,
            optimizers=(optimizer, None),
        )
    else:
        print("Using standard AdamW optimizer")

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            processing_class=tokenizer,
        )

    return trainer


# =============================================================================
# INFERENCE
# =============================================================================

def test_model(model, tokenizer, device, prompts=None):
    """Generate sample responses from the model to verify training worked."""
    if prompts is None:
        prompts = DEFAULT_TEST_PROMPTS

    print("\n" + "="*70)
    print("TESTING FINE-TUNED MODEL")
    print("="*70 + "\n")

    model.eval()

    for prompt in prompts:
        messages = [{"role": "user", "content": prompt}]

        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = tokenizer(text, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        if "<|im_start|>assistant" in response:
            response = response.split("<|im_start|>assistant")[-1].strip()

        print(f"User: {prompt}")
        print(f"Assistant: {response}\n")
        print("-" * 70 + "\n")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point for fine-tuning."""

    args = parse_args()

    # Validate GaLore availability
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

    # Print configuration
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

    if "8B" in args.model_name or "7B" in args.model_name:
        print("WARNING: You're training a large model (7B-8B parameters)")
        print("   Expected training time on consumer GPU: 48-72 hours")
        if not args.use_galore:
            print("   You should probably use --use-galore for memory efficiency!")
        if not args.use_4bit:
            print("   You should use --use-4bit for large models!")
        print()

    # Detect device
    device = detect_device()

    # Load model and tokenizer
    print("\nLoading model and tokenizer...")

    model = load_model(
        model_name=args.model_name,
        use_4bit=args.use_4bit,
        device=device,
        hf_token=args.hf_token
    )

    tokenizer = load_tokenizer(args.model_name)

    # Apply LoRA
    model, trainable_params, total_params = apply_lora(
        model,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout
    )

    # Prepare dataset
    print("\nPreparing dataset...")

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

    train_test_split = train_dataset.train_test_split(test_size=0.1)
    train_dataset = train_test_split["train"]
    eval_dataset = train_test_split["test"]

    print(f"Training examples: {len(train_dataset)}")
    print(f"Evaluation examples: {len(eval_dataset)}")

    steps_per_epoch = len(train_dataset) // (args.batch_size * args.gradient_accumulation)
    total_steps = steps_per_epoch * args.epochs

    if "8B" in args.model_name or "7B" in args.model_name:
        if args.use_galore:
            speed_estimate = 1.4
        else:
            speed_estimate = 0.5
    elif "1.5B" in args.model_name or "3B" in args.model_name:
        speed_estimate = 2.0
    else:
        speed_estimate = 3.0

    estimated_time_hours = total_steps / speed_estimate / 3600
    print(f"\nEstimated training time: ~{estimated_time_hours:.1f} hours")
    print(f"  ({total_steps} steps at ~{speed_estimate:.1f} steps/sec)")

    # Configure training
    training_args = create_training_config(
        output_dir=args.output_dir,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        max_seq_length=args.max_seq_length,
        device=device
    )

    # Create trainer
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

    # Train
    print("\n" + "="*70)
    print("STARTING TRAINING")
    if args.resume_from_checkpoint:
        print(f"  Resuming from checkpoint: {args.resume_from_checkpoint}")
    if args.use_galore:
        print(f"  Using GaLore for memory efficiency")
    print("="*70 + "\n")

    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    print("\n" + "="*70)
    print("TRAINING COMPLETE!")
    print("="*70 + "\n")

    # Save model
    print("Saving model...")

    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    print(f"Model saved to {args.output_dir}")
    print(f"Adapter size: ~{trainable_params * 2 / 1024**2:.1f} MB")

    # Test the model
    if not args.no_test:
        test_model(model, tokenizer, device)
    else:
        print("\nSkipping test generation (--no-test flag set)")

    # Done
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
