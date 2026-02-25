import pymongo
from query_ollama import *
import json
from common import MODEL_NAME, build_salt_prompt

def generate_salt_questions(game_changers_collection, target_count=1000) -> list[dict]:
    """
    Generate Q&A about controversial/salty cards — why they frustrate players,
    whether they're fair, and how to play around them.

    Examples:
    - "Why do people hate Cyclonic Rift?"
    - "Is Thassa's Oracle too powerful for casual Commander?"
    - "How do I play around Stax pieces?"
    """
    print(f"\n=== GENERATING {target_count:,} SALT QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching high-salt cards from MongoDB...")
    salty_cards = list(game_changers_collection.find(
        {'salt': {'$gte': 1.2}, 'oracle_text': {'$exists': True, '$ne': ''}},
        {'name': 1, 'oracle_text': 1, 'type': 1, 'mana_cost': 1,
         'num_decks': 1, 'salt': 1, 'tags': 1, 'color_identity': 1}
    ).sort('salt', -1))  # Saltiest first

    print(f"  → Found {len(salty_cards):,} high-salt cards (salt >= 1.2)")

    # Process in groups of 8 so each prompt covers multiple cards
    batch_size = 8
    batches = [salty_cards[i:i+batch_size] for i in range(0, len(salty_cards), batch_size)]

    for batch in batches:
        if len(mongo_documents) >= target_count:
            break

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_salt_prompt(batch)
        card_names = [c.get('name', '') for c in batch]

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    # Validate: at least one card name from batch in answer
                    mentioned = [n for n in card_names if n in qa['answer']]
                    if not mentioned:
                        print(f"    ✗ REJECTED (no card names in answer): {qa['question'][:60]}")
                        continue
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Salt cards in batch: {', '.join(card_names)}",
                        category="salt_analysis"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "salt_analysis",
                            "source_data": card_names,
                            "cards_mentioned": mentioned,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10, {', '.join(mentioned[:2])}): {qa['question'][:60]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")
        except Exception as e:
            print(f"  ✗ Error for salt batch: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} salt questions")
    return mongo_documents

