import random

import pymongo
from query_ollama import *
import json
from common import MODEL_NAME, build_rule_interaction_prompt

def generate_rule_interactions(rules_collection, target_count=2000) -> list[dict]:
    """
    Generate scenario Q&A where two rules interact.
    Grounded in actual rule text from both rules.

    Examples:
    - "I have a creature with deathtouch that deals 1 damage to a 5/5. What happens?" (702.2 + 704.5g)
    - "A triggered ability and a state-based action happen simultaneously. Which applies first?"
    """
    print(f"\n=== GENERATING {target_count:,} RULE INTERACTION QUESTIONS ===")
    mongo_documents = []

    # Fetch rules and group by section for pairing rules from related sections
    print("  → Fetching rules for interaction pairing...")
    all_rules = list(rules_collection.find(
        {'text': {'$exists': True, '$not': {'$regex': r'^See rule \d'}}, },
        {'rule_number': 1, 'text': 1}
    ))

    meaningful_rules = [r for r in all_rules if len(r.get('text', '')) > 60]

    # Group rules by top-level section number
    rules_by_section = {}
    for rule in meaningful_rules:
        num = rule.get('rule_number', '')
        section = num.split('.')[0] if '.' in num else num[:3]
        if section not in rules_by_section:
            rules_by_section[section] = []
        rules_by_section[section].append(rule)

    print(f"  → Grouped into {len(rules_by_section)} sections")

    # Define section pairs that commonly interact in real games
    interaction_pairs = [
        ('601', '116'),  # Casting spells + Priority
        ('603', '116'),  # Triggered abilities + Priority
        ('603', '704'),  # Triggered abilities + State-based actions
        ('608', '603'),  # Resolving spells + Triggered abilities
        ('702', '120'),  # Keyword abilities + Damage
        ('702', '704'),  # Keyword abilities + State-based actions
        ('706', '603'),  # Copying + Triggered abilities
        ('601', '117'),  # Casting + Costs
        ('700', '116'),  # Additional rules + Priority
        ('800', '116'),  # Multiplayer + Priority
        ('903', '603'),  # Commander + Triggered abilities
        ('120', '704'),  # Damage + State-based actions
        ('118', '117'),  # Paying costs + Costs
        ('604', '603'),  # Static abilities + Triggered abilities
    ]

    attempts = 0
    max_attempts = target_count * 3

    while len(mongo_documents) < target_count and attempts < max_attempts:
        attempts += 1

        # Pick a section pair
        sec1, sec2 = random.choice(interaction_pairs)

        rules1 = rules_by_section.get(sec1, [])
        rules2 = rules_by_section.get(sec2, [])

        if not rules1 or not rules2:
            continue

        rule1 = random.choice(rules1)
        rule2 = random.choice(rules2)

        rule1_num = rule1.get('rule_number', '')
        rule1_text = rule1.get('text', '')
        rule2_num = rule2.get('rule_number', '')
        rule2_text = rule2.get('text', '')

        if not all([rule1_num, rule1_text, rule2_num, rule2_text]):
            continue

        if (len(mongo_documents) + 1) % 100 == 0:
            print(f"    Generated {len(mongo_documents):,}/{target_count:,}...")

        prompt = build_rule_interaction_prompt(rule1_num, rule1_text, rule2_num, rule2_text)

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
                    # Validate: both rule numbers must appear in the answer
                    has_rule1 = rule1_num in qa['answer']
                    has_rule2 = rule2_num in qa['answer']
                    if not has_rule1 or not has_rule2:
                        print(f"    ✗ REJECTED (missing rule refs r1:{has_rule1} r2:{has_rule2}): {qa['question'][:60]}")
                        continue
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Rule {rule1_num}: {rule1_text}\nRule {rule2_num}: {rule2_text}",
                        category="rule_interaction"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "rule_interaction",
                            "source_data": [f"rule_{rule1_num}", f"rule_{rule2_num}"],
                            "rule_numbers": [rule1_num, rule2_num],
                            "sections": [sec1, sec2],
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10, rules {rule1_num}+{rule2_num}): {qa['question'][:70]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:70]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:60]}")
        except Exception as e:
            print(f"  ✗ Error for rules {rule1_num}+{rule2_num}: {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rule interaction questions")
    return mongo_documents

