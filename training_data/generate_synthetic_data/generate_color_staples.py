import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_color_staples_prompt

def generate_color_staples(top_cards_dict, target_count=2000) -> list[dict]:
    """
    Generate Q&A about the top cards for each color in Commander.
    Uses EDHREC's top-color collections sorted by deck inclusion.

    Examples:
    - "What are the best Blue cards for Commander?"
    - "What Green ramp spells should I always include?"
    - "What colorless staples work in any Commander deck?"
    """
    print(f"\n=== GENERATING {target_count:,} COLOR STAPLE QUESTIONS ===")
    mongo_documents = []

    per_color = target_count // len(top_cards_dict)

    for color, collection in top_cards_dict.items():
        if len(mongo_documents) >= target_count:
            break

        print(f"  → Processing {color}...")

        # Get top cards for this color sorted by popularity
        top_cards = list(collection.find(
            {'oracle_text': {'$exists': True}},
            {'name': 1, 'oracle_text': 1, 'num_decks': 1, 'tags': 1,
             'type': 1, 'mana_cost': 1, 'color_identity': 1}
        ).sort('num_decks', -1).limit(30))

        if not top_cards:
            print(f"    ⚠️  No cards found for {color}")
            continue

        # Generate multiple batches using different subsets of top cards
        # so we get variety (top 10, next 10, etc.)
        subsets = [top_cards[:10], top_cards[10:20], top_cards[20:30]]

        color_docs = []
        for subset in subsets:
            if len(color_docs) >= per_color:
                break
            if not subset:
                continue

            prompt = build_color_staples_prompt(color, subset)

            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                if not response.startswith('['):
                    start = response.find('[')
                    end = response.rfind(']')
                    if start != -1 and end != -1:
                        response = response[start:end+1]
                qa_pairs = json.loads(response)

                card_names = [c.get('name', '') for c in subset]
                for qa in qa_pairs:
                    if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                        # Validate: at least 2 card names from the subset appear in the answer
                        mentioned = sum(1 for n in card_names if n in qa['answer'])
                        if mentioned < 2:
                            print(f"    ✗ REJECTED ({mentioned} cards mentioned): {qa['question'][:60]}")
                            continue
                        is_valid, reason, score = validate_qa(
                            qa['question'], qa['answer'],
                            context=f"Color: {color}\nTop staple cards: {', '.join(card_names[:10])}",
                            category="color_staples"
                        )
                        if is_valid:
                            color_docs.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "color_staples",
                                "source_data": card_names[:5],
                                "color": color,
                                "validated": True,
                                "validation_score": score,
                                "needs_review": False
                            })
                            print(f"    ✓ ACCEPTED (score: {score}/10, {color}, {mentioned} cards): {qa['question'][:60]}")
                            if len(color_docs) >= per_color:
                                break
                        else:
                            print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")
            except Exception as e:
                print(f"  ✗ Error for {color} subset: {type(e).__name__}: {e}")
                continue

        mongo_documents.extend(color_docs)
        print(f"  ✓ {color}: {len(color_docs):,} questions")

    print(f"  ✓ Generated {len(mongo_documents):,} color staple questions")
    return mongo_documents

