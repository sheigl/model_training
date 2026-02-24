import random
import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_rule_why_prompt, validate_qa

def generate_rule_why_questions(rules_collection, target_count=1000) -> list[dict]:
    """
    Generate backward-reasoning 'why does this work' questions grounded in rule text.
    Teaches the underlying principle, not just the surface ruling.

    Examples:
    - "Why can't I respond to a mana ability?"
    - "Why does damage use the stack but destroy doesn't?"
    - "Why does a copy of a spell not have the same targets as the original?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE WHY QUESTIONS ===")
    mongo_documents = []

    # Focus on rules that have interesting underlying principles
    principle_sections = ['116', '117', '118', '120', '601', '602', '603', '604',
                          '608', '700', '701', '702', '704', '706']

    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$not': {'$regex': r'^See rule \d'}}},
        {'rule_number': 1, 'text': 1}
    ))

    # Filter to principle sections with substantial text
    principle_rules = []
    for rule in all_rules:
        num = rule.get('rule_number', '')
        text = rule.get('text', '')
        if len(text) < 100:
            continue
        for prefix in principle_sections:
            if num.startswith(prefix):
                principle_rules.append(rule)
                break

    random.shuffle(principle_rules)
    print(f"  → Found {len(principle_rules):,} principle rules")

    for rule in principle_rules:
        if len(mongo_documents) >= target_count:
            break

        rule_num = rule.get('rule_number', '')
        rule_text = rule.get('text', '')

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_why_prompt(rule_num, rule_text)

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
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    if rule_num not in qa['answer']:
                        print(f"    ✗ REJECTED (rule not cited): {qa['question'][:60]}")
                        continue
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Rule {rule_num}: {rule_text}",
                        category="rule_why"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "rule_why",
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

    print(f"  ✓ Generated {len(mongo_documents):,} rule why questions")
    return mongo_documents

