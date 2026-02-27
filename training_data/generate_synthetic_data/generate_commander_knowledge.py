import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_commander_prompt

def generate_commander_knowledge(target_count=200) -> list[dict]:
    """Generate Commander knowledge - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} COMMANDER KNOWLEDGE ===")
    mongo_documents = []
    
    prompt = build_commander_prompt()

    try:
        response =  query_ollama(MODEL_NAME, prompt, max_tokens=9999)
        response = response.replace("```json", "").replace("```", "").strip()
        qa_pairs = json.loads(response)
        
        for qa in qa_pairs:
            if 'question' in qa and 'answer' in qa:
                is_valid, reason, score = validate_qa(
                    qa['question'], qa['answer'],
                    context="Commander format rules: 100-card singleton, commander in command zone, commander tax, commander damage, color identity restrictions.",
                    category="commander_rules"
                )
                if is_valid:
                    mongo_documents.append({
                        "question": qa['question'],
                        "answer": qa['answer'],
                        "category": "commander_rules",
                        "source_data": ["commander_format_rules"],
                        "validated": True,
                        "validation_score": score,
                        "needs_review": False
                    })
                    print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
            else:
                print(f"    ✗ REJECTED (missing question/answer keys): {qa}")

    except Exception as e:
        print(f"  Error: {type(e).__name__}: {e}")
    
    print(f"  ✓ Generated {len(mongo_documents):,} Commander rules")
    print(f"  ⚠️  Needs manual review!")
    return mongo_documents