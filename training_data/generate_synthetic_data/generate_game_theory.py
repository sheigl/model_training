from rich.console import Console
from query_model import QueryModel
import json
from common import build_game_theory_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateGameTheory:
    def __init__(
        self,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=1500,
        metrics: ValidationMetrics | None = None) -> None:

        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_game_theory(self) -> None:
        """Generate game theory and decision-making Q&A - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} GAME THEORY QUESTIONS ===")

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

        query_model = QueryModel()
        total_generated = 0

        for situation, context in situations:
            if total_generated >= target_count:
                break

            print(f"  → {situation}")
            prompt = build_game_theory_prompt(situation, context)

            try:
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"Situation: {situation}\nContext: {context}"

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
                        source_category="game_theory",
                        source_data=["strategy"],
                        source_template=None,
                        metrics=self.metrics
                    )

                    if is_valid and doc:
                        doc.situation_type = situation  # type: ignore[attr-defined]
                        save_item(doc)
                        total_generated += 1

            except Exception as e:
                print(f"  ✗ Error for situation '{situation}': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {total_generated:,} game theory questions")
