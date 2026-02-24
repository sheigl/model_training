import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_staple_analysis_prompt, validate_qa

def generate_staple_analysis(game_changers_collection, target_count=2000) -> list[dict]:
    """
    Generate Q&A analyzing why game-changer cards are Commander staples.
    Uses num_decks and salt scores to ground the analysis.

    Examples:
    - "Why is Rhystic Study in 939K Commander decks?"
    - "Why do people hate Sol Ring at the table?"
    - "What kind of decks want Smothering Tithe?"
    """
    print(f"\n=== GENERATING {target_count:,} STAPLE ANALYSIS QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching game-changer cards from MongoDB...")
    all_changers = list(game_changers_collection.find(
        {'game_changer': True, 'oracle_text': {'$exists': True, '$ne': ''}},
        {'name': 1, 'oracle_text': 1, 'type': 1, 'mana_cost': 1,
         'num_decks': 1, 'salt': 1, 'tags': 1, 'color_identity': 1}
    ).sort('num_decks', -1))  # Sort by popularity

    print(f"  → Found {len(all_changers):,} game-changer cards")

    for card in all_changers:
        if len(mongo_documents) >= target_count:
            break

        name = card.get('name', '')
        if not name:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_staple_analysis_prompt(card)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            accepted = 0
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    # Validate: card name must appear in answer
                    if name not in qa['answer']:
                        continue
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Card: {name}\nDecks played in: {card.get('num_decks', 0):,}\nSalt score: {card.get('salt', 0):.2f}",
                        category="staple_analysis"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "staple_analysis",
                            "source_data": [name],
                            "card_name": name,
                            "num_decks": card.get('num_decks', 0),
                            "salt": card.get('salt', 0),
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        accepted += 1
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")

            print(f"    ✓ ACCEPTED {accepted}/3 from: {name}")
        except Exception as e:
            print(f"  ✗ Error for card '{name}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} staple analysis questions")
    return mongo_documents

