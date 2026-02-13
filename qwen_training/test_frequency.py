import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_PATH = "./output-3b-mtg-qlora"

print("Loading model...")
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    dtype=torch.float32,
    trust_remote_code=True,
)

model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

# Test by frequency
questions = [
    #("HIGH (217x)", "Tell me about Sol Ring"),
    #("MEDIUM (46x)", "Tell me about Counterspell"),
    #("MEDIUM (41x)", "Tell me about Lightning Bolt"),
    #("LOW (18x)", "Tell me about Fynn, the Fangbearer"),
    ("LOW (3x)", "Tell me about Binding Mummy")
]

for freq, question in questions:
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")
    
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.1)
    
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    print(f"\n{'='*70}")
    print(f"FREQUENCY: {freq}")
    print(f"Q: {question}")
    print(f"A: {response}")
    print('='*70)