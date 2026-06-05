from rich.console import Console
from query_model import QueryModel
import json
from common import build_commander_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateCommanderKnowledge:
    def __init__(
        self,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=200,
        metrics: ValidationMetrics | None = None) -> None:

        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_commander_knowledge(self) -> None:
        """Generate Commander knowledge - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} COMMANDER KNOWLEDGE ===")

        prompt = build_commander_prompt()
        query_model = QueryModel()

        try:
            response = query_model.query(models[ModelType.GENERATION], prompt)
            response = response.replace("```json", "").replace("```", "").strip()
            qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

            qa_context = "Commander format rules: 100-card singleton, commander in command zone, commander tax, commander damage, color identity restrictions."

            for qa in qa_pairs:
                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=[qa],
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="commander_rules",
                    source_data=["commander_format_rules"],
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    save_item(doc)

        except Exception as e:
            print(f"  Error: {type(e).__name__}: {e}")

        print(f"  ⚠️  Needs manual review!")
