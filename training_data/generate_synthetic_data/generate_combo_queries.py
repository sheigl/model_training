import pymongo
from query_ollama import *
import json
from common import MODEL_NAME, MTG_NOTATION_LEGEND, build_card_detail
from scryfall_mongodb import ScryfallMongo
import random

def build_combo_prompt(card_name: str, cards: list[dict], combo: str) -> str:
    """Generate combo question prompt with MTG notation guide."""
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 3 natural Q&A pairs about combos with {card_name}.

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

def generate_combo_queries(combos_collection: pymongo.collection.Collection, card_collection: pymongo.collection.Collection, scryfall_client: ScryfallMongo, target_count=5000) -> list:
    """Generate combo queries - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} COMBO QUERIES ===")
    mongo_documents = []
    
    # Get combos grouped by card
    all_combos = list(combos_collection.find({'status': 'OK'}))
    
    combos_by_card = {}
    for combo in all_combos:
        cards = combo.get('uses', [])
        for card_info in cards:
            card_name = card_info.get('card', {}).get('name', '')
            if card_name:
                if card_name not in combos_by_card:
                    combos_by_card[card_name] = []
                combos_by_card[card_name].append(combo)
    
    cards_with_combos = [(card, combos) for card, combos in combos_by_card.items() if len(combos) >= 2]
    cards_with_combos.sort(key=lambda x: len(x[1]), reverse=True)
    
    print(f"  → Processing {len(cards_with_combos):,} cards...")
    
    for card_name, card_combos in cards_with_combos:
        if len(mongo_documents) >= target_count:
            break
        
        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")
        
        # Prepare combo data
        combo_descriptions: list[dict] = []
        for combo in card_combos[:5]:
            combo_cards = [c.get('card', {}).get('name', '') for c in combo.get('uses', []) if c.get('card')]
            description = combo.get('description', '')
            if len(combo_cards) >= 2 and description:
                combo_descriptions.append({'cards': combo_cards, 'description': description, 'combo': combo })
        
        if not combo_descriptions:
            continue
        
        # Build prompt
        prompts: list[tuple[str, list[dict], str]] = []
        
        for combo in combo_descriptions:
            cards_in_combo: list[dict] = []
            
            for combo_card_name in combo.get('cards'):
                cards_in_combo.append(card_collection.find_one({"name": combo_card_name}))
                
            if combo.get('combo').get('requires'):
                for requirement in combo.get('combo').get('requires'):
                    template: dict = requirement.get('template')
                    if "scryfallQuery" in template:
                        query = template.get('scryfallQuery')
                        results = scryfall_client.search_scryfall(query=query)
                        random_card = random.choice(results.cards)
                        cards_in_combo.append(card_collection.find_one({"name": random_card.get('name')}))

                
            
            description: str = combo.get('description')
            notes: str = combo.get('combo').get('notes')
            
            numbered_descriptions = (f"Step {i + 1}. {desc}" for i, desc in enumerate(description.split('\n')))
            description = NEW_LINE.join(numbered_descriptions)
            
            if notes:
                description = description + NEW_LINE + f"*{notes}" 
            
            prompts.append((build_combo_prompt(card_name, cards_in_combo, description), cards_in_combo, description))
        
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
                            mongo_documents.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "combo_query",
                                "source_data": [card_name],
                                "validated": True,
                                "validation_score": score,
                                "needs_review": False
                            })
                            print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                            if len(mongo_documents) >= target_count:
                                break
                        else:
                            print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            
            except Exception as e:
                print(f"  ✗ Error generating for {card_name}: {type(e).__name__}: {e}")
                continue

    print(f"  ✓ Generated {len(mongo_documents):,} combo queries")
    return mongo_documents