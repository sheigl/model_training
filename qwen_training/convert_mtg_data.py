"""
Convert MTGJSON data to instruction-following training format

This script downloads MTG card data and generates Q&A pairs for fine-tuning.
It creates diverse question types about cards, mechanics, and strategy.

Supports both AtomicCards.json (card-focused) and AllPrintings.json (set-focused)

Usage:
    # Use existing AllPrintings.json
    python convert_mtg_data.py --data-file AllPrintings.json --output mtg_training.jsonl --num-examples 1000
    
    # Download fresh AtomicCards.json
    python convert_mtg_data.py --download --file-type atomic --output mtg_training.jsonl
    
    # Download fresh AllPrintings.json  
    python convert_mtg_data.py --download --file-type allprintings --output mtg_training.jsonl
"""

import json
import random
import argparse
import urllib.request
from pathlib import Path

def download_mtg_data(file_type="atomic", output_file=None):
    """
    Download MTGJSON data file
    
    Args:
        file_type: 'atomic' for AtomicCards.json or 'allprintings' for AllPrintings.json
        output_file: Custom output filename (optional)
    
    Returns:
        Path to downloaded file
    """
    urls = {
        "atomic": "https://mtgjson.com/api/v5/AtomicCards.json",
        "allprintings": "https://mtgjson.com/api/v5/AllPrintings.json"
    }
    
    default_names = {
        "atomic": "AtomicCards.json",
        "allprintings": "AllPrintings.json"
    }
    
    if file_type not in urls:
        raise ValueError(f"Unknown file type: {file_type}. Use 'atomic' or 'allprintings'")
    
    url = urls[file_type]
    filename = output_file or default_names[file_type]
    
    print(f"Downloading {url}...")
    if file_type == "allprintings":
        print("This is a large file (~150MB), may take 5-10 minutes...")
    else:
        print("This may take a few minutes (~50MB)...")
    
    urllib.request.urlretrieve(url, filename)
    print(f"Downloaded to {filename}")
    return filename

def load_mtg_data(filepath):
    """
    Load MTGJSON data and extract unique cards
    
    Handles both AtomicCards.json and AllPrintings.json formats
    
    Returns:
        Dictionary of unique cards keyed by card name
    """
    print(f"Loading {filepath}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Detect file type by structure
    if "data" in data:
        raw_data = data["data"]
        
        # Check if it's AtomicCards (cards keyed by name) or AllPrintings (sets keyed by code)
        first_key = next(iter(raw_data.keys()))
        first_value = raw_data[first_key]
        
        if isinstance(first_value, list):
            # AtomicCards format: {"data": {"Card Name": [card_variants], ...}}
            print(f"Detected AtomicCards format")
            cards = raw_data
            print(f"Loaded {len(cards)} unique cards")
            return cards
        
        elif isinstance(first_value, dict) and "cards" in first_value:
            # AllPrintings format: {"data": {"SET_CODE": {"cards": [...], ...}, ...}}
            print(f"Detected AllPrintings format")
            cards_dict = {}
            total_printings = 0
            
            for set_code, set_data in raw_data.items():
                for card in set_data.get("cards", []):
                    card_name = card.get("name")
                    if card_name:
                        if card_name not in cards_dict:
                            cards_dict[card_name] = []
                        cards_dict[card_name].append(card)
                        total_printings += 1
            
            print(f"Loaded {len(cards_dict)} unique cards from {total_printings} printings")
            return cards_dict
        else:
            raise ValueError("Unknown MTGJSON format")
    else:
        raise ValueError("Not a valid MTGJSON file (missing 'data' key)")

def format_mana_cost(mana_cost):
    """Convert mana cost symbols to readable format"""
    if not mana_cost:
        return "no mana cost"
    
    # Replace common symbols
    readable = mana_cost.replace("{", "").replace("}", " ")
    readable = readable.replace("W", "White").replace("U", "Blue")
    readable = readable.replace("B", "Black").replace("R", "Red")
    readable = readable.replace("G", "Green").replace("C", "Colorless")
    readable = readable.replace("X", "X").strip()
    
    return readable

def get_card_colors(card):
    """Get color identity or colors"""
    colors = card.get('colorIdentity', card.get('colors', []))
    if not colors:
        return "colorless"
    
    color_names = {
        'W': 'White', 'U': 'Blue', 'B': 'Black',
        'R': 'Red', 'G': 'Green'
    }
    
    color_list = [color_names.get(c, c) for c in colors]
    
    if len(color_list) == 1:
        return color_list[0]
    elif len(color_list) == 2:
        return f"{color_list[0]} and {color_list[1]}"
    else:
        return ", ".join(color_list[:-1]) + f", and {color_list[-1]}"

def generate_basic_info_questions(card_name, card):
    """Generate basic card information questions"""
    questions = []
    
    # What is this card?
    card_type = card.get('type', 'Unknown')
    questions.append({
        "user": f"What type of card is {card_name}?",
        "assistant": f"{card_name} is a {card_type}."
    })
    
    # Mana cost
    if 'manaCost' in card:
        mana = format_mana_cost(card['manaCost'])
        questions.append({
            "user": f"What is the mana cost of {card_name}?",
            "assistant": f"The mana cost of {card_name} is {mana}."
        })
    
    # Colors
    colors = get_card_colors(card)
    questions.append({
        "user": f"What colors is {card_name}?",
        "assistant": f"{card_name} is {colors}."
    })
    
    # Text/abilities
    if 'text' in card and card['text']:
        questions.append({
            "user": f"What does {card_name} do?",
            "assistant": f"{card_name}: {card['text']}"
        })
    
    return questions

def generate_stats_questions(card_name, card):
    """Generate questions about creature/planeswalker stats"""
    questions = []
    
    # Creature power/toughness
    if 'power' in card and 'toughness' in card:
        questions.append({
            "user": f"What are the power and toughness of {card_name}?",
            "assistant": f"{card_name} is a {card['power']}/{card['toughness']}."
        })
    
    # Planeswalker loyalty
    if 'loyalty' in card:
        questions.append({
            "user": f"What is the starting loyalty of {card_name}?",
            "assistant": f"{card_name} starts with {card['loyalty']} loyalty counters."
        })
    
    # Converted mana cost
    if 'manaValue' in card:
        questions.append({
            "user": f"What is the mana value of {card_name}?",
            "assistant": f"{card_name} has a mana value of {card['manaValue']}."
        })
    
    return questions

def generate_subtypes_questions(card_name, card):
    """Generate questions about card subtypes"""
    questions = []
    
    if 'subtypes' in card and card['subtypes']:
        subtypes = ", ".join(card['subtypes'])
        
        # For creatures
        if 'Creature' in card.get('type', ''):
            questions.append({
                "user": f"What creature type is {card_name}?",
                "assistant": f"{card_name} is a {subtypes}."
            })
        
        # General subtype question
        questions.append({
            "user": f"What are the subtypes of {card_name}?",
            "assistant": f"The subtypes of {card_name} are: {subtypes}."
        })
    
    return questions

def generate_format_questions(card_name, card):
    """Generate questions about format legality"""
    questions = []
    
    if 'legalities' in card:
        legalities = card['legalities']
        
        # Check specific formats
        for format_name in ['standard', 'modern', 'commander', 'legacy', 'vintage']:
            if format_name in legalities:
                legality = legalities[format_name]
                if legality == 'Legal':
                    questions.append({
                        "user": f"Is {card_name} legal in {format_name.capitalize()}?",
                        "assistant": f"Yes, {card_name} is legal in {format_name.capitalize()}."
                    })
                elif legality == 'Banned':
                    questions.append({
                        "user": f"Is {card_name} legal in {format_name.capitalize()}?",
                        "assistant": f"No, {card_name} is banned in {format_name.capitalize()}."
                    })
    
    return questions

def generate_comparison_questions(cards_dict):
    """Generate questions comparing multiple cards"""
    questions = []
    
    # Get a random sample of cards for comparisons
    card_names = list(cards_dict.keys())
    
    # Only generate a few comparison questions
    for _ in range(min(50, len(card_names) // 100)):
        # Pick two random cards
        card1_name = random.choice(card_names)
        card2_name = random.choice(card_names)
        
        if card1_name == card2_name:
            continue
        
        card1 = cards_dict[card1_name][0]  # Get first variant
        card2 = cards_dict[card2_name][0]
        
        # Compare mana values
        if 'manaValue' in card1 and 'manaValue' in card2:
            mv1 = card1['manaValue']
            mv2 = card2['manaValue']
            
            if mv1 < mv2:
                questions.append({
                    "user": f"Which costs more mana, {card1_name} or {card2_name}?",
                    "assistant": f"{card2_name} costs more mana. {card1_name} has a mana value of {mv1}, while {card2_name} has a mana value of {mv2}."
                })
            elif mv1 > mv2:
                questions.append({
                    "user": f"Which costs less mana, {card1_name} or {card2_name}?",
                    "assistant": f"{card2_name} costs less mana. {card2_name} has a mana value of {mv2}, while {card1_name} has a mana value of {mv1}."
                })
    
    return questions

def generate_strategy_questions(card_name, card):
    """Generate strategic gameplay questions"""
    questions = []
    
    card_type = card.get('type', '')
    
    # Different strategy questions based on card type
    if 'Creature' in card_type:
        if 'power' in card and 'toughness' in card:
            power = card['power']
            toughness = card['toughness']
            
            questions.append({
                "user": f"How can I use {card_name} in combat?",
                "assistant": f"{card_name} is a {power}/{toughness} creature. {card.get('text', 'It can attack and block.')} Consider its power and toughness when deciding whether to attack or block."
            })
    
    elif 'Instant' in card_type or 'Sorcery' in card_type:
        questions.append({
            "user": f"When can I cast {card_name}?",
            "assistant": f"{card_name} is {'an instant' if 'Instant' in card_type else 'a sorcery'}. {'You can cast it at any time you have priority, including during combat or on your opponent\'s turn.' if 'Instant' in card_type else 'You can only cast it during your main phase when the stack is empty.'}"
        })
    
    return questions

def generate_training_data(cards_dict, num_examples=1000):
    """
    Generate training examples from MTG cards
    
    Args:
        cards_dict: Dictionary of card data from MTGJSON
        num_examples: Target number of examples to generate
    
    Returns:
        List of training examples in the correct format
    """
    all_questions = []
    
    card_names = list(cards_dict.keys())
    random.shuffle(card_names)
    
    print(f"Generating training examples from {len(card_names)} cards...")
    
    for card_name in card_names:
        # Get first variant of the card (they have the same rules)
        card = cards_dict[card_name][0]
        
        # Generate different types of questions
        questions = []
        questions.extend(generate_basic_info_questions(card_name, card))
        questions.extend(generate_stats_questions(card_name, card))
        questions.extend(generate_subtypes_questions(card_name, card))
        questions.extend(generate_format_questions(card_name, card))
        questions.extend(generate_strategy_questions(card_name, card))
        
        all_questions.extend(questions)
        
        # Stop if we have enough examples
        if len(all_questions) >= num_examples:
            break
    
    # Add some comparison questions
    all_questions.extend(generate_comparison_questions(cards_dict))
    
    # Shuffle and limit to requested number
    random.shuffle(all_questions)
    all_questions = all_questions[:num_examples]
    
    # Convert to the format expected by fine-tuning script
    training_data = []
    for q in all_questions:
        training_data.append({
            "messages": [
                {"role": "user", "content": q["user"]},
                {"role": "assistant", "content": q["assistant"]}
            ]
        })
    
    print(f"Generated {len(training_data)} training examples")
    return training_data

def save_training_data(training_data, output_file):
    """Save training data to JSONL format"""
    print(f"Saving to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item) + '\n')
    
    print(f"Saved {len(training_data)} examples to {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description="Convert MTGJSON data to instruction-following training format"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="mtg_training.jsonl",
        help="Output JSONL file for training data"
    )
    parser.add_argument(
        "--num-examples",
        type=int,
        default=1000,
        help="Number of training examples to generate"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download fresh data from MTGJSON"
    )
    parser.add_argument(
        "--file-type",
        type=str,
        choices=["atomic", "allprintings"],
        default="atomic",
        help="Which MTGJSON file to download: 'atomic' (AtomicCards.json, ~50MB) or 'allprintings' (AllPrintings.json, ~150MB)"
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help="Path to existing MTGJSON data file (AtomicCards.json or AllPrintings.json). If not specified, will look for standard filenames."
    )
    
    args = parser.parse_args()
    
    # Determine which data file to use
    data_file = None
    
    if args.download:
        # User wants to download fresh data
        print("\n" + "="*70)
        print("DOWNLOADING FRESH DATA")
        print("="*70)
        data_file = download_mtg_data(file_type=args.file_type)
    
    elif args.data_file:
        # User specified a file
        if not Path(args.data_file).exists():
            print(f"Error: File not found: {args.data_file}")
            print("\nOptions:")
            print("  1. Check the file path")
            print("  2. Use --download to download fresh data")
            return
        data_file = args.data_file
        print(f"\nUsing existing data file: {data_file}")
    
    else:
        # Check for existing files in order of preference
        possible_files = ["AllPrintings.json", "AtomicCards.json"]
        
        for filename in possible_files:
            if Path(filename).exists():
                data_file = filename
                print(f"\nFound existing data file: {data_file}")
                break
        
        if not data_file:
            print("\nNo data file found!")
            print("\nOptions:")
            print("  1. Download AtomicCards.json:")
            print("     python convert_mtg_data.py --download --file-type atomic")
            print("  2. Download AllPrintings.json:")
            print("     python convert_mtg_data.py --download --file-type allprintings")
            print("  3. Specify existing file:")
            print("     python convert_mtg_data.py --data-file path/to/your/file.json")
            return
    
    # Load card data
    cards_dict = load_mtg_data(data_file)
    
    # Generate training examples
    training_data = generate_training_data(cards_dict, args.num_examples)
    
    # Save to file
    save_training_data(training_data, args.output)
    
    print("\n" + "="*70)
    print("DONE!")
    print("="*70)
    print(f"Training data saved to: {args.output}")
    print(f"Total examples: {len(training_data)}")
    print(f"Source file: {data_file}")
    print("\nYou can now train with:")
    print(f"python finetune_qwen.py --dataset file --data-file {args.output}")
    print("="*70)

if __name__ == "__main__":
    main()