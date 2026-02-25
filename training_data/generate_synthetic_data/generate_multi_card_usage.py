import pymongo
from query_ollama import *
import json
from common import MODEL_NAME, build_multi_card_usage_prompt

def generate_multi_card_usage(combos_collection: pymongo.collection.Collection, target_count=2000) -> list[dict]:
    """Generate multi-card usage - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} MULTI-CARD USAGE ===")
    mongo_documents = []
    
    combos = list(combos_collection.find({'status': 'OK'}).limit(target_count * 2))
    
    for combo in combos:
        if len(mongo_documents) >= target_count:
            break
        
        cards = combo.get('uses', [])
        card_names = [c.get('card', {}).get('name', '') for c in cards if c.get('card')]
        description = combo.get('description', '')
        
        if len(card_names) < 2 or not description:
            continue
        
        card1, card2 = card_names[0], card_names[1]
        
        prompt = build_multi_card_usage_prompt(card1, card2, description)

        try:
            response =  query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Cards: {', '.join(card_names)}\nCombo/interaction: {description}",
                        category="multi_card_usage"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "multi_card_usage",
                            "source_data": card_names,
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
            print(f"  ✗ Error generating for {card1} + {card2}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} multi-card usage")
    return mongo_documents