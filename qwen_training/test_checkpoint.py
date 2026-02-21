from unsloth import FastLanguageModel
from unsloth.chat_templates import get_chat_template
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
# Use the latest checkpoint
CHECKPOINT = "./output/checkpoint-20800"  # Adjust to your latest

print("Loading model...")
base_model, tokenizer = FastLanguageModel.from_pretrained(BASE_MODEL, dtype=None)

model = PeftModel.from_pretrained(base_model, CHECKPOINT)
model.eval()

# Test questions
questions = [
    "Tell me about Fynn, the Fangbearer",
    "What does deathtouch do?",
    "Explain how menace works in Magic: The Gathering"
]

for question in questions:
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")
    
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.1)
    
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    print(f"\n{'='*70}")
    print(f"Q: {question}")
    print(f"A: {response}")
