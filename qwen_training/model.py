"""
Model and tokenizer loading with LoRA configuration.

This module handles loading the pre-trained model and tokenizer, applying
quantization, and configuring LoRA adapters for parameter-efficient fine-tuning.

The model and tokenizer always come as a pair:
  - Tokenizer: converts text -> numbers (and back)
  - Model: takes numbers in, produces numbers out

Real-world analogy: The tokenizer is like a Morse code operator who translates
English into dots and dashes. The model is the telegraph machine that processes
those dots and dashes. You need both to communicate.
"""

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training


# =============================================================================
# GaLore IMPORTS AND SAFE GLOBALS REGISTRATION
# =============================================================================
# GaLore: Gradient Low-Rank Projection optimizer for memory-efficient training.
# This is OPTIONAL and only needed for larger models (7B+) on consumer GPUs.
# Install with: pip install galore-torch
#
# GaLoreAdamW: The GaLore version of the AdamW optimizer. It projects gradients
# to a low-rank subspace before accumulating optimizer states, drastically
# reducing memory usage (~60-70% reduction in optimizer memory).
#
# GaLoreAdamW8bit: Even more memory-efficient version using 8-bit optimizer states.
# This combines GaLore's gradient projection with 8-bit quantization of the
# optimizer states themselves.
#
# Real-world analogy: If regular Adam is like storing full-resolution photos of
# every frame in a video (expensive!), GaLore is like storing a compressed version
# that captures the essential motion vectors. When you need to update the video,
# you work with the compressed version and only expand it when necessary.
try:
    from galore_torch import GaLoreAdamW, GaLoreAdamW8bit
    from galore_torch.galore_projector import GaLoreProjector
    GALORE_AVAILABLE = True

    # Register GaLore classes as safe for torch.load (required for PyTorch 2.6+)
    # This allows checkpoint resumption when GaLore optimizer state is saved
    torch.serialization.add_safe_globals([GaLoreProjector])
except ImportError:
    GaLoreAdamW = None
    GaLoreAdamW8bit = None
    GALORE_AVAILABLE = False
    # GaLore is not installed. This is fine if you're training small models (0.5B-2B).
    # For larger models (7B+), you'll need to install it: pip install galore-torch


# =============================================================================
# DEVICE DETECTION
# =============================================================================

def detect_device():
    """
    Detect available hardware for training.

    GPUs (Graphics Processing Units) are MUCH faster than CPUs for training
    because they can do thousands of math operations in parallel.

    Real-world analogy: A CPU is like one very smart mathematician who solves
    problems one at a time. A GPU is like a stadium full of average calculators
    who each solve one tiny piece of the problem simultaneously. Deep learning
    is mostly "lots of simple math operations," so the GPU wins big.

    This function supports three backends:
      xpu  = Intel Arc GPUs (like B580) via Intel's oneAPI/IPEX
      cuda = NVIDIA GPUs (the most common for ML)
      cpu  = No GPU -- works but is extremely slow for training

    Returns:
        str: The device string ('xpu', 'cuda', or 'cpu').
    """
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        # torch.xpu is Intel's GPU backend, added via Intel Extension for PyTorch.
        # hasattr() checks if the 'xpu' attribute exists in torch (it won't if
        # you installed regular PyTorch without Intel's XPU support).
        device = 'xpu'
        print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
        # Note: 4-bit quantization support on XPU depends on driver version.
        # Newer drivers (2024+) have better support.
    elif torch.cuda.is_available():
        device = 'cuda'
        print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
    else:
        device = 'cpu'
        print('Using CPU (training will be VERY slow!)')
        print('Consider using a GPU for training large models.')

    return device


# =============================================================================
# MODEL LOADING
# =============================================================================

def load_model(model_name, use_4bit=False, device='cpu', hf_token=None):
    """
    Load a pre-trained causal language model with optional quantization.

    AutoModelForCausalLM.from_pretrained() does several things:
    1. Checks if the model is already cached locally
    2. If not, downloads it from huggingface.co
       (~1GB for Qwen 0.5B, ~16GB for Qwen3 8B)
    3. Loads the weights into memory
    4. Creates the model architecture and fills it with the weights

    "CausalLM" means "Causal Language Model" -- it predicts the NEXT token
    based only on PREVIOUS tokens (it can't look ahead). This is how all
    GPT-like models work: they generate text left-to-right, one token at a time.

    Real-world analogy: Loading a model is like loading a save file in a game.
    Someone else already spent weeks training this model (playing the game),
    and we're loading their progress to continue from where they left off.

    Args:
        model_name: Hugging Face model identifier (e.g., "Qwen/Qwen2.5-0.5B-Instruct").
        use_4bit: Whether to use 4-bit quantization for memory efficiency.
        device: Target device ('cuda', 'xpu', or 'cpu').
        hf_token: Optional Hugging Face token for gated models.

    Returns:
        The loaded model, optionally quantized and moved to the target device.
    """
    print(f"Loading {model_name}...")
    if "8B" in model_name or "7B" in model_name:
        print("  (This is a large model - download may take several minutes)")

    # --- Quantization configuration ---
    # Quantization reduces the precision of the model's numbers to save memory.
    # Normally, each model parameter is a 16-bit floating point number (bfloat16).
    # 4-bit quantization squeezes each number into just 4 bits.
    #
    # Math: 0.5B parameters * 16 bits = ~1GB of memory
    #       0.5B parameters * 4 bits  = ~0.25GB of memory
    #       8B parameters * 16 bits   = ~16GB of memory
    #       8B parameters * 4 bits    = ~4GB of memory
    #
    # The "nf4" (NormalFloat4) quantization type is specifically designed for
    # neural network weights, which follow a bell curve (normal distribution).
    # It distributes the 16 possible values (4 bits = 2^4 = 16) along that
    # bell curve for minimum information loss.
    #
    # "double quantization" quantizes the quantization constants themselves,
    # saving even more memory with almost no quality loss.
    #
    # Real-world analogy: Like using JPEG compression for photos. You can't see
    # the difference between a 95% quality JPEG and the original, but the file
    # is 10x smaller. 4-bit quantization is similar for neural network weights.
    quantization_config = None
    if use_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,              # Enable 4-bit quantization
            bnb_4bit_quant_type="nf4",      # Use NormalFloat4 (best for neural nets)
            bnb_4bit_compute_dtype=torch.bfloat16,  # Do math in bfloat16 for speed
            bnb_4bit_use_double_quant=True,  # Quantize the quantization constants too
        )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantization_config,
        # device_map="auto" automatically distributes model layers across available
        # GPUs and CPU. For XPU (Intel), we handle device placement manually.
        device_map="auto" if device != 'xpu' else None,
        # trust_remote_code=True allows the model to use custom code from the
        # model's repository. Qwen uses custom tokenization code.
        # WARNING: Only enable this for models you trust, as it runs arbitrary code.
        trust_remote_code=True,
        # dtype specifies what numerical precision to use for model weights.
        # bfloat16 (Brain Floating Point 16) uses 16 bits per number instead of 32.
        # It has the same range as float32 but less precision. This halves memory
        # usage with minimal quality loss. Intel and Google hardware love bfloat16.
        #
        # If using 4-bit quantization, this dtype is used for computation (the
        # weights themselves are stored in 4-bit but expanded to bfloat16 for math).
        torch_dtype=torch.bfloat16,
        # hf token for downloading base model
        token=hf_token,
    )

    # If using XPU (Intel Arc), manually move the model to the GPU.
    # With NVIDIA/CUDA, device_map="auto" handles this automatically.
    # With XPU, we explicitly tell PyTorch "put this model on the Intel GPU."
    # .to(device) copies all model parameters to the specified device's memory.
    if device == 'xpu':
        print("  Moving model to Intel XPU...")
        model = model.to(device)

    # If using 4-bit quantization, prepare the model for training.
    # Quantized models need special handling because their weights are compressed.
    # This function:
    # 1. Freezes the quantized weights (they stay compressed during training)
    # 2. Casts certain layers to full precision for numerical stability
    # 3. Enables gradient computation for the layers we'll train (LoRA adapters)
    #
    # Real-world analogy: Like preparing a frozen pizza for baking. You can't
    # modify the frozen pizza itself, but you can add toppings (LoRA adapters)
    # on top of it. This function makes sure everything is ready for the oven (GPU).
    if use_4bit:
        print("  Preparing model for k-bit training...")
        model = prepare_model_for_kbit_training(model)

    print(f"Model loaded successfully!")
    return model


# =============================================================================
# TOKENIZER LOADING
# =============================================================================

def load_tokenizer(model_name):
    """
    Load the tokenizer for the specified model.

    The tokenizer converts text to/from token IDs (numbers).
    Qwen uses a byte-pair encoding (BPE) tokenizer:
    - Common words get a single token: "the" -> [279]
    - Rare words get split into subwords: "Ragavan" -> [23187, 5765]
    - This way the vocabulary stays manageable (~150k tokens for Qwen)

    Real-world analogy: A tokenizer is like a shorthand system. Common phrases
    get a single abbreviation ("btw" = "by the way"), while rare words are
    spelled out letter by letter. This keeps the "dictionary" a fixed size
    while being able to represent any text.

    Args:
        model_name: Hugging Face model identifier.

    Returns:
        The loaded tokenizer configured for training.
    """
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
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
    #
    # Example with right padding:
    #   Sequence 1: [Hello, world, !]
    #   Sequence 2: [Hi, <PAD>, <PAD>]
    #   The model can process both together correctly.
    tokenizer.padding_side = "right"

    return tokenizer


# =============================================================================
# LoRA CONFIGURATION
# =============================================================================

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


def apply_lora(model, lora_r=16, lora_alpha=32, lora_dropout=0.05):
    """
    Apply LoRA (Low-Rank Adaptation) adapters to the model.

    HOW LoRA WORKS (the math, simplified):
    A transformer layer has weight matrices like W (e.g., 1024 x 1024).
    Normally, fine-tuning updates W directly: W_new = W + delta_W
    where delta_W is a full 1024x1024 matrix (1,048,576 parameters to learn).

    LoRA says: instead of learning delta_W directly, decompose it into two
    smaller matrices: delta_W = A * B, where:
      A is 1024 x r (e.g., 1024 x 16 = 16,384 parameters)
      B is r x 1024 (e.g., 16 x 1024 = 16,384 parameters)
    Total LoRA parameters: 32,768 instead of 1,048,576 -- that's 32x fewer!

    The "rank" r controls this tradeoff. Higher r = more parameters = more
    capacity but more memory. For most fine-tuning tasks, r=16-32 works well.

    Real-world analogy: Imagine you need to describe a 1000x1000 pixel image.
    Full fine-tuning: store every single pixel (1,000,000 values).
    LoRA: describe it as "16 horizontal patterns" + "16 vertical patterns" and
    combine them. You lose some detail but capture the important structure
    with far fewer numbers.

    Args:
        model: The base model to add LoRA adapters to.
        lora_r: LoRA rank (dimensionality of the decomposition).
        lora_alpha: LoRA scaling factor (effective weight = alpha/r * LoRA output).
        lora_dropout: Dropout rate for regularization.

    Returns:
        tuple: (model_with_lora, trainable_params, total_params)
    """
    print("\nConfiguring LoRA...")

    lora_config = LoraConfig(
        r=lora_r,                    # Rank: dimensionality of the decomposition
        lora_alpha=lora_alpha,       # Scaling factor: effective weight = alpha/r * LoRA output
        target_modules=TARGET_MODULES,  # Which model layers get LoRA adapters
        lora_dropout=lora_dropout,   # Random dropout for regularization (prevents overfitting)
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

    # Calculate how many parameters are trainable vs total.
    # This shows the efficiency of LoRA: you'll typically see something like
    # "Trainable: 1,048,576 (0.21%)" for 0.5B models or
    # "Trainable: 4,194,304 (0.05%)" for 8B models
    # -- only a tiny fraction of the model is being updated!
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)")
    print(f"Total parameters: {total_params:,}")

    return model, trainable_params, total_params
