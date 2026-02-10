"""
Merge your existing card database with new strategic training data
This balances card facts with gameplay knowledge
"""

import json
import random

def load_jsonl(filename):
    """Load JSONL file"""
    data = []
    with open(filename, 'r') as f:
        for line in f:
            data.append(json.loads(line))
    return data

def save_jsonl(data, filename):
    """Save to JSONL file"""
    with open(filename, 'w') as f:
        for item in data:
            f.write(json.dumps(item) + '\n')

def balance_dataset(card_data_file, strategic_data_files, output_file):
    """
    Combine card database with strategic data in balanced proportions
    
    Target distribution:
    - 40% card facts (what you have)
    - 30% game mechanics 
    - 20% strategy concepts
    - 10% format/meta discussion
    """
    
    print("Loading existing card data...")
    card_data = load_jsonl(card_data_file)
    print(f"  Loaded {len(card_data)} card examples")
    
    # Load strategic data
    strategic_data = []
    for filename in strategic_data_files:
        try:
            data = load_jsonl(filename)
            strategic_data.extend(data)
            print(f"  Loaded {len(data)} strategic examples from {filename}")
        except FileNotFoundError:
            print(f"  Warning: {filename} not found, skipping")
    
    print(f"\nTotal strategic examples: {len(strategic_data)}")
    
    if not strategic_data:
        print("\nNo strategic data found!")
        print("Please generate some first using:")
        print("  - python generate_synthetic_data.py")
        print("  - python generate_with_api.py")
        print("  - python scrape_edhrec.py")
        return
    
    # Calculate balanced dataset size
    # We want strategic data to be 60% of total
    # If we have S strategic examples and C card examples:
    # S should be 60% of total, C should be 40% of total
    # So total = S / 0.6, and we sample C = total * 0.4
    
    strategic_count = len(strategic_data)
    target_total = int(strategic_count / 0.6)
    target_card_count = int(target_total * 0.4)
    
    print(f"\nTarget distribution:")
    print(f"  Card facts: {target_card_count} (40%)")
    print(f"  Strategic: {strategic_count} (60%)")
    print(f"  Total: {target_total}")
    
    # Sample card data if we have too much
    if len(card_data) > target_card_count:
        print(f"\nSampling {target_card_count} examples from {len(card_data)} card examples...")
        sampled_card_data = random.sample(card_data, target_card_count)
    else:
        print(f"\nUsing all {len(card_data)} card examples")
        sampled_card_data = card_data
    
    # Combine and shuffle
    combined_data = sampled_card_data + strategic_data
    random.shuffle(combined_data)
    
    # Save
    save_jsonl(combined_data, output_file)
    
    print(f"\n{'='*60}")
    print(f"Created balanced dataset with {len(combined_data)} examples")
    print(f"Saved to {output_file}")
    
    # Show distribution
    print(f"\nFinal distribution:")
    print(f"  Card facts: {len(sampled_card_data)} ({len(sampled_card_data)/len(combined_data)*100:.1f}%)")
    print(f"  Strategic: {len(strategic_data)} ({len(strategic_data)/len(combined_data)*100:.1f}%)")

def main():
    print("Dataset Balancer for MTG Training")
    print("=" * 60)
    
    # Configuration
    CARD_DATA = "complete_mtg.jsonl"
    STRATEGIC_DATA_FILES = [
        "synthetic_mtg_training_data.jsonl",
        "api_generated_mtg_data.jsonl",
        "edhrec_training_data.jsonl",
    ]
    OUTPUT = "balanced_mtg_training.jsonl"
    
    balance_dataset(CARD_DATA, STRATEGIC_DATA_FILES, OUTPUT)

if __name__ == "__main__":
    main()
