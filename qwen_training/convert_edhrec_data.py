"""
Convert EDHREC commander data to training format

EDHREC provides JSON data about:
- Popular commanders
- Card synergies
- Deck archetypes
- Card recommendations by theme

Usage:
    python convert_edhrec_data.py --output edhrec_training.jsonl --num-examples 500
"""

import json
import requests
import random
import time
import argparse
from pathlib import Path

# EDHREC JSON endpoints (publicly available)
EDHREC_BASE = "https://json.edhrec.com"
EDHREC_COMMANDERS = f"{EDHREC_BASE}/pages/commanders"
EDHREC_THEMES = f"{EDHREC_BASE}/pages/themes"

def fetch_json(url, max_retries=3):
    """Fetch JSON data with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"Fetching: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            time.sleep(1)  # Be polite to the server
            return response.json()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print(f"Failed to fetch {url}")
                return None

def get_popular_commanders(limit=100):
    """Get list of popular commanders"""
    try:
        data = fetch_json(f"{EDHREC_COMMANDERS}.json")
        if data and 'container' in data and 'json_dict' in data['container']:
            commanders = data['container']['json_dict'].get('cardlists', [])
            # Get top commanders
            top_commanders = []
            for cardlist in commanders[:limit]:
                if 'cardviews' in cardlist:
                    for card in cardlist['cardviews'][:20]:  # Top 20 per category
                        if 'name' in card:
                            top_commanders.append({
                                'name': card['name'],
                                'url': card.get('url', '')
                            })
            return top_commanders[:limit]
    except Exception as e:
        print(f"Error getting commanders: {e}")
    return []

def get_commander_page(commander_name):
    """Get detailed data for a specific commander"""
    # Convert commander name to URL format
    url_name = commander_name.lower().replace(' ', '-').replace(',', '').replace("'", '')
    url = f"{EDHREC_BASE}/pages/commanders/{url_name}.json"
    
    return fetch_json(url)

def generate_commander_questions(commander_data):
    """Generate questions about a commander and their deck"""
    questions = []
    
    if not commander_data:
        return questions
    
    try:
        container = commander_data.get('container', {})
        json_dict = container.get('json_dict', {})
        
        # Get commander name
        commander_name = json_dict.get('name', 'this commander')
        
        # Card recommendations by category
        cardlists = json_dict.get('cardlists', [])
        
        for cardlist in cardlists:
            tag = cardlist.get('tag', '')
            cards = cardlist.get('cardviews', [])[:5]  # Top 5 cards
            
            if not cards:
                continue
            
            card_names = [c.get('name', '') for c in cards if 'name' in c]
            
            if not card_names:
                continue
            
            # Generate question about card recommendations
            if tag == 'creatures':
                questions.append({
                    "user": f"What are good creatures for a {commander_name} deck?",
                    "assistant": f"Popular creatures in {commander_name} decks include: {', '.join(card_names[:3])}. These cards synergize well with the commander's strategy."
                })
            elif tag == 'instants':
                questions.append({
                    "user": f"What instants should I include in {commander_name}?",
                    "assistant": f"Top instant choices for {commander_name} include: {', '.join(card_names[:3])}. These provide interaction while supporting your game plan."
                })
            elif tag == 'sorceries':
                questions.append({
                    "user": f"What sorceries work well in {commander_name}?",
                    "assistant": f"Strong sorceries for {commander_name} include: {', '.join(card_names[:3])}. These help advance your strategy effectively."
                })
            elif tag == 'artifacts':
                questions.append({
                    "user": f"What artifacts should I run in {commander_name}?",
                    "assistant": f"Key artifacts for {commander_name} include: {', '.join(card_names[:3])}. These provide ramp and utility."
                })
            elif tag == 'lands':
                questions.append({
                    "user": f"What lands are good in {commander_name}?",
                    "assistant": f"Important lands for {commander_name} include: {', '.join(card_names[:3])}. These help fix your mana and provide utility."
                })
        
        # Themes/synergies
        themes = json_dict.get('themes', [])
        if themes:
            theme_list = [t.get('name', '') for t in themes[:3] if 'name' in t]
            if theme_list:
                questions.append({
                    "user": f"What themes work well with {commander_name}?",
                    "assistant": f"{commander_name} synergizes with these themes: {', '.join(theme_list)}. Build around these strategies for best results."
                })
    
    except Exception as e:
        print(f"Error generating questions: {e}")
    
    return questions

def generate_general_commander_questions():
    """Generate general Commander format questions"""
    questions = [
        {
            "user": "How many lands should I run in a Commander deck?",
            "assistant": "Most Commander decks run 36-38 lands. Use 36 lands if you have 10+ ramp sources (mana rocks/dorks), 37-38 as a baseline, and 38-40 if your curve is high or you lack ramp. Adjust based on your deck's mana curve and strategy."
        },
        {
            "user": "What's the ideal mana curve for Commander?",
            "assistant": "Commander curves are typically higher than other formats. A good distribution: 1-2 CMC (8-10 cards for early plays/ramp), 3-4 CMC (12-15 cards for your engine), 5-6 CMC (8-10 cards for powerful effects), 7+ CMC (4-6 bombs/finishers). Adjust based on strategy - aggro curves lower, control curves higher."
        },
        {
            "user": "How much removal should I include in Commander?",
            "assistant": "Include 8-12 removal spells in Commander. This should be a mix of: single-target removal (4-6 cards like Path to Exile, Beast Within), board wipes (2-4 cards like Wrath of God), and flexible answers (2-3 cards like Generous Gift). More removal for competitive metas, less for casual."
        },
        {
            "user": "What's the rule of 8 in Commander deck building?",
            "assistant": "The Rule of 8: For each effect you want in your deck, include 8 cards that provide it. For example, 8 ramp sources, 8 card draw effects, 8 removal spells. This increases consistency while still allowing for 99 unique cards. It's a guideline, not a strict rule."
        },
        {
            "user": "How much card draw should a Commander deck have?",
            "assistant": "Include 8-12 sources of card advantage in Commander. This includes: card draw spells (Rhystic Study, Fact or Fiction), repeatable draw (Phyrexian Arena), and wheel effects (Wheel of Fortune). Blue decks want more (10-12), aggressive decks can run less (6-8) if they have other velocity."
        },
        {
            "user": "What's the best ramp package for Commander?",
            "assistant": "A good ramp package includes 10-12 sources: 2-mana rocks (Sol Ring, Arcane Signet, Signets), 3-mana rocks (Commander's Sphere, Coalition Relic), land ramp (Cultivate, Kodama's Reach, Rampant Growth), and mana dorks (Llanowar Elves, Birds of Paradise). Green gets land ramp, other colors focus on artifacts."
        },
        {
            "user": "Should I include tutors in my Commander deck?",
            "assistant": "Tutors are powerful but meta-dependent. Competitive decks run 4-8 tutors (Demonic Tutor, Vampiric Tutor, Worldly Tutor). Casual decks might run 0-3. Tutors increase consistency but slow down games and reduce variance. Discuss with your playgroup - some prefer lower-power without tutors."
        },
    ]
    return questions

def generate_strategy_questions():
    """Generate questions about MTG strategy"""
    questions = [
        {
            "user": "What's the best way to deal with a combo deck?",
            "assistant": "Combat combo decks with: 1) Interaction - hold up counterspells or removal for combo pieces, 2) Pressure - kill them before they combo, 3) Hate pieces - Rest in Peace vs graveyard combos, Rule of Law vs storm, 4) Disruption - thoughtseize their key pieces. Know the popular combos in your meta."
        },
        {
            "user": "How do I beat control decks?",
            "assistant": "Beat control with: 1) Threats that stick - uncounterable (Cavern of Souls, Carnage Tyrant), or recursive threats, 2) Card advantage - draw more cards than they can answer, 3) Protection - Veil of Summer, Boseiju, 4) Diverse threats - don't overextend into board wipes, 5) Efficient threats - make them have the answer immediately."
        },
        {
            "user": "What's the best removal spell in each color?",
            "assistant": "Best removal by color: White - Path to Exile (1 mana exile), Swords to Plowshares. Black - Fatal Push, Terminate. Blue - Counterspell, Pongify (creature only). Red - Lightning Bolt, Chaos Warp. Green - Beast Within, Force of Vigor. Colorless - Dismember, Oblivion Stone."
        },
        {
            "user": "How do I build a mana base for a 3-color deck?",
            "assistant": "For 3-color mana bases: 1) Fetchlands (9-10 if budget allows), 2) Shocklands/duals (6-9), 3) Basics (3-6 of each color), 4) Utility lands (2-4), 5) Color-fixing lands (Triomes, Command Tower). Total ~36 lands. Prioritize your primary colors, ensure you can cast turn 1-2 plays reliably."
        },
        {
            "user": "What's card advantage and why does it matter?",
            "assistant": "Card advantage is having more cards than your opponent. It matters because: more cards = more options = better chance to win. Generate card advantage through: 1) Draw spells (divination effects), 2) 2-for-1s (one card kills two), 3) Recursive threats, 4) Engines (Rhystic Study). The player with more cards usually wins long games."
        },
    ]
    return questions

def main():
    parser = argparse.ArgumentParser(
        description="Convert EDHREC data to training format"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="edhrec_training.jsonl",
        help="Output JSONL file"
    )
    parser.add_argument(
        "--num-commanders",
        type=int,
        default=50,
        help="Number of commanders to fetch data for"
    )
    parser.add_argument(
        "--include-general",
        action="store_true",
        default=True,
        help="Include general Commander strategy questions"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("GENERATING EDHREC TRAINING DATA")
    print("="*70)
    print(f"This will take a while (~{args.num_commanders} seconds with rate limiting)")
    print("="*70 + "\n")
    
    all_questions = []
    
    # Add general questions
    if args.include_general:
        print("Adding general Commander strategy questions...")
        all_questions.extend(generate_general_commander_questions())
        all_questions.extend(generate_strategy_questions())
        print(f"Added {len(all_questions)} general questions")
    
    # Get popular commanders
    print("\nFetching popular commanders...")
    commanders = get_popular_commanders(args.num_commanders)
    print(f"Found {len(commanders)} commanders")
    
    # Fetch data for each commander
    for i, commander in enumerate(commanders, 1):
        print(f"\n[{i}/{len(commanders)}] Processing {commander['name']}...")
        
        commander_data = get_commander_page(commander['name'])
        if commander_data:
            questions = generate_commander_questions(commander_data)
            all_questions.extend(questions)
            print(f"  Generated {len(questions)} questions")
        else:
            print(f"  Failed to get data")
    
    # Convert to training format
    training_data = []
    for q in all_questions:
        training_data.append({
            "messages": [
                {"role": "user", "content": q["user"]},
                {"role": "assistant", "content": q["assistant"]}
            ]
        })
    
    # Save
    print(f"\nSaving to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item) + '\n')
    
    print("\n" + "="*70)
    print("DONE!")
    print("="*70)
    print(f"Generated {len(training_data)} training examples")
    print(f"Saved to: {args.output}")
    print("\nYou can now train with:")
    print(f"python finetune_qwen.py --dataset file --data-file {args.output}")
    print("="*70)

if __name__ == "__main__":
    main()
