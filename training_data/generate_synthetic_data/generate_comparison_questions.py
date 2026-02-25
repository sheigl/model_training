import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_card_comparision_prompt

def generate_comparison_questions(cards_collection: pymongo.collection.Collection, target_count=2000) -> list[dict]:
    """
    Generate card comparison questions
    
    Examples:
    - "Which is better, Sol Ring or Mana Crypt?"
    - "Cultivate vs Kodama's Reach?"
    - "Should I run Lightning Bolt or Shock?"
    """
    print(f"\n=== GENERATING {target_count:,} COMPARISON QUESTIONS ===")
    mongo_documents = []
    
    # Define comparison patterns (cards with similar effects)
    comparison_patterns = [
        {'effect': 'fast mana', 'query': {'text': {'$regex': 'add.*mana|add {{C}}', '$options': 'i'}, 'type': {'$regex': 'Artifact'}}},
        {'effect': 'ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
        {'effect': 'removal', 'query': {'text': {'$regex': 'destroy|exile', '$options': 'i'}}},
        {'effect': 'card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}}},
        {'effect': 'counterspells', 'query': {'text': {'$regex': 'counter target', '$options': 'i'}, 'type': {'$regex': 'Instant'}}},
        {'effect': 'board wipes', 'query': {'text': {'$regex': 'destroy all|exile all', '$options': 'i'}}},
        {'effect': 'tutors', 'query': {'text': {'$regex': 'search.*library', '$options': 'i'}}},
        {'effect': 'reanimation', 'query': {'text': {'$regex': 'return.*creature.*graveyard', '$options': 'i'}}},
    ]
    
    for pattern in comparison_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['effect']}")
        
        # Get cards with similar effects
        similar_cards = list(cards_collection.find(
            pattern['query'],
            {'name': 1, 'text': 1, 'manaCost': 1, 'type': 1}
        ).limit(20))
        
        if len(similar_cards) < 2:
            continue
        
        # Generate comparisons between pairs
        for i in range(0, len(similar_cards) - 1, 2):
            if len(mongo_documents) >= target_count:
                break
            
            card1 = similar_cards[i]
            card2 = similar_cards[i + 1]
            
            card1_name = card1.get('name', '')
            card2_name = card2.get('name', '')
            
            if not card1_name or not card2_name:
                continue
            
            # Build prompt
            prompt = build_card_comparision_prompt(card1, card2)
            
            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for qa in qa_pairs:
                    # Basic structure check
                    if 'question' not in qa or 'answer' not in qa:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
                        continue
                    
                    # Quick check: at least one card mentioned (fast filter)
                    if card1_name not in qa['answer'] and card2_name not in qa['answer']:
                        print(f"    ✗ REJECTED (neither card in answer): {qa['question'][:80]}")
                        continue
                    
                    # Quick check: not too short
                    if len(qa['answer']) < 80:
                        print(f"    ✗ REJECTED (answer too short: {len(qa['answer'])} chars): {qa['question'][:80]}")
                        continue
                    
                    # Model-based validation (the smart filter!)
                    try:
                        is_valid, reason, score = query_ollama.validate_with_model(MODEL_NAME, card1, card2, qa)
                    except Exception as e:
                        print(f"    ⚠️  Validation failed ({e}), accepting by default")
                        is_valid = True
                        score = 5
                        reason = "validation_error"
                    
                    # Accept if score is 7 or higher
                    if is_valid and score >= 7:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "comparison",
                            "source_data": [card1_name, card2_name],
                            "effect_type": pattern['effect'],
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
            except Exception as e:
                print(f"  ✗ Error generating comparison for {card1_name} vs {card2_name}: {type(e).__name__}: {e}")
                continue

    print(f"  ✓ Generated {len(mongo_documents):,} comparison questions")
    return mongo_documents

