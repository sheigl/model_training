"""
Batch testing script - test multiple questions at once
Usage: python batch_test.py
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Configuration
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_PATH = "./output"  # Update this to your output directory

# Test questions
TEST_QUESTIONS = [
    "What does Lightning Bolt do?",
    "Explain how the stack works in Magic",
    "What is card advantage?",
    "What are the best cards in Modern?",
    "How does lifelink work?",
    "What is the difference between an instant and a sorcery?",
    "Explain what enters the battlefield triggers are",
    "What is graveyard hate?",
]

print("Loading model...")

# Detect device
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    device = 'xpu'
    print(f'Using Intel GPU (XPU)')
elif torch.cuda.is_available():
    device = 'cuda'
    print(f'Using NVIDIA GPU')
else:
    device = 'cpu'
    print('Using CPU')

# Load base model
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    device_map=device if device != 'xpu' else None,
    dtype=torch.bfloat16,
    trust_remote_code=True,
)

if device == 'xpu':
    base_model = base_model.to('xpu')

# Load your trained adapter
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

print("Model loaded successfully!\n")
print("="*70)
print("TESTING YOUR MTG EXPERT MODEL")
print("="*70 + "\n")

for i, question in enumerate(TEST_QUESTIONS, 1):
    print(f"\n{'='*70}")
    print(f"Question {i}/{len(TEST_QUESTIONS)}")
    print(f"{'='*70}")
    print(f"\nQ: {question}")
    
    # Format as chat
    messages = [{"role": "user", "content": question}]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    
    # Tokenize and move to device
    inputs = tokenizer(text, return_tensors="pt").to(device)
    
    # Generate response
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id
        )
    
    # Decode and print
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    print(f"\nA: {response}")

print("\n" + "="*70)
print("Testing complete!")
print("="*70)
