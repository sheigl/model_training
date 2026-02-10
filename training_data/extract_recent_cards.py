"""
Enhanced card extraction with focus on recent and relevant cards
This replaces the extract_card_training_data function
"""

from datetime import datetime
from pymongo import MongoClient
import random

# MongoDB connection
client = MongoClient(
    'mongodb://localhost:27017/',
    username='root',
    password='whatever',
    authSource='admin'
)

mtg_json_db = client['mtg_json']
cards_collection = mtg_json_db['cards']

def analyze_card_distribution():
    """
    Analyze what cards we have by release date and format
    """
    print("="*70)
    print("ANALYZING CARD DATABASE")
    print("="*70)
    
    # Total cards
    total_cards = cards_collection.count_documents({})
    print(f"\nTotal cards: {total_cards:,}")
    
    # Cards by year (if releaseDate exists)
    pipeline = [
        {'$match': {'releaseDate': {'$exists': True}}},
        {'$group': {
            '_id': {'$substr': ['$releaseDate', 0, 4]},
            'count': {'$sum': 1}
        }},
        {'$sort': {'_id': -1}},
        {'$limit': 10}
    ]
    
    print("\nCards by Year (last 10 years):")
    for doc in cards_collection.aggregate(pipeline):
        year = doc['_id']
        count = doc['count']
        print(f"  {year}: {count:,} cards")
    
    # Cards by format legality
    print("\nCards by Format Legality:")
    for format_name in ['standard', 'pioneer', 'modern', 'commander']:
        query = {f'legalities.{format_name}': 'legal'}
        count = cards_collection.count_documents(query)
        print(f"  {format_name.capitalize()}: {count:,} cards")
    
    print("\n" + "="*70)


def extract_cards_tiered(target_total=50000):
    """
    Extract cards using a tiered approach:
    - Tier 1: Recent cards (2020-2026) - ALL with full examples
    - Tier 2: Commander staples - Comprehensive coverage  
    - Tier 3: Older cards - Sample coverage
    
    This ensures the model knows:
    1. All recent cards users will ask about
    2. Popular eternal format cards
    3. Broad coverage of Magic's history
    """
    print("\n" + "="*70)
    print("TIERED CARD EXTRACTION STRATEGY")
    print("="*70)
    
    training_data = []
    examples_per_card = 3  # Average examples per card
    
    # ============================================================
    # TIER 1: Recent Cards (2020-2026) - PRIORITY
    # ============================================================
    print("\n[TIER 1] Extracting Recent Cards (2020-2026)...")
    
    # Cards from last 6 years
    recent_cards = list(cards_collection.find({
        'releaseDate': {'$gte': '2020-01-01'}
    }).limit(15000))
    
    print(f"  Found {len(recent_cards)} recent cards")
    
    tier1_examples = 0
    for card in recent_cards:
        # Generate comprehensive examples for recent cards
        examples = generate_card_examples(card, detail_level='high')
        training_data.extend(examples)
        tier1_examples += len(examples)
    
    print(f"  Generated {tier1_examples:,} examples from recent cards")
    
    # ============================================================
    # TIER 2: Commander Staples - HIGH PRIORITY
    # ============================================================
    print("\n[TIER 2] Extracting Commander Staples...")
    
    # Get commander-legal cards not already covered
    commander_cards = list(cards_collection.find({
        'legalities.commander': 'legal',
        'releaseDate': {'$lt': '2020-01-01'}
    }).limit(10000))
    
    print(f"  Found {len(commander_cards)} older commander cards")
    
    tier2_examples = 0
    for card in random.sample(commander_cards, min(5000, len(commander_cards))):
        examples = generate_card_examples(card, detail_level='medium')
        training_data.extend(examples)
        tier2_examples += len(examples)
    
    print(f"  Generated {tier2_examples:,} examples from commander staples")
    
    # ============================================================
    # TIER 3: Historical Coverage - BROAD SAMPLE
    # ============================================================
    print("\n[TIER 3] Sampling Historical Cards...")
    
    # Random sample of older cards for broad coverage
    historical_cards = list(cards_collection.aggregate([
        {'$match': {
            'releaseDate': {'$lt': '2020-01-01'},
            'legalities.commander': {'$ne': 'legal'}  # Not already in Tier 2
        }},
        {'$sample': {'size': 5000}}
    ]))
    
    print(f"  Sampled {len(historical_cards)} historical cards")
    
    tier3_examples = 0
    for card in historical_cards:
        examples = generate_card_examples(card, detail_level='low')
        training_data.extend(examples)
        tier3_examples += len(examples)
    
    print(f"  Generated {tier3_examples:,} examples from historical cards")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "="*70)
    print("EXTRACTION SUMMARY")
    print("="*70)
    total_cards = len(recent_cards) + 5000 + len(historical_cards)
    print(f"Total cards covered: {total_cards:,}")
    print(f"  Tier 1 (Recent): {len(recent_cards):,} cards → {tier1_examples:,} examples")
    print(f"  Tier 2 (Commander): 5,000 cards → {tier2_examples:,} examples")
    print(f"  Tier 3 (Historical): {len(historical_cards):,} cards → {tier3_examples:,} examples")
    print(f"\nTotal card examples: {len(training_data):,}")
    print("="*70 + "\n")
    
    return training_data


def generate_card_examples(card, detail_level='high'):
    """
    Generate training examples for a card
    detail_level: 'high', 'medium', or 'low'
    """
    examples = []
    name = card.get('name', '')
    
    if not name:
        return examples
    
    # Basic card info (ALL detail levels)
    card_text = card.get('text', '')
    mana_cost = card.get('manaCost', '')
    card_type = card.get('type', '')
    
    # Q1: What does [card] do?
    if card_text:
        examples.append({
            "messages": [
                {"role": "user", "content": f"What does {name} do?"},
                {"role": "assistant", "content": f"{name}: {card_text}"}
            ]
        })
    
    # HIGH detail only - full card breakdown
    if detail_level == 'high':
        # Q2: Mana cost
        if mana_cost:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"What's the mana cost of {name}?"},
                    {"role": "assistant", "content": f"{name} costs {mana_cost}."}
                ]
            })
        
        # Q3: Card type
        examples.append({
            "messages": [
                {"role": "user", "content": f"What type of card is {name}?"},
                {"role": "assistant", "content": f"{name} is a {card_type}."}
            ]
        })
        
        # Q4: Power/Toughness for creatures
        if card.get('power') and card.get('toughness'):
            power = card['power']
            toughness = card['toughness']
            examples.append({
                "messages": [
                    {"role": "user", "content": f"What's the power and toughness of {name}?"},
                    {"role": "assistant", "content": f"{name} is a {power}/{toughness}."}
                ]
            })
    
    # MEDIUM detail - name and text only
    elif detail_level == 'medium':
        if mana_cost:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"Tell me about {name}"},
                    {"role": "assistant", "content": f"{name} ({mana_cost}): {card_text}"}
                ]
            })
    
    # LOW detail - just text
    # (already added Q1 above)
    
    return examples


def main():
    """
    Quick test of the tiered extraction
    """
    # Analyze what we have
    analyze_card_distribution()
    
    # Extract using tiered approach
    training_data = extract_cards_tiered()
    
    print(f"\n✓ Ready to integrate {len(training_data):,} card examples into training data")
    print("\nTo use this:")
    print("1. Copy extract_cards_tiered() and generate_card_examples() functions")
    print("2. Replace extract_card_training_data() in extract_training_data.py")
    print("3. Call it: all_training_data.extend(extract_cards_tiered())")


if __name__ == "__main__":
    main()
