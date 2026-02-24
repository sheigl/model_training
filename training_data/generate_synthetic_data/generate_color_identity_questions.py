import random

import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_color_identity_prompt, validate_qa

def generate_color_identity_questions(cards_collection: pymongo.collection.Collection, commanders_collection: pymongo.collection.Collection, target_count=2000) -> list[dict]:
    """
    Generate color identity questions
    
    Examples:
    - "Can I play Sol Ring in my Atraxa deck?"
    - "What's the color identity of Boros Charm?"
    - "Colorless cards for mono-red?"
    """
    print(f"\n=== GENERATING {target_count:,} COLOR IDENTITY QUESTIONS ===")
    mongo_documents = []
    
    # Sample diverse cards
    cards_sample = list(map(lambda c: { 'name': c.get('name'), 'colors': json.loads(c.get('colors')), 'colorIdentity': json.loads(c.get('colorIdentity')), 'manaCost': c.get('manaCost') }, cards_collection.find(
        {'colors': {'$exists': True}},
        {'name': 1, 'colors': 1, 'colorIdentity': 1, 'manaCost': 1}
    ).limit(500)))
    
    print(f"  → Processing {len(cards_sample)} cards...")
    
    # Common commander color identities
    commanders: list[dict] = commanders_collection.find(
        {'color_identity': {'$exists': True}},
        {'name': 1, 'color_identity': 1}
    ).limit(100)
    
    commander_identities = [
        ('mono-red deck', ['R']),
    ]
    
    for card in commanders:
        commander_identities.append((card.get('name'), card.get('color_identity')))
    
    for card in random.sample(cards_sample, min(200, len(cards_sample))):
        if len(mongo_documents) >= target_count:
            break
        
        card_name = card.get('name', '')
        card_colors = card.get('colorIdentity', card.get('colors', []))
        
        if not card_name:
            continue
        
        # Pick a random commander
        commander_name, commander_colors = random.choice(commander_identities)
        
        # Determine if card is legal
        card_color_set = set(card_colors) if card_colors else set()
        commander_color_set = set(commander_colors)
        is_legal = card_color_set.issubset(commander_color_set)

        prompt = build_color_identity_prompt(card, commander_name, commander_colors, is_legal)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Card: {card_name}, colors: {card_colors}\nCommander: {commander_name}, identity: {commander_colors}\nLegal: {is_legal}",
                        category="color_identity"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "color_identity",
                            "source_data": [card_name, commander_name],
                            "card_colors": card_colors,
                            "commander_colors": commander_colors,
                            "is_legal": is_legal,
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
            print(f"  ✗ Error generating color identity for {card_name}/{commander_name}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} color identity questions")
    return mongo_documents
