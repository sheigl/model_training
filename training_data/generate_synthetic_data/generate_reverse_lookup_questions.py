import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_reverse_lookup_prompt, validate_qa

def generate_reverse_lookup_questions(cards_collection: pymongo.collection.Collection, target_count=3000) -> list[dict]:
    """
    Generate reverse lookup questions (feature → card)
    
    Examples:
    - "What card lets me play lands from graveyard?"
    - "What creature tutors for artifacts?"
    - "What destroys all enchantments?"
    """
    print(f"\n=== GENERATING {target_count:,} REVERSE LOOKUP QUESTIONS ===")
    mongo_documents = []
    
    # Define searchable features
    feature_patterns = [
        {'feature': 'play lands from graveyard', 'regex': 'play.*land.*graveyard|land.*graveyard.*battlefield'},
        {'feature': 'tutor for artifacts', 'regex': 'search.*library.*artifact'},
        {'feature': 'tutor for creatures', 'regex': 'search.*library.*creature'},
        {'feature': 'destroy all creatures', 'regex': 'destroy all creature|destroy all nonland'},
        {'feature': 'destroy all artifacts', 'regex': 'destroy all artifact'},
        {'feature': 'destroy all enchantments', 'regex': 'destroy all enchantment|destroy target enchantment'},
        {'feature': 'exile from graveyard', 'regex': 'exile.*graveyard'},
        {'feature': 'return creatures from graveyard', 'regex': 'return.*creature.*graveyard'},
        {'feature': 'draw cards when creatures die', 'regex': 'draw.*card.*creature.*dies|creature dies.*draw'},
        {'feature': 'create treasure tokens', 'regex': 'create.*treasure|treasure token'},
        {'feature': 'create zombie tokens', 'regex': 'create.*zombie|zombie token'},
        {'feature': 'sacrifice creatures for value', 'regex': 'sacrifice.*creature.*draw|sacrifice.*creature.*mana'},
        {'feature': 'give creatures haste', 'regex': 'creatures.*have haste|creatures you control have haste'},
        {'feature': 'give creatures flying', 'regex': 'creatures.*have flying|creatures you control have flying'},
        {'feature': 'untap all creatures', 'regex': 'untap all creature|untap target creature'},
        {'feature': 'copy spells', 'regex': 'copy.*instant|copy.*sorcery|copy target spell'},
        {'feature': 'double mana', 'regex': 'double.*mana|add.*equal to'},
        {'feature': 'prevent combat damage', 'regex': 'prevent.*combat damage|creatures can.?t attack'},
    ]
    
    per_feature = target_count // len(feature_patterns)
    
    for pattern in feature_patterns:
        if len(mongo_documents) >= target_count:
            break
        
        print(f"  → {pattern['feature']}")
        
        # Find cards with this feature
        matching_cards = list(cards_collection.find(
            {'text': {'$regex': pattern['regex'], '$options': 'i'}},
            {'name': 1, 'text': 1, 'type': 1}
        ).limit(15))
        
        if not matching_cards:
            continue
        
        card_names = [c.get('name', '') for c in matching_cards]
        card_details = "\n".join([f"  - {c.get('name', '')}: {c.get('text', '')[:80]}..." for c in matching_cards[:5]])
        
        # Generate varied questions
        
        prompt = build_reverse_lookup_prompt(pattern, card_details)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    # Validate at least 2 cards mentioned
                    mentioned = sum(1 for name in card_names if name in qa['answer'])
                    if mentioned >= 2:
                        is_valid, reason, score = validate_qa(
                            qa['question'], qa['answer'],
                            context=f"Feature: {pattern['feature']}\nMatching cards: {card_details}",
                            category="reverse_lookup"
                        )
                        if is_valid:
                            mongo_documents.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "reverse_lookup",
                                "source_data": card_names[:5],
                                "feature": pattern['feature'],
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
            print(f"  ✗ Error generating reverse lookup for '{pattern['feature']}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} reverse lookup questions")
    return mongo_documents

