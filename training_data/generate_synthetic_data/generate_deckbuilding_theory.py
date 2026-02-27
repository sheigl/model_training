import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_deckbuilding_theory_prompt

def generate_deckbuilding_theory(target_count=2000) -> list[dict]:
    """
    Generate deckbuilding theory Q&A covering card evaluation, ratios, construction principles.

    Examples:
    - "How do I evaluate whether a card earns its slot?"
    - "What's the difference between card advantage and card selection?"
    - "How do I know when to cut cards during tuning?"
    """
    print(f"\n=== GENERATING {target_count:,} DECKBUILDING THEORY QUESTIONS ===")
    mongo_documents = []

    topics = [
        (
            "card evaluation and slot justification",
            "How to determine if a card belongs in your deck, evaluating cards on rate, role, and redundancy."
        ),
        (
            "card advantage vs card selection",
            "The difference between drawing more cards (Rhystic Study) vs filtering cards (Ponder). When each matters."
        ),
        (
            "mana curve and tempo",
            "How to build a mana curve, what tempo means, why you want to spend mana efficiently each turn."
        ),
        (
            "redundancy and consistency",
            "Why you run multiple effects that do similar things, how to determine the right amount of redundancy."
        ),
        (
            "synergy vs goodstuff",
            "The tradeoff between running powerful generic cards vs cards that specifically support your strategy."
        ),
        (
            "win conditions and closing games",
            "How to identify your win conditions, ensure they're reachable, and have enough redundancy to close games."
        ),
        (
            "deck tuning and iteration",
            "How to identify what's wrong with a deck after testing, what to cut, what to add, how to iterate."
        ),
        (
            "threat density and role assignment",
            "Assigning cards roles (threat, answer, engine, accelerant) and ensuring the right density of each."
        ),
        (
            "mana base construction",
            "How to build a mana base, dual lands vs basics, color ratios, when to run utility lands."
        ),
        (
            "protection and resilience",
            "How to protect your key pieces, recover from board wipes, maintain card advantage after setbacks."
        ),
        (
            "interaction and removal philosophy",
            "When to hold up interaction vs advance your game plan, reactive vs proactive playstyles."
        ),
        (
            "tribal deck construction",
            "Special considerations for tribal decks: lord effects, creature density, tribal synergies, non-creature support."
        ),
    ]

    for topic, context in topics:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {topic}")
        prompt = build_deckbuilding_theory_prompt(topic, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Topic: {topic}\nContext: {context}",
                        category="deckbuilding_theory"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "deckbuilding_theory",
                            "source_data": ["deckbuilding_theory"],
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

    print(f"  ✓ Generated {len(mongo_documents):,} deckbuilding theory questions")
    return mongo_documents
