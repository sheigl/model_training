import pymongo
from query_model import QueryModel
import json
from common import MODEL_NAME, build_rules_scenario_prompt

def generate_rules_scenarios(target_count=3000) -> list[dict]:
    """
    Generate scenario-based rules Q&A that teaches rules reasoning.

    Examples:
    - "I cast Lightning Bolt, they respond with Giant Growth. What happens?"
    - "My creature has lifelink and deathtouch. What happens when it deals damage?"
    - "Can I activate a planeswalker ability the turn it enters?"
    """
    print(f"\n=== GENERATING {target_count:,} RULES SCENARIO QUESTIONS ===")
    mongo_documents = []

    scenarios = [
        (
            "spell resolution and the stack",
            "Last in first out stack resolution, responding to spells, fizzling spells, counterspells"
        ),
        (
            "combat damage and blocking",
            "Assigning combat damage, trample, first strike, double strike, deathtouch in combat, lifelink in combat"
        ),
        (
            "triggered abilities and timing",
            "When triggered abilities go on the stack, controlling the order of your own triggers, missed triggers"
        ),
        (
            "state-based actions",
            "Creatures dying from lethal damage or 0 toughness, legend rule, planeswalker uniqueness rule, poison counters"
        ),
        (
            "activated abilities and costs",
            "Paying costs for activated abilities, tapping as a cost, sacrifice as a cost, mana abilities"
        ),
        (
            "replacement effects and prevention effects",
            "How replacement effects modify events, prevention effects, damage prevention, redirection"
        ),
        (
            "keyword abilities interactions",
            "How keywords interact: hexproof vs targeting, shroud vs targeting, indestructible vs destroy vs exile, regenerate"
        ),
        (
            "Commander-specific rules",
            "Commander tax, commander damage, moving to command zone vs graveyard, color identity in deck building"
        ),
        (
            "planeswalker rules",
            "Activating planeswalker abilities, attacking planeswalkers, the planeswalker uniqueness rule, loyalty counters"
        ),
        (
            "token and copy rules",
            "Creating tokens, copying spells, copying permanents, token characteristics, copy effects on the stack"
        ),
        (
            "priority and passing priority",
            "When players receive priority, how to sequence actions, when you can and cannot respond"
        ),
        (
            "enters the battlefield and leaves the battlefield triggers",
            "ETB triggers, LTB triggers, flicker effects, blink, phasing, bouncing permanents"
        ),
        (
            "targeting and illegal targets",
            "Choosing targets on announcement, targets becoming illegal before resolution, fizzling"
        ),
        (
            "mana and casting",
            "Mana pool, emptying the mana pool, split second, flash, timing restrictions for casting spells"
        ),
        (
            "graveyard and exile interactions",
            "Cards going to graveyard, replacement effects for dying, exile vs graveyard, returning from exile"
        ),
    ]

    for scenario, rules in scenarios:
        if len(mongo_documents) >= target_count:
            break

        print(f"  → {scenario}")
        prompt = build_rules_scenario_prompt(scenario, rules)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)

            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa and len(qa['answer']) > 100:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Rules topic: {scenario}\nRelevant rules: {rules}",
                        category="rules_scenario"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "rules_scenario",
                            "source_data": ["comprehensive_rules"],
                            "rules_topic": scenario,
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
            print(f"  ✗ Error for scenario '{scenario}': {type(e).__name__}: {e}")
            continue

    print(f"  ✓ Generated {len(mongo_documents):,} rules scenario questions")
    return mongo_documents

