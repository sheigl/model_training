import random

import pymongo
from query_model import QueryModel
import json
from common import COMPLEX_RULE_SECTIONS, MODEL_NAME, build_rule_edge_case_prompt

def generate_rule_edge_cases(rules_collection, target_count=1500) -> list[dict]:
    """
    Generate tricky edge case questions from complex rule sections.
    Designed to trip up experienced players, not beginners.

    Examples:
    - "Players often think X. What does rule 704.5g actually say?"
    - "If a creature has both deathtouch and indestructible assigned to it, what happens?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE EDGE CASE QUESTIONS ===")
    mongo_documents = []

    print("  → Fetching rules from complex sections...")
    # Only fetch from sections known to be tricky
    complex_section_prefixes = list(COMPLEX_RULE_SECTIONS.keys())

    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$ne': '', '$not': {'$regex': r'^See rule \d'}}},
        {'rule_number': 1, 'text': 1}
    ))

    # Filter to rules from complex sections with substantial text
    complex_rules = []
    for rule in all_rules:
        num = rule.get('rule_number', '')
        text = rule.get('text', '')
        if len(text) < 80:
            continue
        # Check if this rule is in a complex section
        for prefix in complex_section_prefixes:
            if num.startswith(prefix):
                section_name = COMPLEX_RULE_SECTIONS[prefix]
                rule['section_name'] = section_name
                complex_rules.append(rule)
                break

    random.shuffle(complex_rules)
    print(f"  → Found {len(complex_rules):,} rules in complex sections")

    for rule in complex_rules:
        if len(mongo_documents) >= target_count:
            break

        rule_num = rule.get('rule_number', '')
        rule_text = rule.get('text', '')
        section_name = rule.get('section_name', 'General Rules')

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_edge_case_prompt(rule_num, rule_text, section_name)

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
                        print(f"    ✗ REJECTED (rule number not cited): {qa['question'][:60]}")
                        continue
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Rule {rule_num} ({section_name}): {rule_text}",
                        category="rule_edge_case"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "rule_edge_case",
                            "source_data": [f"rule_{rule_num}"],
                            "rule_number": rule_num,
                            "section": section_name,
                            "rule_text": rule_text,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10, rule {rule_num}, {section_name}): {qa['question'][:60]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:60]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rule {rule_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule edge case questions")
    return mongo_documents

