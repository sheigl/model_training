import random

import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_glossary_with_examples_prompt

def generate_glossary_with_examples(glossary_collection, target_count=1500) -> list[dict]:
    """
    Generate Q&A from glossary terms with concrete in-game examples.
    Grounded in the official glossary definition — not just "what does X mean".

    Examples:
    - "Give me an example of deathtouch in a game."
    - "How does lifelink work in practice?"
    - "What's the difference between exile and destroy?"
    """
    print(f"\n=== GENERATING {target_count:,} GLOSSARY WITH EXAMPLES QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching glossary terms from MongoDB...")
    all_terms = list(glossary_collection.find(
        {'word': {'$exists': True}, 'definition': {'$exists': True, '$ne': ''}},
        {'word': 1, 'definition': 1}
    ))

    # Filter to terms with meaningful definitions
    meaningful_terms = [t for t in all_terms if len(t.get('definition', '')) > 30]
    random.shuffle(meaningful_terms)
    print(f"  → Found {len(meaningful_terms):,} glossary terms")

    for term_doc in meaningful_terms:
        if len(mongo_documents) >= target_count:
            break

        term = term_doc.get('word', '')
        definition = term_doc.get('definition', '')

        if not term or not definition:
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_glossary_with_examples_prompt(term, definition)

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
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Term: {term}\nDefinition: {definition}",
                        category="glossary_with_examples"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "glossary_with_examples",
                            "source_data": [f"glossary_{term}"],
                            "term": term,
                            "definition": definition,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10, {term}): {qa['question'][:70]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for term '{term}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} glossary with examples questions")
    return mongo_documents

