import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_PATH = "./output-3b-mtg-expert"

# Load on CPU first
print("Loading on CPU...")
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float32,
    trust_remote_code=True,
)

model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)

# Check LoRA status
print(f"\nModel type: {type(model)}")
print(f"Active adapters: {model.active_adapters if hasattr(model, 'active_adapters') else 'N/A'}")

# Count LoRA parameters
lora_count = sum(1 for n, p in model.named_parameters() if 'lora' in n.lower())
print(f"LoRA parameters found: {lora_count}")

model.eval()

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

# Test
question = "Tell me about Fynn, the Fangbearer"
messages = [{"role": "user", "content": question}]
text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(text, return_tensors="pt")

with torch.no_grad():
    outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.1)

response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
print(f"\nQ: {question}")
print(f"A: {response}")