import pymongo
from rich.console import Console
from rich.status import Status
from query_ollama import *
import json
from common import MODEL_NAME, MTG_NOTATION_LEGEND, build_card_detail
from scryfall_mongodb import ScryfallMongo
import random
from typing import Callable

console = Console()

def build_combo_prompt(cards: list[dict], combo: str, random_combo_feature: str) -> str:
    """Generate combo question prompt with MTG notation guide."""
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 3 natural Q&A pairs about combos with the cards below. Make sure at least one of the questions is from the perspective of a player that doesn't know the extact combo or the cards, but may have an idea of a combo or looking for a combo. For example: "What combo can I make with {", ".join(map(lambda card: card.get('name'), cards))}?" or "How can I make a {random_combo_feature} combo?".

Cards:
{NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards))}

Combo:
{combo}

Output JSON:
[
{{"question": "...", "answer": "..."}},
{{"question": "...", "answer": "..."}},
{{"question": "...", "answer": "..."}}
]

Make questions varied and natural. Base answers on combo data above.
Explain how the combos work and what they achieve.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
    return prompt

# TODO build combo text just like commander spellbook

# Initial Card State
#  Sol Ring in hand.
#  Teferi and Displacer Kitten on the battlefield.
# Mana Needed
# ({1} magic symbol)  Magic Symbol (1) available.
# Steps
# Cast Sol Ring by paying ({1} magic symbol)  Magic Symbol (1).
# Displacer Kitten triggers, blinking Teferi.
# Activate Sol Ring by tapping it, adding ({C} magic symbol)  Magic Symbol (C)({C} magic symbol)  Magic Symbol (C).
# Activate Teferi's second loyalty ability by removing three loyalty counters from it, returning Sol Ring from the battlefield to your hand and drawing a card.
# Repeat.
# Results
# Infinite card draw.
# Infinite draw triggers.
# Near-infinite colorless mana.
# Near-infinite storm count.

def extract_combo_data(
    combos_collection: pymongo.collection.Collection, 
    card_collection: pymongo.collection.Collection, 
    scryfall_client: ScryfallMongo,
    target_count: int,
    rich_status: Status) -> list[dict]:
    """Extract combo data from commander spellbook documents and prepare for prompt generation."""
    all_combos = list(combos_collection.find({'status': 'OK'}).limit(target_count + 100))
    combos: list[dict] = []
    
    for i, combo in enumerate(all_combos):
        rich_status.update(f"[bold green]Extracting combo data... {i+1}/{len(all_combos)}")
        cards: list[dict] = combo.get('uses', [])
        combo_name = "|".join(map(lambda card: card.get('card', {}).get('name', 'Unknown'), cards))
        
        if len(list(filter(lambda combo: combo.get('name', None) == combo_name, combos))) > 0:
            continue
        
        projected_combo = {
            "name": combo_name,
            "description": combo.get('description', None),
            "cards_in_combo": list(map(lambda card: map_using_card(card, card_collection), cards)),
            "features": map_features(combo),
            "requirements": map_requirements(combo),
            "notes": combo.get('notes', None)
        }
        
        if len(projected_combo.get('requirements', [])) > 0:
            for req in projected_combo.get('requirements'):
                query = req.get('scryfallQuery')
                results = scryfall_client.search_scryfall(query=query)
                if hasattr(results, 'cards') and  len(results.cards) > 0:
                    random_card = random.choice(results.cards)
                    random_card_mapped = map_using_card({"card": {"name": random_card.get('name')}, "zoneLocations": []}, card_collection)
                    if random_card_mapped:
                        projected_combo.get('cards_in_combo').append(random_card_mapped)
                
        combos.append(projected_combo)
    
    random.shuffle(combos)
    return combos

def map_requirements(combo: dict) -> list[dict]:
    reqs = []
    
    if "requires" in combo:
        for req in combo.get('requires'):
            reqs.append({
                "zoneLocations": req.get('zoneLocations', []),
                "name": req.get('template', {}).get('name', None),
                "scryfallQuery": req.get('template', {}).get('scryfallQuery')
            })
    
    return reqs
        
def map_features(combo: dict) -> list[str]:
    features = []
    if "produces" in combo:
        for feature in combo.get('produces'):
            features.append(feature.get('feature', {}).get('name', None))
            
    return features
        
def map_using_card(card: dict, card_collection: pymongo.collection.Collection) -> dict:
    mtg_card: dict = card_collection.find_one({"name": card.get('card', {}).get('name')})
    
    if not mtg_card:
        return None
    
    projected_card = {
        "name": mtg_card.get('name', None),
        "type": mtg_card.get('type', None),
        "manaCost": mtg_card.get('manaCost', None),
        "text": mtg_card.get('text', None),
        "subtypes": json.loads(mtg_card.get('subtypes', '[]')),
        "supertypes": json.loads(mtg_card.get('supertypes', '[]')),
        "colorIdentity": json.loads(mtg_card.get('colorIdentity', '[]')),
        "zoneLocations": card.get('zoneLocations', [])
    }
    
    return projected_card

def generate_combo_queries(
    combos_collection: pymongo.collection.Collection, 
    card_collection: pymongo.collection.Collection, 
    scryfall_client: ScryfallMongo, 
    save_item: Callable[[dict], None], target_count=5000) -> None:
    """Generate combo queries - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} COMBO QUERIES ===")
    
    combos = []
    
    with console.status("[bold green]Extracting combo data...") as status:    
        combos = extract_combo_data(combos_collection, card_collection, scryfall_client, target_count, status)
    
    print(f"  → Processing {len(combos):,} cards...")
    
    i: int = 0
    for combo in combos:
        if i >= target_count:
            break
        
        if (i + 1) % 100 == 0:
            print(f"    Generated {i:,}/{target_count:,}...")
        
        combo_name = combo.get('name', '')
        
        # Build prompt
        prompts: list[tuple[str, list[dict], str]] = []
        
        description: str = combo.get('description')
        notes: str = combo.get('notes')
        
        numbered_descriptions = (f"Step {i + 1}. {desc}" for i, desc in enumerate(description.split('\n')))
        description = NEW_LINE.join(numbered_descriptions)
        
        if notes:
            description = description + NEW_LINE + NEW_LINE + f"*{notes}" 
            
        cards_in_combo: list[dict] = combo.get('cards_in_combo', [])
        
        prompts.append((build_combo_prompt(cards_in_combo, description, random.choice(combo.get('features', []))), cards_in_combo, description))
        
        for prompt, cards_in_combo, description in prompts:         
            try:
                response =  query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for qa in qa_pairs:
                    if 'question' in qa and 'answer' in qa:
                        # Validate
                        # Create MongoDB document
                        is_valid, reason, score = validate_qa(
                            qa['question'], qa['answer'],
                            context=f"\nCards:\n{NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards_in_combo))}\nCombo:\n{description}",
                            category="combo_query"
                        )
                        if is_valid:
                            doc = {
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "combo_query",
                                "source_data": [combo_name],
                                "validated": True,
                                "validation_score": score,
                                "needs_review": False
                            }
                            
                            save_item(doc)
                            
                            print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                            
                        else:
                            print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            
            except Exception as e:
                print(f"  ✗ Error generating for {combo_name}: {type(e).__name__}: {e}")
                continue
        
        i = i + 1
