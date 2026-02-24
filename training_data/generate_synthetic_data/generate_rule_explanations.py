import random

import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_rule_explanation_prompt, validate_qa

def generate_rule_explanations(rules_collection, target_count=2000) -> list[dict]:
    """
    Generate natural Q&A grounded in actual rule text.
    Each Q&A is traceable back to a specific rule number.

    Examples:
    - "What does rule 702.2 say about flying?"
    - "Can a creature with flying block a ground creature?"
    - "What happens when a creature with flying attacks?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE EXPLANATION QUESTIONS ===")
    mongo_documents = []

    # Fetch rules from relevant sections — skip overly short or administrative rules
    print("  → Fetching rules from MongoDB...")
    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$ne': '', '$not': {'$regex': r'^See rule \d'}}},
        {'rule_number': 1, 'text': 1}
    ))

    # Filter to rules with meaningful content (>50 chars) and shuffle for variety
    meaningful_rules = [r for r in all_rules if len(r.get('text', '')) > 50]
    random.shuffle(meaningful_rules)
    print(f"  → Found {len(meaningful_rules):,} meaningful rules")

    for rule in meaningful_rules:
        if len(mongo_documents) >= target_count:
            break

        rule_num = rule.get('rule_number', '')
        rule_text = rule.get('text', '')

        if not rule_num or not rule_text:
            continue

        if (len(mongo_documents) + 1) % 200 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_explanation_prompt(rule_num, rule_text)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            # Handle array wrapped in extra brackets
            if not response.startswith('['):
                start = response.find('[')
                end = response.rfind(']')
                if start != -1 and end != -1:
                    response = response[start:end+1]
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    # Validate: answer must reference the rule number
                    if rule_num not in qa['answer']:
                        print(f"    ✗ REJECTED (rule number not in answer): {qa['question'][:60]}")
                        continue
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Rule {rule_num}: {rule_text}",
                        category="rule_explanation"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "rule_explanation",
                            "source_data": [f"rule_{rule_num}"],
                            "rule_number": rule_num,
                            "rule_text": rule_text,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10, rule {rule_num}): {qa['question'][:70]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:70]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rule {rule_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule explanation questions")
    return mongo_documents
