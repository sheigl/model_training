import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_multi_card_usage_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()


class GenerateMultiCardUsage:
    def __init__(
        self,
        combos_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 2000,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.combos_collection = combos_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_multi_card_usage(self) -> None:
        """Generate multi-card usage - returns MongoDB documents"""

        combos_collection = self.combos_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} MULTI-CARD USAGE ===")

        combos: list[dict] = []

        with console.status("[bold green]Extracting combo data...") as status:
            combos = list(combos_collection.find({'status': 'OK'}).limit(target_count * 2))

        print(f"  → Processing {len(combos)} combos...")

        num_docs = 0

        for combo in combos:
            if num_docs >= target_count:
                break

            cards = combo.get('uses', [])
            card_names = [c.get('card', {}).get('name', '') for c in cards if c.get('card')]
            description = combo.get('description', '')

            if len(card_names) < 2 or not description:
                continue

            card1, card2 = card_names[0], card_names[1]

            prompt = build_multi_card_usage_prompt(card1, card2, description)

            try:
                query_model = QueryModel()
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"""
Cards: {', '.join(card_names)}
Combo/interaction: {description}
"""

                source_data: list[Any] = card_names + [description]

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=qa_pairs,
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="multi_card_usage",
                    source_data=source_data,
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    save_item(doc)
                    num_docs += 1

            except Exception as e:
                print(f"  ✗ Error generating for {card1} + {card2}: {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {num_docs:,} multi-card usage")
