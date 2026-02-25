import pymongo
from query_ollama import *
import json
from common import MODEL_NAME, build_meta_knowledge_prompt

def generate_meta_knowledge(target_count=1000) -> list[dict]:
    """
    Generate meta and power level Q&A covering cEDH, pod dynamics, and format knowledge.

    Examples:
    - "What makes a deck cEDH viable?"
    - "How do I calibrate my deck's power level?"
    - "What separates a 7/10 from a 9/10 Commander deck?"
    """
    print(f"\n=== GENERATING {target_count:,} META KNOWLEDGE QUESTIONS ===")
    mongo_documents = []

    topics = [
        (
            "cEDH viability and what separates competitive from casual",
            "cEDH decks win on turns 3-5, use fast mana (Mana Crypt, Chrome Mox), run tutors, counterspells, and win through established combo lines. Power level 9-10."
        ),
        (
            "Commander power level scale (1-10)",
            "The 1-10 power level scale: 1-3 precon/kitchen table, 4-6 focused casual, 7-8 optimized synergy, 9 high power, 10 cEDH. How to self-assess your deck."
        ),
        (
            "pod communication and power level matching",
            "How to communicate your deck's power level to your pod, why mismatched power levels ruin games, asking before you sit down."
        ),
        (
            "fast mana and why it's powerful",
            "Sol Ring, Mana Crypt, Chrome Mox — why fast mana is so format-warping, what separates high power from casual, the role of 0-cost acceleration."
        ),
        (
            "tutors and deck consistency",
            "How tutors increase consistency, why tutors are stronger in Commander than other formats, the tradeoff between consistency and fun."
        ),
        (
            "common cEDH win conditions and strategies",
            "Flash Hulk, Thassa's Oracle + Demonic Consultation, Underworld Breach loops, Dockside Extortionist combos — recognizing and playing against them."
        ),
        (
            "evaluating commanders for power level",
            "What makes a commander powerful: built-in card advantage, low mana cost, combo enabler, resilience. Why some commanders are format staples."
        ),
        (
            "meta reads and adapting your deck",
            "Reading your local meta, building hate for common strategies, adjusting your deck for the environment you play in."
        ),
        (
            "banned list philosophy in Commander",
            "Why certain cards are banned in Commander (Flash, Primeval Titan, Braids), how the rules committee evaluates bans, why some powerful cards aren't banned."
        ),
    ]

    for topic, context in topics:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {topic}")
        prompt = build_meta_knowledge_prompt(topic, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Topic: {topic}\nContext: {context}",
                        category="meta_knowledge"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "meta_knowledge",
                            "source_data": ["meta_strategy"],
                            "topic": topic,
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                        if len(mongo_documents) >= target_count:
                            break
                    else:
                        print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                else:
                    print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
        except Exception as e:
            print(f"  ✗ Error for topic '{topic}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} meta knowledge questions")
    return mongo_documents

