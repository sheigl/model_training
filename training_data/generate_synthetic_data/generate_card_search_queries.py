import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_card_search_prompt

def generate_card_search_queries(cards_collection: pymongo.collection.Collection, target_count=3000) -> list:
    """Generate card search queries - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} CARD SEARCH QUERIES ===")
    mongo_documents = []
    
    search_patterns = [
        {'name': 'Green ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
        {'name': 'Zombie tokens', 'query': {'text': {'$regex': 'zombie.*token', '$options': 'i'}}},
        {'name': 'Treasure tokens', 'query': {'text': {'$regex': 'treasure', '$options': 'i'}}},
        {'name': 'White removal', 'query': {'text': {'$regex': 'exile|destroy', '$options': 'i'}, 'colors': ['W']}},
        {'name': 'Blue card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'colors': ['U']}},
        {'name': 'ETB effects', 'query': {'text': {'$regex': 'enters the battlefield', '$options': 'i'}}},
        {'name': 'Black removal', 'query': {'text': {'$regex': 'destroy.*creature', '$options': 'i'}, 'colors': ['B']}},
        {'name': 'Red burn', 'query': {'text': {'$regex': 'deals.*damage', '$options': 'i'}, 'colors': ['R']}},
    ]
    
    for pattern in search_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['name']}")
        
        matching_cards = list(cards_collection.find(pattern['query'], {'name': 1, 'text': 1, 'manaCost': 1}).limit(15))
        
        if not matching_cards:
            continue
        
        card_info = "\n".join([f"  - {c.get('name', '')} ({c.get('manaCost', '')}): {c.get('text', '')[:100]}..." for c in matching_cards[:10]])
        card_names = [c.get('name', '') for c in matching_cards]
        
        prompt = build_card_search_prompt(pattern, card_info)

        try:
            response =  query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    mentioned = sum(1 for name in card_names if name in qa['answer'])

                    if mentioned >= 2:
                        is_valid, reason, score = query_ollama.validate_qa(
                            qa['question'], qa['answer'],
                            context=f"Search pattern: {pattern['name']}\nMatching cards: {card_info}",
                            category="card_search"
                        )
                        if is_valid:
                            mongo_documents.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "card_search",
                                "source_data": card_names[:5],
                                "search_pattern": pattern['name'],
                                "validated": True,
                                "validation_score": score,
                                "needs_review": False
                            })
                            print(f"    ✓ ACCEPTED (score: {score}/10, {mentioned} cards): {qa['question'][:80]}")
                            if len(mongo_documents) >= target_count:
                                break
                        else:
                            print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (only {mentioned}/2 cards mentioned): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating for {pattern['name']}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} card search queries")
    return mongo_documents