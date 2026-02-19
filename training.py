# Configuration - same for both experiments
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MAX_SEQ_LENGTH = 512
BATCH_SIZE = 2
GRAD_ACCUM = 4
NUM_EPOCHS = 1
LEARNING_RATE = 2e-4

# LoRA settings
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05

from unsloth import FastLanguageModel
from transformers import DataCollatorForSeq2Seq
import torch
import time
import gc
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
# Analyze dataset text lengths (no tokenizer needed)
import argparse
from datasets import load_dataset

def check_gpu():
    # Check GPU
    if torch.xpu.is_available():
        gpu_name = torch.xpu.get_device_name(0)
        total_mem = torch.xpu.get_device_properties(0).total_memory / 1e9
        print(f"✅ GPU: {gpu_name}")
        print(f"   Total Memory: {total_mem:.1f} GB")
    else:
        raise RuntimeError("No GPU available!")

def get_gpu_memory():
    """Get current GPU memory usage in GB."""
    return torch.xpu.memory_allocated() / 1e9

def get_peak_memory():
    """Get peak GPU memory usage in GB."""
    return torch.xpu.max_memory_allocated() / 1e9

def load_training_std_dataset():
    # Load dataset
    dataset = load_dataset("mlabonne/guanaco-llama2-1k", split="train")

    # Explore the dataset
    print("="*60)
    print("📊 DATASET EXPLORATION")
    print("="*60)

    # Basic info
    print(f"\n📋 Dataset size: {len(dataset)} examples")
    print(f"📋 Features: {list(dataset.features.keys())}")

    # Look at structure
    print(f"\n🔍 First example:")
    print("-"*60)
    print(dataset[0]["text"][:500] + "..." if len(dataset[0]["text"]) > 500 else dataset[0]["text"])

    # Text length statistics
    text_lengths = [len(item["text"]) for item in dataset]
    token_estimates = [len(item["text"].split()) for item in dataset]

    print(f"\n📈 Text Length Statistics:")
    print(f"   Min chars:     {min(text_lengths):,}")
    print(f"   Max chars:     {max(text_lengths):,}")
    print(f"   Avg chars:     {sum(text_lengths)//len(text_lengths):,}")
    print(f"   Avg words:     {sum(token_estimates)//len(token_estimates):,}")

    # Check format (Llama2 style)
    sample = dataset[0]["text"]
    has_inst = "[INST]" in sample
    has_human = "### Human:" in sample
    print(f"\n📝 Format detected:")
    print(f"   Llama2 style [INST]: {has_inst}")
    print(f"   Guanaco style ###:   {has_human}")

    # Show a few more examples
    print(f"\n🔍 Sample prompts (first 100 chars):")
    for i in range(min(3, len(dataset))):
        preview = dataset[i]["text"][:100].replace("\n", " ")
        print(f"   [{i}] {preview}...")

    # Approximate tokens by words (rough estimate: 1 word ≈ 1.3 tokens)
    word_lengths = [len(ex["text"].split()) for ex in dataset]
    approx_tokens = [int(w * 1.3) for w in word_lengths]

    print(f"📊 Approximate Token Length Statistics:")
    print(f"   Min: {min(approx_tokens)}")
    print(f"   Max: {max(approx_tokens)}")
    print(f"   Mean: {sum(approx_tokens)//len(approx_tokens)}")
    print(f"   Examples > 512 tokens: {sum(1 for l in approx_tokens if l > 512)} ({100*sum(1 for l in approx_tokens if l > 512)/len(approx_tokens):.1f}%)")
    print(f"   Examples > 1024 tokens: {sum(1 for l in approx_tokens if l > 1024)} ({100*sum(1 for l in approx_tokens if l > 1024)/len(approx_tokens):.1f}%)")

    # Show what percentage of data is kept/lost
    kept_512 = sum(1 for l in approx_tokens if l <= 512)
    kept_1024 = sum(1 for l in approx_tokens if l <= 1024)
    print(f"\n📈 Data Retention:")
    print(f"   With max_length=512:  {kept_512}/{len(dataset)} examples fully kept ({100*kept_512/len(dataset):.1f}%)")
    print(f"   With max_length=1024: {kept_1024}/{len(dataset)} examples fully kept ({100*kept_1024/len(dataset):.1f}%)")

    # Reset memory tracking
    torch.xpu.reset_peak_memory_stats()
    torch.xpu.empty_cache()
    gc.collect()
    
    return dataset

def load_std_model():
    # 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model
    print("\n📦 Loading model...")
    model_std = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
    )
    model_std = prepare_model_for_kbit_training(model_std)

    mem_after_load = get_gpu_memory()
    print(f"   Memory after load: {mem_after_load:.2f} GB")
    
    return model_std, tokenizer

def load_unsloth_dataset(dataset, tokenizer_unsloth):
    
    tok_fn = lambda examples: tokenizer_unsloth(
        examples["text"],
        truncation=True,   # ✅ Cut sequences > MAX_SEQ_LENGTH
        max_length=MAX_SEQ_LENGTH,
        padding=False,          # important: no padding in dataset
    )
    
    tokenized_dataset = dataset.map(tok_fn, batched=True, remove_columns=dataset.column_names)

    # Data collator with proper truncation
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer_unsloth,
        padding=True,
        pad_to_multiple_of=8,
    )
    
    return tokenized_dataset, data_collator

def load_unsloth_model():
    # Start timing
    start_time = time.time()

    # Load model with Unsloth
    print("\n📦 Loading model with Unsloth...")
    model_unsloth, tokenizer_unsloth = FastLanguageModel.from_pretrained(
        model_name=MODEL_ID,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )

    mem_after_load = get_gpu_memory()
    print(f"   Memory after load: {mem_after_load:.2f} GB")

    """
    Memory after load: 1.10 GB
    """


    # Apply LoRA with Unsloth (same settings)
    model_unsloth = FastLanguageModel.get_peft_model(
        model_unsloth,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        use_gradient_checkpointing="unsloth",  # Unsloth's optimized checkpointing
        random_state=42,
    )

    print("✅ LoRA applied with Unsloth optimizations")
    
    return model_unsloth, tokenizer_unsloth

def unsloth_training(model_unsloth, tokenizer_unsloth, tokenized_dataset, data_collator): 
    # Training arguments - quick training
    
    args = SFTConfig(
        output_dir="./output",
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LEARNING_RATE,
        fp16=False,
        bf16=True,
        logging_steps=50,
        save_strategy="no",
        optim="adamw_8bit",
        warmup_ratio=0.03,
        gradient_checkpointing=True,  # Unsloth's optimized checkpointing
        report_to="none",
        max_length=MAX_SEQ_LENGTH,  # Ensure trainer knows the max seq length for proper handling
        packing=False,  # Disable packing to match standard training setup
    )
    
    trainer_unsloth = SFTTrainer(
        model=model_unsloth,
        args=args,
        train_dataset=tokenized_dataset,
        processing_class=tokenizer_unsloth,
        data_collator=data_collator,
    )
    
    dl = trainer_unsloth.get_train_dataloader()
    batch = next(iter(dl))

    print("input_ids:", batch["input_ids"].shape)
    print("labels:", batch["labels"].shape)
    print("attention_mask:", batch["attention_mask"].shape)

    # Flatten sizes (what CE effectively sees)
    print("flat input tokens:", batch["input_ids"].numel())
    print("flat label tokens:", batch["labels"].numel())

    # Check exact mismatch positions
    print("same shape?", batch["input_ids"].shape == batch["labels"].shape)

    """
    input_ids: torch.Size([2, 512])
    labels: torch.Size([2, 512])
    attention_mask: torch.Size([2, 512])
    flat input tokens: 1024
    flat label tokens: 1024
    same shape? True
    """
    
    # Train with Unsloth!
    print("\n🚀 Starting Unsloth training...\n")
    train_start = time.time()

    result_unsloth = trainer_unsloth.train()

    train_time_unsloth = time.time() - train_start
    peak_memory_unsloth = get_peak_memory()
    final_loss_unsloth = result_unsloth.training_loss

    print(f"\n✅ Unsloth training complete!")
    print(f"   Training time: {train_time_unsloth:.1f} seconds")
    print(f"   Peak memory:   {peak_memory_unsloth:.2f} GB")
    print(f"   Final loss:    {final_loss_unsloth:.4f}")


    """
    ✅ Unsloth training complete!
    Training time: 173.9 seconds
    Peak memory:   2.48 GB
    Final loss:    1.7787
    """
    
    unsloth_results = {
        "training_time": train_time_unsloth,
        "peak_memory": peak_memory_unsloth,
        "final_loss": final_loss_unsloth,
    }
    
    return unsloth_results

def standard_training(model_std, tokenizer, dataset):
    # Apply LoRA
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )

    model_std = get_peft_model(model_std, lora_config)
    model_std.print_trainable_parameters()

    """
    trainable params: 2,162,688 || all params: 496,195,456 || trainable%: 0.4359
    """

    # Training arguments
    training_args_std = TrainingArguments(
        output_dir="./standard_output",
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=LEARNING_RATE,
        bf16=True,
        logging_steps=50,
        save_strategy="no",
        optim="adamw_torch",
        warmup_ratio=0.03,
        gradient_checkpointing=True,
        max_grad_norm=0.3,
        report_to="none",
    )

    # Create trainer
    trainer_std = SFTTrainer(
        model=model_std,
        args=training_args_std,
        train_dataset=dataset,
        processing_class=tokenizer,
        #max_seq_length=MAX_SEQ_LENGTH,
    )

    train_start = time.time()

    result_std = trainer_std.train()

    train_time_std = time.time() - train_start
    peak_memory_std = get_peak_memory()
    final_loss_std = result_std.training_loss

    print(f"\n✅ Standard training complete!")
    print(f"   Training time: {train_time_std:.1f} seconds")
    print(f"   Peak memory:   {peak_memory_std:.2f} GB")
    print(f"   Final loss:    {final_loss_std:.4f}")

    """
    Training time: 784.2 seconds
    Peak memory:   4.96 GB
    Final loss:    1.8213
    """

    standard_results = {
        "training_time": train_time_std,
        "peak_memory": peak_memory_std,
        "final_loss": final_loss_std,
    }
    
    # Cleanup
    del model_std
    del trainer_std
    gc.collect()
    torch.xpu.empty_cache()
    
    return standard_results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-type", type=str, choices=["standard", "unsloth"], default="standard", help="Type of training to perform")
    
    args = parser.parse_args()
    
    if args.training_type == "standard":
        print("🚀 Starting standard training...")
        check_gpu()
        dataset = load_training_std_dataset()
        model, tokenizer = load_std_model()
        standard_results = standard_training(model, tokenizer, dataset)
        
        print(f"✅ Standard training results:")
        print(f"   Training time: {standard_results['training_time']:.1f} seconds")
        print(f"   Peak memory:   {standard_results['peak_memory']:.2f} GB")
        print(f"   Final loss:    {standard_results['final_loss']:.4f}")
    else:
        print("🚀 Starting Unsloth training...")
        check_gpu()
        dataset = load_training_std_dataset()
        model_unsloth, tokenizer_unsloth = load_unsloth_model()
        tokenized_dataset, data_collator = load_unsloth_dataset(dataset, tokenizer_unsloth)
        unsloth_results = unsloth_training(model_unsloth, tokenizer_unsloth, tokenized_dataset, data_collator)
    
if __name__ == "__main__":
    main()