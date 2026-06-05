from rich.console import Console
from query_model import QueryModel
import json
from common import build_deckbuilding_theory_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateDeckbuildingTheory:
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

    def generate_deckbuilding_theory(self) -> None:
        """Generate deckbuilding theory Q&A - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} DECKBUILDING THEORY QUESTIONS ===")

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

        query_model = QueryModel()
        total_generated = 0

        for topic, context in topics:
            if total_generated >= target_count:
                break

            print(f"  → {topic}")
            prompt = build_deckbuilding_theory_prompt(topic, context)

            try:
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"Topic: {topic}\nContext: {context}"

                for qa in qa_pairs:
                    if total_generated >= target_count:
                        break

                    if len(qa.answer) <= 80:
                        print(f"    ✗ REJECTED (too short): {qa.question[:80]}")
                        continue

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=[qa],
                        validation_pct=validation_pct,
                        enable_extra_validation=False,
                        build_context=lambda: qa_context,
                        source_category="deckbuilding_theory",
                        source_data=["deckbuilding_theory"],
                        source_template=None,
                        metrics=self.metrics
                    )

                    if is_valid and doc:
                        doc.topic = topic  # type: ignore[attr-defined]
                        save_item(doc)
                        total_generated += 1

            except Exception as e:
                print(f"  ✗ Error for topic '{topic}': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {total_generated:,} deckbuilding theory questions")
