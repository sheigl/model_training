import random

import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_guide_qa_prompt, clean_html

def generate_guide_qa(guides_collection, target_count=2000) -> list[dict]:
    """
    Generate Q&A grounded in EDHREC guide content.
    Guides are more instructional than articles — focus on how-to and best practices.

    Examples:
    - "How do I build a consistent mana base?"
    - "What mistakes do beginners make with Commander deckbuilding?"
    """
    print(f"\n=== GENERATING {target_count:,} GUIDE Q&A ===")
    mongo_documents = []

    print("  → Fetching guides from MongoDB...")
    all_guides = list(guides_collection.find(
        {'title': {'$exists': True}, 'content': {'$exists': True, '$ne': ''}},
        {'title': 1, 'content': 1}
    ))

    good_guides = [g for g in all_guides if len(clean_html(g.get('content', ''))) > 300]
    random.shuffle(good_guides)
    print(f"  → Found {len(good_guides):,} guides with sufficient content")

    for guide in good_guides:
        if len(mongo_documents) >= target_count:
            break

        title = guide.get('title', '')
        content = clean_html(guide.get('content', ''))[:2000]

        if not title or not content:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_guide_qa_prompt(title, content)

        try:
            response = query_ollama(MODEL_NAME, prompt, max_tokens=8192)
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
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Guide: {title}\n{content[:500]}",
                        category="guide_qa"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "guide_qa",
                            "source_data": [title],
                            "guide_title": title,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        accepted += 1
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")

            print(f"    ✓ ACCEPTED {accepted}/4 from: {title[:60]}")
        except Exception as e:
            print(f"  ✗ Error for guide '{title[:50]}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} guide Q&A examples")
    return mongo_documents
