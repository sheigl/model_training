"""
Generate synthetic MTG training data using the base Qwen model
This creates strategic Q&A about game mechanics, strategy, etc.
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import json

# Topics to generate Q&A about
TOPICS = [
    # Game Mechanics
    "the stack in Magic: The Gathering",
    "priority in Magic: The Gathering", 
    "how combat works in Magic: The Gathering",
    "the different phases and steps in a Magic turn",
    "how triggered abilities work",
    "how activated abilities work",
    "the difference between instants and sorceries",
    
    # Keyword Mechanics
    "what lifelink means in Magic",
    "what trample means in Magic",
    "what flying means in Magic",
    "what haste means in Magic",
    "what vigilance means in Magic",
    "what first strike means in Magic",
    "what double strike means in Magic",
    "what deathtouch means in Magic",
    "what hexproof means in Magic",
    "what ward means in Magic",
    
    # Strategic Concepts
    "card advantage in Magic: The Gathering",
    "tempo in Magic: The Gathering",
    "mana curve in deck building",
    "graveyard hate in Magic",
    "what ramp means in Magic",
    "board wipes in Magic",
    "removal spells in Magic",
    "what aggro decks are",
    "what control decks are",
    "what midrange decks are",
    "what combo decks are",
    
    # Format Basics
    "the Modern format in Magic",
    "the Standard format in Magic",
    "the Pioneer format in Magic",
    "the Legacy format in Magic",
    "the Commander/EDH format",
    "the Pauper format in Magic",
]

def generate_qa_for_topic(model, tokenizer, topic, device):
    """Generate Q&A pair for a given topic"""
    
    # Create prompt asking for explanation
    prompt = f"Explain {topic} in detail, including how it works and why it matters in gameplay."
    
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    
    inputs = tokenizer(text, return_tensors="pt").to(device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id
        )
    
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    
    # Create multiple question variations
    questions = []
    if "the stack" in topic:
        questions = [
            "How does the stack work in Magic?",
            "Explain the stack in Magic: The Gathering",
            "What is the stack in MTG?",
        ]
    elif "priority" in topic:
        questions = [
            "How does priority work in Magic?",
            "Explain priority in Magic: The Gathering",
            "What is priority in MTG?",
        ]
    elif "combat" in topic:
        questions = [
            "How does combat work in Magic?",
            "Explain the combat phase",
            "What happens during combat in MTG?",
        ]
    elif "card advantage" in topic:
        questions = [
            "What is card advantage?",
            "Explain card advantage in Magic",
            "Why does card advantage matter?",
        ]
    elif "graveyard hate" in topic:
        questions = [
            "What is graveyard hate?",
            "What does graveyard hate mean in Magic?",
            "How do I fight graveyard strategies?",
        ]
    else:
        # Generic questions
        questions = [
            f"What is {topic}?",
            f"Explain {topic}",
        ]
    
    return [(q, response) for q in questions]

def main():
    print("Synthetic MTG Training Data Generator")
    print("=" * 60)
    print("Using base Qwen model to generate explanations...")
    
    # Detect device
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        device = 'xpu'
        print('Using Intel GPU (XPU)')
    elif torch.cuda.is_available():
        device = 'cuda'
        print('Using NVIDIA GPU')
    else:
        device = 'cpu'
        print('Using CPU')
    
    # Load base model (not your fine-tuned one)
    print("\nLoading base Qwen model...")
    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen2.5-3B-Instruct",
        device_map=device if device != 'xpu' else None,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    
    if device == 'xpu':
        model = model.to('xpu')
    
    tokenizer = AutoTokenizer.from_pretrained(
        "Qwen/Qwen2.5-3B-Instruct",
        trust_remote_code=True
    )
    
    model.eval()
    print("Model loaded!\n")
    
    # Generate Q&A for each topic
    all_training_data = []
    
    for i, topic in enumerate(TOPICS):
        print(f"Generating Q&A for topic {i+1}/{len(TOPICS)}: {topic}")
        
        try:
            qa_pairs = generate_qa_for_topic(model, tokenizer, topic, device)
            
            for question, answer in qa_pairs:
                all_training_data.append({
                    "messages": [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": answer}
                    ]
                })
            
            print(f"  Generated {len(qa_pairs)} Q&A pairs")
            
        except Exception as e:
            print(f"  Error: {e}")
            continue
    
    # Save to file
    output_file = 'synthetic_mtg_training_data.jsonl'
    with open(output_file, 'w') as f:
        for example in all_training_data:
            f.write(json.dumps(example) + '\n')
    
    print(f"\n{'='*60}")
    print(f"Generated {len(all_training_data)} training examples")
    print(f"Saved to {output_file}")
    print(f"\nPreview of first example:")
    print(json.dumps(all_training_data[0], indent=2))

if __name__ == "__main__":
    main()
