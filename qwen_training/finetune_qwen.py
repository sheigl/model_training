"""
Fine-tune Qwen 2.5 0.5B Instruct with LoRA
============================================

WHAT THIS SCRIPT DOES:
    This script takes a pre-trained language model (Qwen 2.5 0.5B) and teaches it
    new behavior using your custom data. This is called "fine-tuning."

    Real-world analogy: Imagine hiring someone who already has a college degree
    (the pre-trained model). They know how to read, write, and reason. Now you're
    giving them specialized on-the-job training (fine-tuning) to become an expert
    in YOUR specific field -- in this case, Magic: The Gathering.

WHY LoRA (Low-Rank Adaptation)?
    Normally, fine-tuning means updating ALL of a model's parameters (weights).
    For a 0.5 billion parameter model, that requires a LOT of GPU memory.

    LoRA is a shortcut: instead of rewriting the entire textbook, you add small
    sticky notes (adapters) to specific pages. The original book stays the same,
    and the sticky notes teach the new behavior. This uses ~10x less memory.

    Real-world analogy: Instead of rebuilding an entire car engine to go faster,
    you bolt on a turbocharger. The engine stays the same, but the turbo (LoRA
    adapter) changes its behavior. You can even swap turbos (adapters) for
    different tasks without touching the engine.

WHAT YOU NEED:
    - A GPU (this script supports Intel Arc via XPU, NVIDIA via CUDA, or CPU)
    - Training data in JSONL format (conversations with user/assistant messages)
    - The dependencies in pyproject.toml installed via: uv sync

Usage:
    # Use sample data (for testing that everything works)
    python finetune_qwen.py --dataset sample

    # Use Hugging Face dataset (community-shared data)
    python finetune_qwen.py --dataset hf --hf-dataset yahma/alpaca-cleaned

    # Use your custom JSONL file (what we'll do with MTG data)
    python finetune_qwen.py --dataset file --data-file my_data.jsonl

    # Customize training hyperparameters
    python finetune_qwen.py --dataset sample --epochs 5 --batch-size 8 --lora-r 32
"""

# =============================================================================
# IMPORTS
# =============================================================================
# Each import brings in a library (a collection of pre-written code) that we need.
# Think of imports like tools in a toolbox -- you grab what you need before starting work.

# json: Reads and writes JSON files (the format our training data is stored in).
# Real-world analogy: JSON is like a standardized shipping container -- everyone
# agrees on the format so data can move between programs easily.
import json

# torch (PyTorch): The deep learning framework that does all the math.
# This is the "engine" that actually trains the model. It handles tensors (multi-
# dimensional arrays of numbers), automatic differentiation (calculating how to
# improve the model), and GPU acceleration.
# Real-world analogy: PyTorch is like the physics engine in a video game -- it
# handles all the complex calculations under the hood so you can focus on the
# game design (model architecture and training strategy).
import torch

# argparse: Lets users pass settings via command-line flags (like --epochs 5).
# This way you don't have to edit the script every time you want to change something.
# Real-world analogy: argparse is like the settings menu in a game -- you configure
# options without modifying the game's source code.
import argparse

# datasets: Hugging Face library for loading and manipulating training data.
# Dataset is a table-like structure (think spreadsheet) optimized for ML workflows.
# load_dataset can download community-shared datasets from the Hugging Face Hub.
from datasets import Dataset, load_dataset

# transformers: Hugging Face library for working with pre-trained language models.
# - AutoModelForCausalLM: Loads a "causal language model" (a model that predicts
#   the next word, like GPT/Qwen). "Auto" means it auto-detects the architecture.
# - AutoTokenizer: Loads the tokenizer, which converts text into numbers the model
#   understands. Each model has its own tokenizer (its own "dictionary").
#   Real-world analogy: A tokenizer is like a translator that converts English
#   sentences into a secret code of numbers. The model only speaks "number code,"
#   so the tokenizer translates back and forth.
# - TrainingArguments: Configuration object for training settings (imported but
#   we actually use SFTConfig from trl instead, which extends it).
# - BitsAndBytesConfig: Settings for model quantization (compressing the model
#   to use less memory by using fewer bits per number).
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig
)

# peft: "Parameter-Efficient Fine-Tuning" library. This is the LoRA implementation.
# - LoraConfig: Settings for LoRA (rank, which layers to target, etc.)
# - get_peft_model: Wraps a normal model with LoRA adapters
# - prepare_model_for_kbit_training: Prepares a quantized model for training
#   (fixes numerical stability issues that arise from using compressed numbers)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# trl: "Transformer Reinforcement Learning" library. Despite the name, it's used
# for supervised fine-tuning (SFT) too.
# - SFTTrainer: A trainer specifically designed for instruction-tuning LLMs.
#   It handles the chat template formatting, tokenization, and training loop.
# - SFTConfig: Training configuration that extends TrainingArguments with SFT-
#   specific options like max_length and packing.
from trl import SFTTrainer, SFTConfig

# os: Operating system utilities (we use it to check if files exist).
import os

# =============================================================================
# COMMAND LINE ARGUMENTS
# =============================================================================
# This section defines all the "knobs and dials" you can adjust when running
# the script. Each argument has a name, type, default value, and help text.
#
# Real-world analogy: Think of these like the controls on a mixing board in a
# recording studio. Each slider controls a different aspect of the sound (training).
# The defaults give you a reasonable starting point, but you can tweak them.

def parse_args():
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen 2.5 0.5B with LoRA on instruction data"
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
        # downloads the model weights (~1GB) from huggingface.co. After that,
        # it uses the cached version.
        # "Instruct" means it's already been trained to follow instructions.
        # We're fine-tuning it further to specialize in MTG.
        help="Base model to fine-tune"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./qwen-finetuned",
        # Where to save the trained LoRA adapter weights. This directory will
        # contain the adapter files (small, ~10MB) -- NOT a full copy of the model.
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
        # 2e-4 is a well-tested default for LoRA fine-tuning.
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
        # You lose some quality but it takes way less storage. For the 0.5B
        # model this isn't strictly necessary, but for larger models it's essential.
        #
        # NOTE: 4-bit quantization may not work on Intel XPU (Arc GPUs) yet.
        # The bitsandbytes library primarily supports NVIDIA CUDA GPUs.
        help="Use 4-bit quantization (may not work on XPU)"
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
        #   - Training can take hours. If it crashes, you don't lose all progress.
        #   - You can stop training, adjust hyperparameters, and continue.
        #   - Lets you extend training (e.g., train 3 more epochs from where you
        #     stopped) without repeating already-completed work.
        #
        # NOTE: The checkpoint directory must match the same model and LoRA config
        # you're using. You can't resume a checkpoint from a different model.
        help="Path to a checkpoint directory to resume training from (e.g., ./output/checkpoint-200)"
    )

    return parser.parse_args()

# Parse command line arguments immediately when the script starts.
# This makes all the user's settings available in the 'args' object.
# Example: args.epochs gives us the number of epochs they chose.
args = parse_args()

# =============================================================================
# CONFIGURATION (from command-line args)
# =============================================================================
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
print(f"  Learning rate={args.learning_rate}")
print(f"  Max sequence length={args.max_seq_length}")
print(f"  Use 4-bit quantization: {args.use_4bit}")
if args.resume_from_checkpoint:
    print(f"  Resume from checkpoint: {args.resume_from_checkpoint}")
print("="*70 + "\n")

# Transfer command-line args to uppercase constants for clarity in the rest
# of the script. This is a style convention: UPPERCASE = "don't change these
# after this point." Think of them as the final settings locked in.
MODEL_NAME = args.model_name
OUTPUT_DIR = args.output_dir
LORA_R = args.lora_r
LORA_ALPHA = args.lora_alpha
LORA_DROPOUT = args.lora_dropout

# TARGET_MODULES defines which layers inside the model get LoRA adapters.
# These are the "attention" layers -- the part of the transformer that decides
# which words to pay attention to when generating the next word.
#
# q_proj = Query projection  ("What am I looking for?")
# k_proj = Key projection    ("What information do I have?")
# v_proj = Value projection   ("What's the actual content?")
# o_proj = Output projection  ("How do I combine everything?")
#
# Real-world analogy: In a classroom, attention is like:
#   q_proj: The student's question ("I need info about Lightning Bolt")
#   k_proj: The textbook index ("Chapter 3 covers red spells")
#   v_proj: The actual content ("Lightning Bolt deals 3 damage")
#   o_proj: The student's notes ("Lightning Bolt = 3 damage, 1 mana, instant")
#
# We add LoRA adapters to all 4 of these because they're the most impactful
# layers for changing the model's behavior. Other layers (like feed-forward
# layers) could also be targeted, but attention layers give the best bang
# for the buck.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]

NUM_EPOCHS = args.epochs
BATCH_SIZE = args.batch_size
GRADIENT_ACCUMULATION = args.gradient_accumulation
LEARNING_RATE = args.learning_rate
MAX_SEQ_LENGTH = args.max_seq_length
USE_4BIT = args.use_4bit

# =============================================================================
# DEVICE DETECTION
# =============================================================================
# Figure out what hardware we have available for training.
# GPUs (Graphics Processing Units) are MUCH faster than CPUs for training
# because they can do thousands of math operations in parallel.
#
# Real-world analogy: A CPU is like one very smart mathematician who solves
# problems one at a time. A GPU is like a stadium full of average calculators
# who each solve one tiny piece of the problem simultaneously. Deep learning
# is mostly "lots of simple math operations," so the GPU wins big.
#
# This script supports three backends:
#   xpu  = Intel Arc GPUs (like your B580) via Intel's oneAPI/IPEX
#   cuda = NVIDIA GPUs (the most common for ML)
#   cpu  = No GPU -- works but is extremely slow for training

if hasattr(torch, 'xpu') and torch.xpu.is_available():
    # torch.xpu is Intel's GPU backend, added via Intel Extension for PyTorch.
    # hasattr() checks if the 'xpu' attribute exists in torch (it won't if
    # you installed regular PyTorch without Intel's XPU support).
    device = 'xpu'
    print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
    # Note: 4-bit quantization might not work on XPU yet because the
    # bitsandbytes library was written for NVIDIA GPUs.
elif torch.cuda.is_available():
    device = 'cuda'
    print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
else:
    device = 'cpu'
    print('Using CPU (training will be slow!)')

# =============================================================================
# DATASET LOADING FUNCTIONS
# =============================================================================
# These functions handle loading training data from different sources.
# All of them produce data in the same format: a list of conversations
# where each conversation has a "messages" field containing role/content pairs.
#
# This format looks like:
#   {"messages": [
#       {"role": "user", "content": "What does Lightning Bolt do?"},
#       {"role": "assistant", "content": "Lightning Bolt deals 3 damage..."}
#   ]}
#
# Real-world analogy: This is like a script for a play. Each message has a
# character (role) and their line (content). The model learns to play the
# "assistant" character by studying many example scripts.

def create_sample_dataset():
    """
    Create a small sample instruction dataset for testing.

    This is a toy dataset just to verify the training pipeline works end-to-end.
    It contains only 5 unique examples, duplicated 20 times to reach 100.

    In real training, you'd want hundreds or thousands of UNIQUE examples.
    Using duplicates like this is only for pipeline testing -- the model won't
    learn much from seeing the same 5 things over and over.

    Real-world analogy: This is like a "Hello World" program. It doesn't do
    anything useful, but it proves your setup works.
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

    # Multiply the dataset to have more training examples.
    # This is a HACK for testing only. Real training data should be unique.
    # Duplicating data like this leads to overfitting (memorization).
    expanded_data = sample_data * 20  # 5 unique * 20 = 100 total examples

    # Dataset.from_list() converts a Python list of dictionaries into a
    # Hugging Face Dataset object, which is optimized for ML workflows
    # (efficient batching, shuffling, memory mapping, etc.).
    return Dataset.from_list(expanded_data)


def load_custom_dataset(file_path):
    """
    Load dataset from a JSONL file (JSON Lines format).

    JSONL = one JSON object per line. Each line is an independent record.
    This is the format our MTG data conversion scripts output.

    Example file content:
        {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
        {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

    Real-world analogy: JSONL is like a CSV file but more flexible. Each line
    is a self-contained record, so you can process the file one line at a time
    without loading everything into memory (though here we load it all).
    """
    with open(file_path, 'r') as f:
        # List comprehension: for each line in the file, parse it as JSON.
        # json.loads() converts a JSON string into a Python dictionary.
        data = [json.loads(line) for line in f]
    return Dataset.from_list(data)


def load_hf_dataset(dataset_name="yahma/alpaca-cleaned"):
    """
    Load a dataset from the Hugging Face Hub.

    The HF Hub is like GitHub but for ML datasets and models. Community
    members upload datasets that anyone can use. This function downloads
    one and converts it to our expected format.

    Popular instruction datasets:
    - yahma/alpaca-cleaned: Cleaned version of Stanford Alpaca's training data
    - vicgalle/alpaca-gpt4: Alpaca data generated with GPT-4 (higher quality)
    - tatsu-lab/alpaca: The original Stanford Alpaca dataset

    Real-world analogy: The HF Hub is like a public library of training data.
    Instead of gathering all the data yourself, you can borrow pre-made datasets.
    """
    # load_dataset downloads and caches the dataset. split="train" means we
    # only want the training portion (some datasets have train/test/validation).
    dataset = load_dataset(dataset_name, split="train")

    # Alpaca-format datasets have "instruction" and "output" fields, but our
    # trainer expects "messages" format. This function converts between them.
    # It's like translating a book from one language to another -- same content,
    # different structure.
    def format_to_messages(example):
        return {
            "messages": [
                {"role": "user", "content": example["instruction"]},
                {"role": "assistant", "content": example["output"]}
            ]
        }

    # dataset.map() applies a function to every row. This is much faster than
    # a Python for-loop because it uses optimized C code under the hood.
    return dataset.map(format_to_messages)

# =============================================================================
# LOAD MODEL AND TOKENIZER
# =============================================================================
# This is where we download (or load from cache) the actual neural network
# and its tokenizer. This is the "brain" we're going to teach.
#
# The model and tokenizer always come as a pair:
#   - Tokenizer: converts text -> numbers (and back)
#   - Model: takes numbers in, produces numbers out
#
# Real-world analogy: The tokenizer is like a Morse code operator who translates
# English into dots and dashes. The model is the telegraph machine that processes
# those dots and dashes. You need both to communicate.

print("\nLoading model and tokenizer...")

# --- Quantization configuration ---
# Quantization reduces the precision of the model's numbers to save memory.
# Normally, each model parameter is a 16-bit floating point number (bfloat16).
# 4-bit quantization squeezes each number into just 4 bits.
#
# Math: 0.5B parameters * 16 bits = ~1GB of memory
#       0.5B parameters * 4 bits  = ~0.25GB of memory
#
# The "nf4" (NormalFloat4) quantization type is specifically designed for
# neural network weights, which follow a bell curve (normal distribution).
# It distributes the 16 possible values (4 bits = 2^4 = 16) along that
# bell curve for minimum information loss.
#
# "double quantization" quantizes the quantization constants themselves,
# saving even more memory with almost no quality loss.
quantization_config = None
if USE_4BIT:  # XPU might not support 4-bit yet
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,              # Enable 4-bit quantization
        bnb_4bit_quant_type="nf4",      # Use NormalFloat4 (best for neural nets)
        bnb_4bit_compute_dtype=torch.bfloat16,  # Do math in bfloat16 for speed
        bnb_4bit_use_double_quant=True,  # Quantize the quantization constants too
    )

# --- Load the model ---
# AutoModelForCausalLM.from_pretrained() does several things:
# 1. Checks if the model is already cached locally
# 2. If not, downloads it from huggingface.co (~1GB for Qwen 0.5B)
# 3. Loads the weights into memory
# 4. Creates the model architecture and fills it with the weights
#
# "CausalLM" means "Causal Language Model" -- it predicts the NEXT token
# based only on PREVIOUS tokens (it can't look ahead). This is how all
# GPT-like models work: they generate text left-to-right, one token at a time.
#
# Real-world analogy: Loading a model is like loading a save file in a game.
# Someone else already spent weeks training this model (playing the game),
# and we're loading their progress to continue from where they left off.
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=quantization_config,
    # device_map="auto" automatically distributes model layers across available
    # GPUs and CPU. For XPU (Intel), we handle device placement manually.
    device_map="auto" if device != 'xpu' else None,
    # trust_remote_code=True allows the model to use custom code from the
    # model's repository. Qwen uses custom tokenization code.
    # WARNING: Only enable this for models you trust, as it runs arbitrary code.
    trust_remote_code=True,
    # bfloat16 (Brain Floating Point 16) uses 16 bits per number instead of 32.
    # It has the same range as float32 but less precision. This halves memory
    # usage with minimal quality loss. Intel and Google hardware love bfloat16.
    dtype=torch.bfloat16,
)

# If using XPU (Intel Arc), manually move the model to the GPU.
# With NVIDIA/CUDA, device_map="auto" handles this automatically.
# With XPU, we explicitly tell PyTorch "put this model on the Intel GPU."
# .to(device) copies all model parameters to the specified device's memory.
if device == 'xpu':
    model = model.to(device)

# If using 4-bit quantization, prepare the model for training.
# Quantized models need special handling because their weights are compressed.
# This function:
# 1. Freezes the quantized weights (they stay compressed during training)
# 2. Casts certain layers to full precision for numerical stability
# 3. Enables gradient computation for the layers we'll train
if USE_4BIT:
    model = prepare_model_for_kbit_training(model)

# --- Load the tokenizer ---
# The tokenizer converts text to/from token IDs (numbers).
# Qwen uses a byte-pair encoding (BPE) tokenizer:
# - Common words get a single token: "the" -> [279]
# - Rare words get split into subwords: "Ragavan" -> [23187, 5765]
# - This way the vocabulary stays manageable (~150k tokens for Qwen)
#
# Real-world analogy: A tokenizer is like a shorthand system. Common phrases
# get a single abbreviation ("btw" = "by the way"), while rare words are
# spelled out letter by letter. This keeps the "dictionary" a fixed size
# while being able to represent any text.
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_NAME,
    trust_remote_code=True,
)

# Set the padding token to be the same as the end-of-sequence token.
# Padding is needed when batching sequences of different lengths together.
# Imagine packing boxes of different sizes into a shipping container -- you
# need filler material (padding) to make them all the same size.
# The EOS (End Of Sequence) token signals "this is where the text ends."
tokenizer.pad_token = tokenizer.eos_token

# "right" padding means filler goes at the END of shorter sequences.
# This is important for causal (left-to-right) language models because
# the model needs real content on the LEFT side to generate properly.
# Padding on the left would confuse the model during generation.
tokenizer.padding_side = "right"

print(f"Model loaded on {device}")

# =============================================================================
# CONFIGURE LoRA
# =============================================================================
# Now we configure the LoRA adapters that will be attached to the model.
#
# HOW LoRA WORKS (the math, simplified):
# A transformer layer has weight matrices like W (e.g., 1024 x 1024).
# Normally, fine-tuning updates W directly: W_new = W + delta_W
# where delta_W is a full 1024x1024 matrix (1,048,576 parameters to learn).
#
# LoRA says: instead of learning delta_W directly, decompose it into two
# smaller matrices: delta_W = A * B, where:
#   A is 1024 x r (e.g., 1024 x 16 = 16,384 parameters)
#   B is r x 1024 (e.g., 16 x 1024 = 16,384 parameters)
# Total LoRA parameters: 32,768 instead of 1,048,576 -- that's 32x fewer!
#
# The "rank" r controls this tradeoff. Higher r = more parameters = more
# capacity but more memory. For most fine-tuning tasks, r=16 works well.
#
# Real-world analogy: Imagine you need to describe a 1000x1000 pixel image.
# Full fine-tuning: store every single pixel (1,000,000 values).
# LoRA: describe it as "16 horizontal patterns" + "16 vertical patterns" and
# combine them. You lose some detail but capture the important structure
# with far fewer numbers.

print("\nConfiguring LoRA...")

lora_config = LoraConfig(
    r=LORA_R,                    # Rank: dimensionality of the decomposition (see above)
    lora_alpha=LORA_ALPHA,       # Scaling factor: effective weight = alpha/r * LoRA output
    target_modules=TARGET_MODULES,  # Which model layers get LoRA adapters
    lora_dropout=LORA_DROPOUT,   # Random dropout for regularization (prevents overfitting)
    bias="none",                 # Don't add trainable biases (keeps things simpler)
    task_type="CAUSAL_LM",       # We're doing causal language modeling (next-token prediction)
)

# get_peft_model() wraps the original model with LoRA adapters.
# The original weights are FROZEN (locked, not updated during training).
# Only the small LoRA adapter weights are trainable.
#
# Real-world analogy: Like putting a clear overlay on a painting. The
# original painting (frozen weights) stays untouched. You only draw on
# the overlay (LoRA weights). When you look at the result, you see the
# original painting + your additions combined.
model = get_peft_model(model, lora_config)

# Print how many parameters are trainable vs total.
# This shows the efficiency of LoRA: you'll typically see something like
# "Trainable: 1,048,576 (0.21%)" -- only 0.21% of the model is being updated!
trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
total_params = sum(p.numel() for p in model.parameters())
print(f"Trainable parameters: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)")
print(f"Total parameters: {total_params:,}")

# =============================================================================
# PREPARE DATASET
# =============================================================================
# Load the training data using whichever source the user specified.

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

# =============================================================================
# CONFIGURE TRAINING
# =============================================================================
# SFTConfig (Supervised Fine-Tuning Config) bundles all training settings
# into one object. This is the "control panel" for the training loop.

print("\nConfiguring training...")

training_args = SFTConfig(
    # Where to save checkpoints and the final model
    output_dir=OUTPUT_DIR,

    # --- Core training settings ---
    num_train_epochs=NUM_EPOCHS,               # How many times to go through all data
    per_device_train_batch_size=BATCH_SIZE,     # Examples per step (per GPU)
    per_device_eval_batch_size=BATCH_SIZE,      # Examples per eval step
    gradient_accumulation_steps=GRADIENT_ACCUMULATION,  # Accumulate before updating
    learning_rate=LEARNING_RATE,               # Step size for weight updates
    max_length=MAX_SEQ_LENGTH,                 # Max tokens per example (truncates longer ones)

    # --- Optimizer settings ---
    # AdamW is the standard optimizer for transformers. "W" means it includes
    # weight decay, which penalizes large weights to prevent overfitting.
    #
    # Real-world analogy: The optimizer is like the navigation system telling
    # you which direction to adjust. Adam is a smart navigator that:
    # - Remembers which direction worked well recently (momentum)
    # - Adjusts step size per-parameter (some weights need big steps, some small)
    # - Weight decay adds "friction" that gently pulls weights toward zero,
    #   preventing any single weight from dominating.
    optim="adamw_torch",

    # Weight decay coefficient. 0.01 means "add a tiny penalty proportional
    # to the size of each weight." This is a form of regularization.
    weight_decay=0.01,

    # Warmup: start with a very small learning rate and gradually increase
    # it during the first 3% of training. This prevents the model from making
    # wild updates early on when gradients are noisy.
    # Real-world analogy: Like warming up before exercise -- you don't sprint
    # at full speed immediately, you ease into it.
    warmup_ratio=0.03,

    # --- Evaluation and logging ---
    # These control how often we check progress and save snapshots.

    # eval_strategy="steps" means "evaluate every N training steps" (not epochs).
    eval_strategy="epoch", # (no, steps, epoch), when to evaulate the training
    #eval_steps=50,         # Run evaluation every 50 training steps
    logging_steps=10,      # Print training loss every 10 steps (so you can watch progress)
    save_strategy="epoch", # Save a checkpoint every N steps (steps,no,epoch)
    save_steps=200,        # Save every x steps
    save_total_limit=3,    # Only keep the 2 most recent checkpoints (saves disk space)

    # --- Performance flags ---
    # bf16=True tells PyTorch to use bfloat16 (16-bit) math on the GPU.
    # This is faster than float32 and uses half the memory, with minimal
    # accuracy loss. Intel Arc GPUs have excellent bfloat16 support.
    bf16=True if device in ['cuda', 'xpu'] else False,

    # Gradient checkpointing is a memory-saving technique. Normally, all
    # intermediate computations are kept in memory for the backward pass.
    # With checkpointing, some are discarded and recomputed when needed.
    # This trades compute time for memory savings (~30-50% less memory).
    #
    # Real-world analogy: Like a GPS that only remembers major intersections
    # instead of every meter of the route. If you need to backtrack, you
    # drive back to the last intersection and recalculate from there.
    gradient_checkpointing=True,

    # --- Other settings ---
    report_to="none",  # Don't send metrics to external services.
                       # Change to "wandb" to use Weights & Biases for
                       # beautiful training dashboards and experiment tracking.

    # Load the best model (lowest eval loss) at the end of training,
    # rather than the last checkpoint. This ensures we keep the version
    # that performed best on unseen data.
    load_best_model_at_end=True,

    # Packing: when True, multiple short examples are concatenated into a
    # single sequence to fill max_length efficiently. This speeds up training
    # but can sometimes confuse the model about conversation boundaries.
    # We keep it False for cleaner training on chat data.
    packing=False,
)

# =============================================================================
# CREATE TRAINER
# =============================================================================
# The SFTTrainer ties everything together: model, data, tokenizer, and config.
# It handles the entire training loop:
#   1. Tokenize each batch of examples using the chat template
#   2. Feed tokens through the model to get predictions
#   3. Calculate the loss (how wrong the predictions were)
#   4. Backpropagate to compute gradients (which direction to adjust weights)
#   5. Update the LoRA weights using the optimizer
#   6. Repeat for all batches across all epochs
#
# Real-world analogy: The trainer is like a personal coach. You give them
# the athlete (model), the training plan (config), and the exercises (data),
# and they handle running each drill, tracking progress, and adjusting
# intensity.

print("\nCreating trainer...")

trainer = SFTTrainer(
    model=model,                   # The model with LoRA adapters attached
    args=training_args,            # All the training configuration from above
    train_dataset=train_dataset,   # The 90% of data used for learning
    eval_dataset=eval_dataset,     # The 10% held out for testing
    processing_class=tokenizer     # The tokenizer that converts text <-> numbers
)

# =============================================================================
# TRAIN!
# =============================================================================
# This is where the actual learning happens. The trainer.train() call starts
# the training loop described above. Depending on your data size and hardware,
# this could take minutes to hours.
#
# What you'll see in the output:
#   - Loss: How wrong the model's predictions are (lower = better)
#     The loss should generally decrease over time.
#   - Eval loss: Same thing but on the held-out evaluation data.
#     If train loss goes down but eval loss goes UP, you're overfitting.
#   - Learning rate: Changes over time due to warmup and scheduling.
#
# Real-world analogy: Watching the loss decrease is like watching a student's
# test scores improve over the semester. You want both homework scores (train
# loss) and exam scores (eval loss) to improve together.

print("\n" + "="*70)
print("STARTING TRAINING")
if args.resume_from_checkpoint:
    print(f"  Resuming from checkpoint: {args.resume_from_checkpoint}")
print("="*70 + "\n")

# If --resume-from-checkpoint was provided, pass that path to trainer.train().
# The trainer will load the saved optimizer state, scheduler state, and model
# weights from the checkpoint directory and continue training from that point.
# If no checkpoint is specified, training starts fresh from the beginning.
trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

print("\n" + "="*70)
print("TRAINING COMPLETE!")
print("="*70 + "\n")

# =============================================================================
# SAVE MODEL
# =============================================================================
# Save the trained LoRA adapter weights and tokenizer.
#
# IMPORTANT: This only saves the LoRA adapter (~10-50MB), NOT the full base
# model (~1GB). To use the model later, you need:
#   1. Load the base model (Qwen 2.5 0.5B)
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

model.save_pretrained(OUTPUT_DIR)      # Save LoRA adapter weights
tokenizer.save_pretrained(OUTPUT_DIR)  # Save tokenizer (needed for inference)

print(f"Model saved to {OUTPUT_DIR}")

# =============================================================================
# TEST THE MODEL
# =============================================================================
# After training, generate some sample responses to see how the model behaves.
# This is a quick sanity check, not a rigorous evaluation.
#
# The generation process:
#   1. Format the prompt as a chat message (using the model's template)
#   2. Tokenize it (convert text to numbers)
#   3. Feed it into the model
#   4. The model predicts one token at a time, feeding each prediction back
#      in as input for the next (this is "autoregressive generation")
#   5. Decode the output tokens back to text
#
# Real-world analogy: Like asking a student to answer questions after they
# finish studying. You're not grading them -- just checking they can produce
# coherent answers about the material.

if not args.no_test:
    print("\n" + "="*70)
    print("TESTING FINE-TUNED MODEL")
    print("="*70 + "\n")

    # model.eval() switches the model from "training mode" to "evaluation mode."
    # In training mode, dropout is active (randomly disabling connections).
    # In eval mode, dropout is disabled so the model gives consistent outputs.
    # Real-world analogy: In practice (training), a team rotates players.
    # In the real game (evaluation), everyone plays their best lineup.
    model.eval()

    test_prompts = [
        "What is machine learning?",
        "Explain photosynthesis simply.",
        "Write a short poem about the ocean.",
    ]

    for prompt in test_prompts:
        # Format as a chat conversation with the model's expected template.
        # Qwen uses the ChatML format:
        #   <|im_start|>user
        #   What is machine learning?<|im_end|>
        #   <|im_start|>assistant
        messages = [{"role": "user", "content": prompt}]

        # apply_chat_template() wraps the message in the model's specific
        # format. tokenize=False means "give me the string, don't convert
        # to numbers yet." add_generation_prompt=True adds the
        # "<|im_start|>assistant\n" prefix so the model knows it should
        # start generating the assistant's response.
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        # Now tokenize (convert text to token IDs) and move to the GPU.
        # return_tensors="pt" means "return PyTorch tensors" (as opposed to
        # numpy arrays or TensorFlow tensors).
        # .to(device) moves the data to the same device as the model (GPU/CPU).
        inputs = tokenizer(text, return_tensors="pt").to(device)

        # Generate the response.
        # torch.no_grad() disables gradient tracking, which saves memory
        # and speeds up inference. We only need gradients during training.
        with torch.no_grad():
            outputs = model.generate(
                **inputs,               # Unpack the tokenized input
                max_new_tokens=128,     # Generate at most 128 new tokens
                temperature=0.7,        # Controls randomness:
                                        #   0.0 = always pick the most likely token (deterministic)
                                        #   1.0 = sample proportionally from probabilities
                                        #   0.7 = a good balance of creativity and coherence
                                        #   >1.0 = more random/creative
                do_sample=True,         # Enable sampling (vs greedy decoding)
                pad_token_id=tokenizer.eos_token_id  # Use EOS for padding
            )

        # Decode: convert token IDs back to human-readable text.
        # skip_special_tokens=True removes formatting tokens like <|im_start|>
        # that are meaningful to the model but ugly for humans to read.
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Extract just the assistant's response (everything after the last
        # "<|im_start|>assistant" marker). The full decoded output includes
        # the original prompt + the generated response, and we only want
        # the new part.
        if "<|im_start|>assistant" in response:
            response = response.split("<|im_start|>assistant")[-1].strip()

        print(f"User: {prompt}")
        print(f"Assistant: {response}\n")
        print("-" * 70 + "\n")
else:
    print("\nSkipping test generation (--no-test flag set)")

print("\nDone! Your fine-tuned model is ready to use.")
print(f"Load it with: model = AutoModelForCausalLM.from_pretrained('{OUTPUT_DIR}')")
