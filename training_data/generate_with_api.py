"""
Generate high-quality MTG training data using ChatGPT API
This produces the best quality strategic content

Usage:
1. Get API key from OpenAI
2. Set environment variable: export OPENAI_API_KEY="your-key"
3. Run: python generate_with_api.py
"""

import os
import json
import time

import openai
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# High-value topics to generate
GENERATION_PROMPTS = [
    # Mechanics explanations
    {
        "system": "You are an expert Magic: The Gathering rules judge.",
        "prompts": [
            "Explain how the stack works in Magic: The Gathering, including priority and how players can respond to spells and abilities.",
            "Explain how combat works in Magic, including all steps and priority passes.",
            "Explain what lifelink means and how it works in different situations.",
            "Explain what trample means and how damage is assigned.",
            "Explain the difference between instants and sorceries, including timing restrictions.",
            "Explain how triggered abilities work and when they go on the stack.",
            "Explain how enter-the-battlefield (ETB) triggers work.",
            "Explain what ward means and how it protects permanents.",
        ]
    },
    
    # Strategic concepts
    {
        "system": "You are an expert competitive Magic: The Gathering player and deck builder.",
        "prompts": [
            "Explain what card advantage means in Magic and why it's important.",
            "Explain what tempo means in Magic and how tempo decks win games.",
            "Explain what graveyard hate means and give examples of popular graveyard hate cards.",
            "Explain the difference between aggro, control, midrange, and combo deck archetypes.",
            "Explain what ramp means in Magic and why it's powerful.",
            "Explain what board wipes are and when to use them strategically.",
            "Explain what removal spells are and the difference between targeted and non-targeted removal.",
            "Explain what a mana curve is and why it matters in deck building.",
        ]
    },
    
    # Specific popular cards
    {
        "system": "You are an expert Magic: The Gathering player who explains why cards are powerful.",
        "prompts": [
            "Explain why Lightning Bolt is considered one of the best cards in Magic, including its efficiency and versatility.",
            "Explain why Counterspell is so powerful and how control decks use it.",
            "Explain why fetch lands like Polluted Delta are so valuable in competitive Magic.",
            "Explain why Sol Ring is banned in most formats but legal in Commander.",
            "Explain why Dark Ritual is powerful and what kinds of decks use it.",
            "Explain why Swords to Plowshares is considered premium removal.",
        ]
    },
    
    # Format explanations
    {
        "system": "You are an expert on Magic: The Gathering formats and tournament play.",
        "prompts": [
            "Explain the Modern format: what sets are legal, what the meta is like, and what kinds of decks are popular.",
            "Explain the Commander/EDH format: the rules, deck construction, and why it's so popular.",
            "Explain the Legacy format: what makes it unique, what kinds of cards are legal, and what the power level is like.",
            "Explain the Standard format: how rotation works and why it's good for new players.",
            "Explain the Pauper format: what makes it special and what kinds of decks are competitive.",
        ]
    },
]

def generate_with_openai(system_prompt, user_prompt):
    """Generate response using OpenAI API"""
    response = client.chat.completions.create(
        model="gpt-4o",  # or "gpt-4o-mini" for cheaper
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        max_tokens=1000
    )
    return response.choices[0].message.content

def create_question_variations(prompt):
    """Create multiple question phrasings for the same topic"""
    # Extract the key topic
    if "how the stack works" in prompt.lower():
        return [
            "How does the stack work in Magic?",
            "Explain the stack in Magic: The Gathering",
            "What is the stack in MTG?",
        ]
    elif "how combat works" in prompt.lower():
        return [
            "How does combat work in Magic?",
            "Explain combat in MTG",
            "What happens during the combat phase?",
        ]
    elif "card advantage" in prompt.lower():
        return [
            "What is card advantage?",
            "Explain card advantage in Magic",
            "Why is card advantage important?",
        ]
    elif "graveyard hate" in prompt.lower():
        return [
            "What is graveyard hate?",
            "What does graveyard hate mean in Magic?",
            "How do I fight graveyard strategies?",
        ]
    elif "lightning bolt" in prompt.lower():
        return [
            "Why is Lightning Bolt so good?",
            "What makes Lightning Bolt powerful?",
            "Why is Lightning Bolt a staple card?",
        ]
    else:
        # Default: extract topic and create generic questions
        return [prompt]

def main():
    print("High-Quality MTG Training Data Generator")
    print("=" * 60)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        return
    print("Using OpenAI GPT-4o")
    
    all_training_data = []
    total_prompts = sum(len(category["prompts"]) for category in GENERATION_PROMPTS)
    current = 0
    
    for category in GENERATION_PROMPTS:
        system_prompt = category["system"]
        
        for prompt in category["prompts"]:
            current += 1
            print(f"\n[{current}/{total_prompts}] Generating: {prompt[:60]}...")
            
            try:
                # Generate answer
                answer = generate_with_openai(system_prompt, prompt)
                
                # Create question variations
                questions = create_question_variations(prompt)
                
                # Add to training data
                for question in questions:
                    all_training_data.append({
                        "messages": [
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": answer}
                        ]
                    })
                
                print(f"  Generated {len(questions)} Q&A pairs")
                
                # Be polite to API
                time.sleep(1)
                
            except Exception as e:
                print(f"  Error: {e}")
                continue
    
    # Save to file
    output_file = 'api_generated_mtg_data.jsonl'
    with open(output_file, 'w') as f:
        for example in all_training_data:
            f.write(json.dumps(example) + '\n')
    
    print(f"\n{'='*60}")
    print(f"Generated {len(all_training_data)} training examples")
    print(f"Saved to {output_file}")
    print(f"\nEstimated cost: ~${len(all_training_data) * 0.01:.2f}")
    print(f"\nPreview of first example:")
    print(json.dumps(all_training_data[0], indent=2))

if __name__ == "__main__":
    main()
