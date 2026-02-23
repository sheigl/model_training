from unsloth import FastLanguageModel

# Load your trained model + adapter
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="./output-7b-mtg-unsloth",  # your output dir
    dtype=None,
    load_in_4bit=True,
)

# Merge and save as full 16-bit model
model.save_pretrained_merged(
    "./output-7b-mtg-unsloth-merged",
    tokenizer,
    save_method="merged_16bit",  # or "merged_4bit" to keep it smaller
)

model.save_pretrained_gguf(
    "./output-7b-mtg-unsloth-merged-gguf",
    tokenizer,
    quantization_method="q5_k_m"  # good balance of quality vs size
)