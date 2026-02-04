"""
Fine-tune Qwen 2.5 0.5B Instruct with LoRA
This script fine-tunes the Qwen 2.5 0.5B model on instruction-following data
using LoRA (Low-Rank Adaptation) for memory-efficient training.

Usage:
    # Use sample data
    python finetune_qwen.py --dataset sample
    
    # Use Hugging Face dataset
    python finetune_qwen.py --dataset hf --hf-dataset yahma/alpaca-cleaned
    
    # Use custom JSONL file
    python finetune_qwen.py --dataset file --data-file my_data.jsonl
    
    # Customize training
    python finetune_qwen.py --dataset sample --epochs 5 --batch-size 8 --lora-r 32
"""

import json
import torch
import argparse
from datasets import Dataset, load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
import os

# ============================================================================
# COMMAND LINE ARGUMENTS
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen 2.5 0.5B with LoRA on instruction data"
    )
    
    # Dataset options
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
    
    # Model and output
    parser.add_argument(
        "--model-name",
        type=str,
        default="Qwen/Qwen2.5-0.5B-Instruct",
        help="Base model to fine-tune"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./qwen-finetuned",
        help="Directory to save fine-tuned model"
    )
    
    # LoRA configuration
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
    
    # Training configuration
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
    
    # Other options
    parser.add_argument(
        "--use-4bit",
        action="store_true",
        help="Use 4-bit quantization (may not work on XPU)"
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Skip test generation after training"
    )
    
    return parser.parse_args()

args = parse_args()

# ============================================================================
# CONFIGURATION (from command-line args)
# ============================================================================

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
print(f"  Learning rate={args.learning_rate}")
print(f"  Max sequence length={args.max_seq_length}")
print(f"  Use 4-bit quantization: {args.use_4bit}")
print("="*70 + "\n")

# Set configuration from args
MODEL_NAME = args.model_name
OUTPUT_DIR = args.output_dir
LORA_R = args.lora_r
LORA_ALPHA = args.lora_alpha
LORA_DROPOUT = args.lora_dropout
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]
NUM_EPOCHS = args.epochs
BATCH_SIZE = args.batch_size
GRADIENT_ACCUMULATION = args.gradient_accumulation
LEARNING_RATE = args.learning_rate
MAX_SEQ_LENGTH = args.max_seq_length
USE_4BIT = args.use_4bit

# ============================================================================
# DEVICE DETECTION
# ============================================================================

if hasattr(torch, 'xpu') and torch.xpu.is_available():
    device = 'xpu'
    print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
    # Note: 4-bit quantization might not work on XPU yet
    # If you get errors, set USE_4BIT = False
elif torch.cuda.is_available():
    device = 'cuda'
    print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
else:
    device = 'cpu'
    print('Using CPU (training will be slow!)')

# ============================================================================
# CREATE SAMPLE INSTRUCTION DATASET
# ============================================================================

def create_sample_dataset():
    """
    Create a small sample instruction dataset for demonstration.
    Replace this with your own dataset!
    
    Format: List of conversations with 'messages' field containing role/content pairs
    """
    
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
    
    # Multiply the dataset to have more training examples
    # In practice, you'd want 100s or 1000s of examples
    expanded_data = sample_data * 20  # Creates 100 examples
    
    return Dataset.from_list(expanded_data)

# You can also load from a file:
def load_custom_dataset(file_path):
    """Load dataset from a JSONL file"""
    with open(file_path, 'r') as f:
        data = [json.loads(line) for line in f]
    return Dataset.from_list(data)

# Or use a dataset from Hugging Face:
def load_hf_dataset(dataset_name="yahma/alpaca-cleaned"):
    """
    Load a dataset from Hugging Face Hub
    Popular instruction datasets:
    - yahma/alpaca-cleaned
    - vicgalle/alpaca-gpt4
    - tatsu-lab/alpaca
    """
    dataset = load_dataset(dataset_name, split="train")
    
    # Convert to the format Qwen expects (with 'messages' field)
    def format_to_messages(example):
        return {
            "messages": [
                {"role": "user", "content": example["instruction"]},
                {"role": "assistant", "content": example["output"]}
            ]
        }
    
    return dataset.map(format_to_messages)

# ============================================================================
# LOAD MODEL AND TOKENIZER
# ============================================================================

print("\nLoading model and tokenizer...")

# Configure quantization if enabled
quantization_config = None
if USE_4BIT and device in ['cuda', 'cpu']:  # XPU might not support 4-bit yet
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

# Load model
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=quantization_config,
    device_map="auto" if device != 'xpu' else None,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
)

# If using XPU, manually move model
if device == 'xpu':
    model = model.to(device)

# Prepare model for k-bit training if using quantization
if USE_4BIT and device in ['cuda', 'cpu']:
    model = prepare_model_for_kbit_training(model)

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"  # Important for generation

print(f"Model loaded on {device}")

# ============================================================================
# CONFIGURE LORA
# ============================================================================

print("\nConfiguring LoRA...")

lora_config = LoraConfig(
    r=LORA_R,
    lora_alpha=LORA_ALPHA,
    target_modules=TARGET_MODULES,
    lora_dropout=LORA_DROPOUT,
    bias="none",
    task_type="CAUSAL_LM",
)

# Apply LoRA to the model
model = get_peft_model(model, lora_config)

# Print trainable parameters
trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
total_params = sum(p.numel() for p in model.parameters())
print(f"Trainable parameters: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)")
print(f"Total parameters: {total_params:,}")

# ============================================================================
# PREPARE DATASET
# ============================================================================

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

# Split into train and eval
train_test_split = train_dataset.train_test_split(test_size=0.1)
train_dataset = train_test_split["train"]
eval_dataset = train_test_split["test"]

print(f"Training examples: {len(train_dataset)}")
print(f"Evaluation examples: {len(eval_dataset)}")

# ============================================================================
# CONFIGURE TRAINING
# ============================================================================

print("\nConfiguring training...")

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRADIENT_ACCUMULATION,
    learning_rate=LEARNING_RATE,
    max_seq_length=MAX_SEQ_LENGTH,
    
    # Optimization
    optim="adamw_torch",
    weight_decay=0.01,
    warmup_ratio=0.03,
    
    # Evaluation and logging
    eval_strategy="steps",
    eval_steps=50,
    logging_steps=10,
    save_strategy="steps",
    save_steps=100,
    save_total_limit=2,
    
    # Performance
    bf16=True if device in ['cuda', 'xpu'] else False,
    gradient_checkpointing=True,
    
    # Other
    report_to="none",  # Can use "wandb" for logging
    load_best_model_at_end=True,
)

# ============================================================================
# CREATE TRAINER
# ============================================================================

print("\nCreating trainer...")

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    tokenizer=tokenizer,
    packing=False,  # Don't pack multiple examples together
)

# ============================================================================
# TRAIN!
# ============================================================================

print("\n" + "="*70)
print("STARTING TRAINING")
print("="*70 + "\n")

trainer.train()

print("\n" + "="*70)
print("TRAINING COMPLETE!")
print("="*70 + "\n")

# ============================================================================
# SAVE MODEL
# ============================================================================

print("Saving model...")

# Save the LoRA adapter
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print(f"Model saved to {OUTPUT_DIR}")

# ============================================================================
# TEST THE MODEL
# ============================================================================

if not args.no_test:
    print("\n" + "="*70)
    print("TESTING FINE-TUNED MODEL")
    print("="*70 + "\n")

    model.eval()

    test_prompts = [
        "What is machine learning?",
        "Explain photosynthesis simply.",
        "Write a short poem about the ocean.",
    ]

    for prompt in test_prompts:
        # Format as conversation
        messages = [{"role": "user", "content": prompt}]
        
        # Apply chat template
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        # Tokenize
        inputs = tokenizer(text, return_tensors="pt").to(device)
        
        # Generate
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )
        
        # Decode
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract just the assistant's response
        if "<|im_start|>assistant" in response:
            response = response.split("<|im_start|>assistant")[-1].strip()
        
        print(f"User: {prompt}")
        print(f"Assistant: {response}\n")
        print("-" * 70 + "\n")
else:
    print("\nSkipping test generation (--no-test flag set)")

print("\nDone! Your fine-tuned model is ready to use.")
print(f"Load it with: model = AutoModelForCausalLM.from_pretrained('{OUTPUT_DIR}')")