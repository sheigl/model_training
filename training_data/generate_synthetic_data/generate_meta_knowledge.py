from rich.console import Console
from query_model import QueryModel
import json
from common import build_meta_knowledge_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateMetaKnowledge:
    def __init__(
        self,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=1000,
        metrics: ValidationMetrics | None = None) -> None:

        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_meta_knowledge(self) -> None:
        """Generate meta and power level Q&A - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} META KNOWLEDGE QUESTIONS ===")

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

        query_model = QueryModel()
        total_generated = 0

        for topic, context in topics:
            if total_generated >= target_count:
                break

            print(f"  → {topic}")
            prompt = build_meta_knowledge_prompt(topic, context)

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
                        source_category="meta_knowledge",
                        source_data=["meta_strategy"],
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

        print(f"  ✓ Generated {total_generated:,} meta knowledge questions")
