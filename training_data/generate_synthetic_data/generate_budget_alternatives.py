import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_budget_alternative_prompt, validate_qa

def generate_budget_alternatives(cards_collection: pymongo.collection.Collection, target_count=2000) -> list[dict]:
    """
    Generate budget alternative questions
    
    Examples:
    - "What's a budget alternative to Mana Crypt?"
    - "Cheap replacement for Cyclonic Rift?"
    - "Under $5 cards that ramp?"
    """
    print(f"\n=== GENERATING {target_count:,} BUDGET ALTERNATIVE QUESTIONS ===")
    mongo_documents = []
    
    # Use rarity as proxy for price (Mythic/Rare = expensive, Uncommon/Common = budget)
    # Get expensive cards (Mythic/Rare staples)
    expensive_patterns = [
        {'effect': 'ramp', 'query': {'text': {'$regex': 'search.*land|add.*mana', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        {'effect': 'removal', 'query': {'text': {'$regex': 'destroy|exile', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        {'effect': 'card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        {'effect': 'tutors', 'query': {'text': {'$regex': 'search.*library', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
    ]
    
    for pattern in expensive_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['effect']}")
        
        # Get expensive cards
        expensive_cards = list(cards_collection.find(
            pattern['query'],
            {'name': 1, 'text': 1, 'rarity': 1}
        ).limit(10))
        
        # Get budget alternatives (uncommon/common with similar effect)
        budget_query = pattern['query'].copy()
        budget_query['rarity'] = {'$in': ['uncommon', 'common']}
        
        budget_cards = list(cards_collection.find(
            budget_query,
            {'name': 1, 'text': 1, 'rarity': 1}
        ).limit(15))
        
        if not expensive_cards or not budget_cards:
            continue
        
        # Generate alternatives for each expensive card
        for exp_card in expensive_cards[:5]:
            if len(mongo_documents) >= target_count:
                break
            
            exp_name = exp_card.get('name', '')
            if not exp_name:
                continue
            
            budget_names = [c.get('name', '') for c in budget_cards[:5]]
            budget_details = "\n".join([f"  - {c.get('name', '')} ({c.get('rarity', '')})" for c in budget_cards[:5]])
            
            prompt = build_budget_alternative_prompt(exp_card, budget_details)

            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for qa in qa_pairs:
                    if 'question' in qa and 'answer' in qa:
                        # Validate budget cards mentioned
                        matched_budget = [name for name in budget_names if name in qa['answer']]
                        if matched_budget:
                            print(f"    ✓ ACCEPTED (budget cards: {', '.join(matched_budget[:3])}): {qa['question'][:80]}")
                            is_valid, reason, score = validate_qa(
                                qa['question'], qa['answer'],
                                context=f"Expensive card: {exp_name}\nBudget alternatives:\n{budget_details}",
                                category="budget_alternative"
                            )
                            if is_valid:
                                mongo_documents.append({
                                    "question": qa['question'],
                                    "answer": qa['answer'],
                                    "category": "budget_alternative",
                                    "source_data": [exp_name] + budget_names,
                                    "expensive_card": exp_name,
                                    "validated": True,
                                    "validation_score": score,
                                    "needs_review": False
                                })
                                print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                            else:
                                print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                        else:
                            print(f"    ✗ REJECTED (no budget cards in answer): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            except Exception as e:
                print(f"  ✗ Error generating budget alt for {exp_name}: {type(e).__name__}: {e}")
                continue
    
    print(f"  ✓ Generated {len(mongo_documents):,} budget alternative questions")
    return mongo_documents

