import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_game_theory_prompt, validate_qa

def generate_game_theory(target_count=1500) -> list[dict]:
    """
    Generate game theory and decision-making Q&A.

    Examples:
    - "When should I use removal on a creature vs holding it?"
    - "How do I evaluate whether a hand is worth keeping?"
    - "When is it correct to attack the player in the lead?"
    """
    print(f"\n=== GENERATING {target_count:,} GAME THEORY QUESTIONS ===")
    mongo_documents = []

    situations = [
        (
            "threat assessment and removal sequencing",
            "Deciding which threats to answer immediately vs ignore, when to hold removal, opportunity cost of using removal early"
        ),
        (
            "opening hand evaluation and mulliganing",
            "What makes a hand keepable, when to mulligan, evaluating land count, curve, and role of each card in opening hand"
        ),
        (
            "sequencing spells for maximum efficiency",
            "Playing around counterspells, ordering your spells to maximize impact, sandbagging threats"
        ),
        (
            "mana efficiency and tempo",
            "Spending all your mana every turn, tempo advantage, knowing when to hold up mana vs spend it"
        ),
        (
            "multiplayer politics and deal-making",
            "When to make deals in Commander, how to evaluate political deals, threat perception, being the archenemy"
        ),
        (
            "threat perception and table dynamics",
            "Recognizing who is ahead, when to team up vs go it alone, threat ordering in multiplayer"
        ),
        (
            "when to go all-in vs play conservatively",
            "Assessing when it's correct to commit your hand to the board vs hold back, playing around sweepers"
        ),
        (
            "card advantage decisions",
            "When to use your card draw, whether to refill your hand or deploy threats, resource management"
        ),
        (
            "combat math and blocking decisions",
            "How to evaluate attack and block decisions, when to take damage vs trade creatures, alpha strikes"
        ),
        (
            "timing your win attempt",
            "Reading the table to know when to go for the win, when opponents are tapped out, winning through disruption"
        ),
    ]

    for situation, context in situations:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {situation}")
        prompt = build_game_theory_prompt(situation, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Situation: {situation}\nContext: {context}",
                        category="game_theory"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "game_theory",
                            "source_data": ["strategy"],
                            "situation_type": situation,
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
            print(f"  ✗ Error for situation '{situation}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} game theory questions")
    return mongo_documents

