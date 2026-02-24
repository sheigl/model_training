import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_combo_prompt, validate_qa

def generate_combo_queries(combos_collection: pymongo.collection.Collection, cards: pymongo.collection.Collection, target_count=5000) -> list:
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
        combo_descriptions = []
        for combo in card_combos[:5]:
            combo_cards = [c.get('card', {}).get('name', '') for c in combo.get('uses', []) if c.get('card')]
            description = combo.get('description', '')
            if len(combo_cards) >= 2 and description:
                combo_descriptions.append({'cards': combo_cards, 'description': description})
        
        if not combo_descriptions:
            continue
        
        # Build prompt
        combo_list = "\n".join([f"  - {' + '.join(c['cards'])}: {c['description']}" for c in combo_descriptions])
        
        prompt = build_combo_prompt(card_name, combo_list)

        try:
            response =  query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    # Validate
                    valid = any(combo_card in qa['answer'] for combo in combo_descriptions for combo_card in combo['cards'] if combo_card != card_name)

                    if valid:
                        # Create MongoDB document
                        is_valid, reason, score = validate_qa(
                            qa['question'], qa['answer'],
                            context=f"Card: {card_name}\nCombos:\n{combo_list}",
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
                        print(f"    ✗ REJECTED (no combo cards in answer): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        
        except Exception as e:
            print(f"  ✗ Error generating for {card_name}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} combo queries")
    return mongo_documents