#!/usr/bin/env python3
"""
Analyze card frequency in MTG training data.

This script identifies low-exposure cards that might need more training examples
to achieve reliable memorization.

Usage:
    python analyze_card_frequency.py --data-file training_data.jsonl
    python analyze_card_frequency.py --data-file training_data.jsonl --min-freq 20
"""

import json
import re
import argparse
from collections import Counter
from typing import Dict, List, Tuple


def extract_card_names(text: str) -> List[str]:
    """
    Extract card names from MTG training data.
    
    Handles patterns in both user questions and assistant responses.
    """
    card_names = []
    
    # USER QUESTION PATTERNS
    
    # "What is the mana cost of X?"
    matches = re.findall(r"what is the mana cost of ([^?]+)\?", text, re.IGNORECASE)
    card_names.extend(matches)
    
    # "Tell me about X"
    matches = re.findall(r"tell me about ([^?]+?)(?:\?|$)", text, re.IGNORECASE)
    card_names.extend(matches)
    
    # "What does X do?"
    matches = re.findall(r"what does ([^?]+?) do\?", text, re.IGNORECASE)
    card_names.extend(matches)
    
    # "How does X combo with Y?" - extracts both X and Y
    matches = re.findall(r"how does (.+?) combo with (.+?)\?", text, re.IGNORECASE)
    for match in matches:
        card_names.extend(match)
    
    # "X combo with Y" (without "How does")
    matches = re.findall(r"^(.+?) combo with (.+?)\?", text, re.IGNORECASE)
    for match in matches:
        card_names.extend(match)
    
    # "What is X?"
    matches = re.findall(r"what is ([^?]+)\?", text, re.IGNORECASE)
    # Filter out generic questions
    for match in matches:
        if not any(word in match.lower() for word in ['the mana cost', 'the power', 'the toughness']):
            card_names.append(match)
    
    # ASSISTANT RESPONSE PATTERNS
    
    # "Card Name ({mana cost})" - most reliable pattern
    matches = re.findall(r"^([A-Z][^(]+?)\s+\(\{[^}]+\}\)", text, re.MULTILINE)
    card_names.extend(matches)
    
    # "The mana cost of X is {Y}"
    matches = re.findall(r"mana cost of ([^i]+?) is \{", text, re.IGNORECASE)
    card_names.extend(matches)
    
    # Clean up all extracted names
    cleaned = []
    stopwords = {
        "the", "a", "an", "this", "that", "these", "those",
        "it", "its", "i", "you", "we", "they", "is", "are",
    }
    
    for name in card_names:
        # Strip whitespace
        name = name.strip()
        
        # Remove common trailing/leading phrases
        name = re.sub(r'^\s*(?:the|a|an)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+(?:do|mean|combo|with|and|or)$', '', name, flags=re.IGNORECASE)
        
        # Skip if too short
        if len(name) <= 2:
            continue
            
        # Skip if it's just a stopword
        if name.lower() in stopwords:
            continue
        
        # Skip if it contains "the mana cost of" (leftover from bad extraction)
        if 'mana cost' in name.lower():
            continue
            
        # Capitalize first letter if needed (for consistency)
        if name and name[0].islower():
            name = name[0].upper() + name[1:]
        
        cleaned.append(name)
    
    return cleaned


def analyze_card_frequency(data_file: str) -> Counter:
    """
    Analyze frequency of card mentions in training data.
    
    Returns:
        Counter: Card name -> frequency mapping
    """
    card_counter = Counter()
    
    print(f"Analyzing {data_file}...")
    
    with open(data_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 10000 == 0:
                print(f"  Processed {line_num:,} examples...")
            
            try:
                data = json.loads(line)
                messages = data.get('messages', [])
                
                for message in messages:
                    content = message.get('content', '')
                    
                    # Extract card names from this message
                    cards = extract_card_names(content)
                    
                    # Count each unique card once per message
                    for card in set(cards):
                        card_counter[card] += 1
                        
            except json.JSONDecodeError:
                print(f"Warning: Skipped malformed JSON at line {line_num}")
                continue
    
    print(f"  Processed {line_num:,} examples total.")
    print(f"  Found {len(card_counter)} unique cards.\n")
    
    return card_counter


def print_frequency_report(
    card_counter: Counter,
    min_freq: int = 0,
    max_freq: int = float('inf'),
    top_n: int = None
):
    """Print a formatted frequency report."""
    
    # Filter by frequency range
    filtered = {
        card: count 
        for card, count in card_counter.items() 
        if min_freq <= count <= max_freq
    }
    
    if not filtered:
        print(f"No cards found with frequency between {min_freq} and {max_freq}")
        return
    
    # Sort by frequency
    sorted_cards = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    
    if top_n:
        sorted_cards = sorted_cards[:top_n]
    
    print(f"{'Card Name':<50} {'Frequency':>10} {'3 Epochs':>10} {'5 Epochs':>10}")
    print("=" * 80)
    
    for card, count in sorted_cards:
        exposures_3 = count * 3
        exposures_5 = count * 5
        print(f"{card:<50} {count:>10} {exposures_3:>10} {exposures_5:>10}")


def print_summary_stats(card_counter: Counter, epochs: int = 3):
    """Print summary statistics about the dataset."""
    
    total_cards = len(card_counter)
    total_mentions = sum(card_counter.values())
    avg_freq = total_mentions / total_cards if total_cards > 0 else 0
    
    # Categorize by frequency
    very_low = sum(1 for count in card_counter.values() if count < 10)
    low = sum(1 for count in card_counter.values() if 10 <= count < 20)
    medium_low = sum(1 for count in card_counter.values() if 20 <= count < 40)
    medium = sum(1 for count in card_counter.values() if 40 <= count < 100)
    high = sum(1 for count in card_counter.values() if count >= 100)
    
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"Total unique cards:        {total_cards:>10,}")
    print(f"Total card mentions:       {total_mentions:>10,}")
    print(f"Average frequency:         {avg_freq:>10.1f}")
    print(f"\nFrequency Distribution:")
    print(f"  Very Low (<10):          {very_low:>10,} ({100*very_low/total_cards:.1f}%)")
    print(f"  Low (10-19):             {low:>10,} ({100*low/total_cards:.1f}%)")
    print(f"  Medium-Low (20-39):      {medium_low:>10,} ({100*medium_low/total_cards:.1f}%)")
    print(f"  Medium (40-99):          {medium:>10,} ({100*medium/total_cards:.1f}%)")
    print(f"  High (100+):             {high:>10,} ({100*high/total_cards:.1f}%)")
    
    print(f"\nExposure Analysis ({epochs} epochs):")
    print(f"  <30 exposures:           {very_low + low:>10,} cards (likely to hallucinate)")
    print(f"  30-60 exposures:         {medium_low:>10,} cards (partially accurate)")
    print(f"  60-150 exposures:        {medium:>10,} cards (mostly accurate)")
    print(f"  150+ exposures:          {high:>10,} cards (highly accurate)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze card frequency in MTG training data"
    )
    parser.add_argument(
        '--data-file',
        type=str,
        required=True,
        help='Path to training data JSONL file'
    )
    parser.add_argument(
        '--min-freq',
        type=int,
        default=0,
        help='Minimum frequency to display (default: 0)'
    )
    parser.add_argument(
        '--max-freq',
        type=int,
        default=float('inf'),
        help='Maximum frequency to display (default: unlimited)'
    )
    parser.add_argument(
        '--top',
        type=int,
        default=None,
        help='Show only top N cards (default: show all)'
    )
    parser.add_argument(
        '--low-exposure',
        action='store_true',
        help='Show only low-exposure cards (<40 examples)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=3,
        help='Number of epochs for exposure calculation (default: 3)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Save results to file (optional)'
    )
    
    args = parser.parse_args()
    
    # Analyze the data
    card_counter = analyze_card_frequency(args.data_file)
    
    # Print summary stats
    print_summary_stats(card_counter, args.epochs)
    
    # Determine frequency range to display
    min_freq = args.min_freq
    max_freq = args.max_freq if args.max_freq != float('inf') else float('inf')
    
    if args.low_exposure:
        max_freq = min(max_freq, 39)  # <40 examples
    
    # Print frequency report
    print("\n" + "="*80)
    if args.low_exposure:
        print("LOW-EXPOSURE CARDS (High Risk of Hallucination)")
    else:
        print("CARD FREQUENCY REPORT")
    print("="*80 + "\n")
    
    print_frequency_report(
        card_counter,
        min_freq=min_freq,
        max_freq=max_freq,
        top_n=args.top
    )
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            f.write("Card Name,Frequency,3 Epochs,5 Epochs\n")
            for card, count in sorted(card_counter.items(), key=lambda x: x[1]):
                f.write(f'"{card}",{count},{count*3},{count*5}\n')
        print(f"\nResults saved to {args.output}")


if __name__ == '__main__':
    main()
