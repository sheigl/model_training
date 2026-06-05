from rich.console import Console
from query_model import QueryModel
import json
from common import build_quick_guidelines_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateQuickGuidelines:
    def __init__(
        self,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=2000,
        metrics: ValidationMetrics | None = None) -> None:

        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_quick_guidelines(self) -> None:
        """Generate quick deckbuilding guideline questions - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} QUICK GUIDELINE QUESTIONS ===")

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
        query_model = QueryModel()
        total_generated = 0

        for base_question, base_answer in guidelines:
            if total_generated >= target_count:
                break

            # Validate the base Q&A first
            base_qa_pairs = [QuestionAnswer(base_question, base_answer)]
            base_context = f"Deckbuilding guideline: {base_question}\nExpected answer direction: {base_answer}"

            is_valid, doc = validate_and_loop_with_suggested_fix(
                query_model=query_model,
                models=models,
                qa_pairs=base_qa_pairs,
                validation_pct=validation_pct,
                enable_extra_validation=False,
                build_context=lambda: base_context,
                source_category="guideline",
                source_data=["deckbuilding_guidelines"],
                source_template=None,
                metrics=self.metrics
            )

            if is_valid and doc:
                save_item(doc)
                total_generated += 1

            if total_generated >= target_count:
                break

            # Generate variations with LLM
            prompt = build_quick_guidelines_prompt(base_question, base_answer)

            try:
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                for qa in qa_pairs:
                    if total_generated >= target_count:
                        break

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=[qa],
                        validation_pct=validation_pct,
                        enable_extra_validation=False,
                        build_context=lambda: base_context,
                        source_category="guideline",
                        source_data=["deckbuilding_guidelines"],
                        source_template=None,
                        metrics=self.metrics
                    )

                    if is_valid and doc:
                        save_item(doc)
                        total_generated += 1

            except Exception as e:
                print(f"  ✗ Error generating guideline variation for '{base_question[:50]}...': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {total_generated:,} guideline questions")
