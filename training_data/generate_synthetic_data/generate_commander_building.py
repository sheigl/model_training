import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_commander_building_prompt

def generate_commander_building(target_count=3000) -> list[dict]:
    """
    Generate Commander-specific deckbuilding Q&A for various archetypes and strategies.

    Examples:
    - "How do I build around a sacrifice commander?"
    - "What's the right threat density for a control commander?"
    - "How do I balance synergy vs goodstuff in Commander?"
    """
    print(f"\n=== GENERATING {target_count:,} COMMANDER BUILDING QUESTIONS ===")
    mongo_documents = []

    archetypes = [
        (
            "sacrifice/aristocrats",
            "Decks that sacrifice creatures for value, using Blood Artist-style effects, sac outlets, and token generators. Key challenge: balancing fodder, payoffs, and sac outlets."
        ),
        (
            "spellslinger/magecraft",
            "Decks that cast lots of instants and sorceries, using magecraft triggers, prowess, and spell-based win conditions. Key challenge: protecting your win condition while staying low to the ground."
        ),
        (
            "token swarm",
            "Decks that generate many creature tokens and win through wide attacks or combo. Key challenge: having enough anthems and ways to win through chump blockers."
        ),
        (
            "reanimator",
            "Decks that put big creatures in the graveyard and reanimate them cheaply. Key challenge: filling the graveyard, protecting the reanimation target, winning with the reanimated creature."
        ),
        (
            "combo",
            "Decks that assemble a specific combination of cards to win instantly or lock opponents out. Key challenge: finding the combo pieces, protecting the combo, having backup win conditions."
        ),
        (
            "control",
            "Decks that answer every threat and win through superior card advantage in the late game. Key challenge: staying relevant in multiplayer, having a win condition that can close through disruption."
        ),
        (
            "voltron",
            "Decks that buff one creature (usually the commander) with equipment and auras to win through commander damage. Key challenge: protecting your commander, rebuilding after removal, winning through 21 combat damage."
        ),
        (
            "stax/prison",
            "Decks that use symmetrical or asymmetrical effects to slow opponents while you advance your own game plan. Key challenge: calibrating the lock pieces so you can still win, not making the game unfun."
        ),
        (
            "landfall/lands matter",
            "Decks that trigger off lands entering the battlefield, using extra land effects and landfall payoffs. Key challenge: getting enough lands into play per turn, balancing consistency with power."
        ),
        (
            "graveyard value",
            "Decks that use the graveyard as a resource without necessarily being reanimator — flashback, delve, threshold, cycling. Key challenge: filling the graveyard efficiently, playing around graveyard hate."
        ),
        (
            "turbo draw/card advantage",
            "Decks built around drawing as many cards as possible to find combo pieces or assemble overwhelming card advantage. Key challenge: using the cards drawn effectively, not decking yourself."
        ),
        (
            "midrange goodstuff",
            "Decks that play powerful cards at every part of the curve without a focused synergy strategy. Key challenge: distinguishing this from a tuned synergy deck, knowing when to choose goodstuff over theme."
        ),
    ]

    for archetype, context in archetypes:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {archetype}")
        prompt = build_commander_building_prompt(archetype, context)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Archetype: {archetype}\nContext: {context}",
                        category="commander_building"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "commander_building",
                            "source_data": ["commander_format"],
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

    print(f"  ✓ Generated {len(mongo_documents):,} Commander building questions")
    return mongo_documents

