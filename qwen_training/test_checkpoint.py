import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
# Use the latest checkpoint
CHECKPOINT = "./output-3b-mtg-qlora/checkpoint-10800"  # Adjust to your latest

print("Loading model...")
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float32,
    trust_remote_code=True,
)

model = PeftModel.from_pretrained(base_model, CHECKPOINT)
model.eval()

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

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
