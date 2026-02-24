import pymongo
import query_ollama
import json
from common import MODEL_NAME, build_quick_guidelines_prompt, validate_qa

def generate_quick_guidelines(target_count=2000) -> list[dict]:
    """
    Generate quick deckbuilding guideline questions
    
    Examples:
    - "How many lands in a 100-card deck?"
    - "How much ramp is enough?"
    - "How many board wipes should I run?"
    """
    print(f"\n=== GENERATING {target_count:,} QUICK GUIDELINE QUESTIONS ===")
    mongo_documents = []
    
    # Curated deckbuilding guidelines
    guidelines = [
        ("How many lands in a 100-card Commander deck?", "A typical Commander deck runs 36-40 lands, with 37-38 being most common. Adjust based on your average mana cost and amount of ramp."),
        ("How much ramp should I include?", "Include 8-12 ramp sources (mana rocks, land ramp spells, or mana dorks) to ensure consistent mana development."),
        ("How many board wipes should I run?", "Run 3-5 board wipes in most decks. More in control, fewer in aggressive strategies."),
        ("How much card draw do I need?", "Include 8-12 sources of card draw or card advantage. Commander games go long, and you need to keep your hand full."),
        ("How much removal should I include?", "Run 8-12 targeted removal spells. Include a mix of creature removal, artifact/enchantment removal, and flexible answers."),
        ("What's a good mana curve?", "Peak at 2-3 mana, with most spells costing 2-4 mana. Include some expensive bombs but keep your average CMC around 3-4."),
        ("How many creatures should I run?", "Most decks run 20-35 creatures. Creature-heavy strategies might run 35-40, while spell-based decks might run 15-20."),
        ("What's the right number of counterspells?", "Blue control decks typically run 5-8 counterspells. Include a mix of cheap counters and versatile ones."),
        ("How many tutors should I include?", "2-5 tutors is typical. More tutors make your deck more consistent but can make games repetitive."),
        ("What's a good balance of instant vs sorcery speed?", "Aim for 60-70% instant speed interaction when possible. Instant speed is more flexible in multiplayer."),
        ("How many win conditions do I need?", "Include 2-4 distinct ways to win. This ensures you can close out games and have backup plans."),
        ("How much protection should I run?", "Include 4-6 ways to protect your key pieces (counterspells, hexproof, indestructible, recursion)."),
        ("What's the right amount of recursion?", "3-5 recursion effects lets you recover from removal and board wipes without being excessive."),
        ("How many mana rocks for artifact-based ramp?", "5-8 mana rocks is typical, with Sol Ring and Arcane Signet being auto-includes in most decks."),
        ("How do I know if I have enough interaction?", "Aim for 12-15 total interaction pieces (removal, counterspells, board wipes, protection)."),
    ]
    
    print(f"  → Using {len(guidelines)} curated guidelines...")
    
    # Generate variations with Qwen
    for base_question, base_answer in guidelines:
        if len(mongo_documents) >= target_count:
            break
        
        prompt = build_quick_guidelines_prompt(base_question, base_answer)

        try:
            response = query_ollama(MODEL_NAME, prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = json.loads(response)
            
            for qa in qa_pairs:
                if 'question' in qa and 'answer' in qa:
                    is_valid, reason, score = validate_qa(
                        qa['question'], qa['answer'],
                        context=f"Deckbuilding guideline: {base_question}\nExpected answer direction: {base_answer}",
                        category="guideline"
                    )
                    if is_valid:
                        mongo_documents.append({
                            "question": qa['question'],
                            "answer": qa['answer'],
                            "category": "guideline",
                            "source_data": ["deckbuilding_guidelines"],
                            "guideline_type": "deckbuilding",
                            "validated": True,
                            "validation_score": score,
                            "needs_review": False
                        })
                        print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")

                    if len(mongo_documents) >= target_count:
                        break
                else:
                    print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
        except Exception as e:
            print(f"  ✗ Error generating guideline variation for '{base_question[:50]}...': {type(e).__name__}: {e}")
            # If generation fails, use original
            mongo_documents.append({
                "question": base_question,
                "answer": base_answer,
                "category": "guideline",
                "source_data": ["deckbuilding_guidelines"],
                "guideline_type": "deckbuilding",
                "validated": True,
                "needs_review": False
            })
    
    print(f"  ✓ Generated {len(mongo_documents):,} guideline questions")
    return mongo_documents

