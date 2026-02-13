"""
Interactive testing script for your fine-tuned Qwen model
Usage: python test_model.py
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Configuration
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_PATH = "./output-3b-mtg-qlora"

print("Loading model...")
print(f"Base model: {BASE_MODEL}")
print(f"Adapter: {ADAPTER_PATH}")

# Detect device
if hasattr(torch, 'xpu') and torch.xpu.is_available():
    device = 'xpu'
    print(f'Using Intel GPU (XPU): {torch.xpu.get_device_name(0)}')
elif torch.cuda.is_available():
    device = 'cuda'
    print(f'Using NVIDIA GPU: {torch.cuda.get_device_name(0)}')
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

# Move to XPU if needed
if device == 'xpu':
    base_model = base_model.to('xpu')

# Load your trained adapter
model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
model.eval()

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)

print("\nModel loaded successfully!")
print("\n" + "="*70)
print("MTG Expert Model - Interactive Testing")
print("="*70)
print("Type your Magic: The Gathering questions below.")
print("Type 'quit' to exit.\n")

while True:
    # Get user input
    user_input = input("You: ").strip()
    
    if user_input.lower() in ['quit', 'exit', 'q']:
        print("\nGoodbye!")
        break
    
    if not user_input:
        continue
    
    # Format as chat
    messages = [{"role": "user", "content": user_input}]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    
    # Tokenize and move to device
    inputs = tokenizer(text, return_tensors="pt").to(device)
    
    # Generate response
    print("\nAssistant: ", end="", flush=True)
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
    print(response + "\n")
