import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_synergy_prompt

def generate_synergy_questions(cards_collection: pymongo.collection.Collection, combos_collection: pymongo.collection.Collection, target_count=3000):
    """
    Generate synergy discovery questions
    
    Examples:
    - "What cards synergize with Sol Ring?"
    - "What goes well with treasure tokens?"
    - "What commander works with artifacts?"
    """
    print(f"\n=== GENERATING {target_count:,} SYNERGY QUESTIONS ===")
    mongo_documents = []
    
    # Get popular cards from combos
    all_combos = list(combos_collection.find({'status': 'OK'}).limit(5000))
    
    # Count card appearances in combos
    card_combo_count = {}
    for combo in all_combos:
        cards = combo.get('uses', [])
        for card_info in cards:
            card_name = card_info.get('card', {}).get('name', '')
            if card_name:
                card_combo_count[card_name] = card_combo_count.get(card_name, 0) + 1
    
    # Get top cards by combo appearances
    popular_cards = sorted(card_combo_count.items(), key=lambda x: x[1], reverse=True)[:200]
    
    print(f"  → Processing {len(popular_cards)} popular combo cards...")
    
    for card_name, combo_count in popular_cards:
        if len(mongo_documents) >= target_count:
            break
        
        if (len(mongo_documents) + 1) % 200 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")
        
        # Get card details
        card = cards_collection.find_one({'name': card_name})
        if not card:
            continue
        
        # Find combos with this card
        card_combos = [c for c in all_combos if card_name in str(c.get('uses', []))][:3]
        
        # Get synergy cards (cards that appear with this card in combos)
        synergy_cards = set()
        for combo in card_combos:
            cards = combo.get('uses', [])
            for c in cards:
                other_name = c.get('card', {}).get('name', '')
                if other_name and other_name != card_name:
                    synergy_cards.add(other_name)
        
        if not synergy_cards:
            continue
        
        prompt = build_synergy_prompt(card, synergy_cards)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    # Validate at least one synergy card mentioned
                    matched_synergies = [syn for syn in synergy_cards if syn in qa['answer']]
                    if matched_synergies:
                        is_valid, reason, score = validate_qa(
                            qa['question'], qa['answer'],
                            context=f"Card: {card_name}\nSynergy cards: {', '.join(list(synergy_cards)[:10])}",
                            category="synergy"
                        )
                        if is_valid:
                            mongo_documents.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "synergy",
                                "source_data": [card_name] + list(synergy_cards)[:5],
                                "validated": True,
                                "validation_score": score,
                                "needs_review": False
                            })
                            print(f"    ✓ ACCEPTED (score: {score}/10, synergies: {', '.join(matched_synergies[:3])}): {qa['question'][:80]}")
                            if len(mongo_documents) >= target_count:
                                break
                        else:
                            print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (no synergy cards in answer): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating synergy for {card_name}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} synergy questions")
    return mongo_documents

