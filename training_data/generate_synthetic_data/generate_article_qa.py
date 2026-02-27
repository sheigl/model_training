import random

import pymongo
import json
from common import MODEL_NAME, build_article_qa_prompt, clean_html

def generate_article_qa(articles_collection, target_count=2000) -> list[dict]:
    """
    Generate Q&A grounded in EDHREC article content.
    Uses Qwen 14B to synthesize article advice into natural Q&A — not truncated raw text.

    Examples:
    - "What does this article recommend about building a sacrifice deck?"
    - "How should I approach land count in Commander?"
    """
    print(f"\n=== GENERATING {target_count:,} ARTICLE Q&A ===")
    mongo_documents = []

    print("  → Fetching articles from MongoDB...")
    all_articles = list(articles_collection.find(
        {'title': {'$exists': True}, 'content': {'$exists': True, '$ne': ''}},
        {'title': 1, 'content': 1}
    ))

    # Filter to articles with enough content to be useful
    good_articles = [a for a in all_articles if len(clean_html(a.get('content', ''))) > 300]
    random.shuffle(good_articles)
    print(f"  → Found {len(good_articles):,} articles with sufficient content")

    for article in good_articles:
        if len(mongo_documents) >= target_count:
            break

        title = article.get('title', '')
        # Clean HTML and take up to 2000 chars — enough context without overwhelming the prompt
        content = clean_html(article.get('content', ''))[:2000]

        if not title or not content:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_article_qa_prompt(title, content)

        try:
            response = query_model(MODEL_NAME, prompt, max_tokens=9999)
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
                    is_valid, reason, score = query_model.validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Article: {title}\n{content[:500]}",
                        category="article_qa"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "article_qa",
                            "source_data": [title],
                            "article_title": title,
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
            print(f"  ✗ Error for article '{title[:50]}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} article Q&A examples")
    return mongo_documents

