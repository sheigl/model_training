
import json

from training_data.generate_synthetic_data import query_ollama
from training_data.generate_synthetic_data.common import *

def generate_archetypes(target_count=1500) -> list[dict]:
    """
    Generate deck archetype and strategy Q&A.

    Examples:
    - "How does a stax deck win?"
    - "What are the weaknesses of voltron?"
    - "How do I recognize a storm deck?"
    """
    print(f"\n=== GENERATING {target_count:,} ARCHETYPE QUESTIONS ===")
    mongo_documents = []

    archetypes = [
        (
            "stax/prison",
            "Stax uses symmetrical and asymmetrical tax effects and lock pieces to slow opponents to a crawl. Win conditions are usually faster mana and hatebears. Cards like Smokestack, Winter Orb, Sphere of Resistance, and Cursed Totem."
        ),
        (
            "storm/spellslinger combo",
            "Storm decks chain spells to generate a large storm count and win with Tendrils of Agony or Brain Freeze. Require rituals, cantrips, and a way to win at high storm count. Fragile to counterspells."
        ),
        (
            "aggro/tempo",
            "Aggressive decks develop threats quickly and attack the opponent's life total before they can set up. Rely on efficient creatures, haste, and pump spells. Weaker in longer games."
        ),
        (
            "hard control",
            "Control decks answer every threat with counterspells, removal, and board wipes, winning with a single powerful threat in the late game. Card advantage is paramount."
        ),
        (
            "midrange",
            "Midrange decks play powerful cards at every mana cost and win through card quality rather than synergy. Flexible but less explosive than combo or aggro."
        ),
        (
            "infinite combo",
            "Infinite combo decks assemble two or more cards that create an infinite loop — infinite mana, infinite creatures, infinite damage. Win immediately on assembly."
        ),
        (
            "reanimator",
            "Reanimator puts large expensive creatures into the graveyard cheaply (via discard, mill, or self-mill) and brings them back for cheap. Fast and resilient but weak to graveyard hate."
        ),
        (
            "aristocrats/sacrifice",
            "Aristocrats generates value from creatures dying repeatedly. Uses Blood Artist-style effects, recursive creatures, and sacrifice outlets to drain opponents incrementally."
        ),
        (
            "tokens/go wide",
            "Token strategies flood the board with small creatures and win through wide attacks, token doublers, or sacrifice payoffs. Weak to board wipes, strong against single-target removal."
        ),
        (
            "voltron",
            "Voltron buffs one creature to enormous size and wins through combat damage, often specifically 21 commander damage. Equipment-based voltron is more resilient than aura-based."
        ),
        (
            "group hug",
            "Group hug gives all players resources (card draw, mana, etc.) to stay out of the crosshairs while building toward a secret win condition. Political and unique playstyle."
        ),
        (
            "lands/landfall",
            "Lands-matter decks maximize land drops per turn and use landfall triggers to generate value. Often use extra land effects, land recursion, and powerful landfall payoffs."
        ),
    ]

    for archetype, context in archetypes:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {archetype}")
        prompt = build_archetype_prompt(archetype, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                    is_valid, reason, score = query_ollama.validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Archetype: {archetype}\nContext: {context}",
                        category="archetype"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "archetype",
                            "source_data": ["strategy"],
                            "archetype": archetype,
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
            print(f"  ✗ Error for archetype '{archetype}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} archetype questions")
    return mongo_documents

