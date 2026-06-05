import random
import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import build_color_staples_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 2000
console = Console()

class GenerateColorStaples:
    def __init__(
        self,
        top_cards_dict: dict[str, pymongo.collection.Collection],  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = DEFAULT,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.top_cards_dict = top_cards_dict
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_color_staples(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} COLOR STAPLE QUESTIONS ===")

        per_color = self.target_count // len(self.top_cards_dict) if self.top_cards_dict else 0
        total_generated: int = 0

        for color, collection in self.top_cards_dict.items():
            if total_generated >= self.target_count:
                break

            print(f"  → Processing {color}...")

            top_cards: list[dict] = []
            with console.status(f"[bold green]Extracting top cards for {color}...") as status:
                top_cards = list(
                    collection.find(
                        {"oracle_text": {"$exists": True}},
                        {
                            "name": 1,
                            "oracle_text": 1,
                            "num_decks": 1,
                            "tags": 1,
                            "type": 1,
                            "mana_cost": 1,
                            "color_identity": 1,
                        },
                    )
                    .sort("num_decks", -1)
                    .limit(30)
                )
                status.update(f"[bold green]Extracted {len(top_cards)} cards for {color}")

            if not top_cards:
                print(f"    ⚠️  No cards found for {color}")
                continue

            subsets = [top_cards[:10], top_cards[10:20], top_cards[20:30]]
            color_count: int = 0

            for subset in subsets:
                if color_count >= per_color or total_generated >= self.target_count:
                    break
                if not subset:
                    continue

                prompt = build_color_staples_prompt(color, subset)
                card_names = [c.get("name", "") for c in subset]

                try:
                    query_model = QueryModel()
                    response = query_model.query(self.models[ModelType.GENERATION], prompt)
                    qa_pairs = list(
                        map(
                            lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                            json.loads(response),
                        )
                    )

                    qa_context = f"Color: {color}\nTop staple cards: {', '.join(card_names[:10])}"

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=self.models,
                        qa_pairs=qa_pairs,
                        validation_pct=self.validation_pct,
                        enable_extra_validation=False,
                        build_context=lambda: qa_context,
                        source_category="color_staples",
                        source_data=card_names[:5],
                        source_template=None,
                        metrics=self.metrics,
                    )

                    if is_valid and doc:
                        self.save_item(doc)
                        color_count += 1
                        total_generated += 1
                        if (total_generated) % 100 == 0:
                            print(f"    Generated {total_generated:,}/{self.target_count:,}...")

                except Exception as e:
                    print(f"  ✗ Error for {color} subset: {type(e).__name__}: {e}")
                    continue

            print(f"  ✓ {color}: {color_count:,} questions")

        print(f"  ✓ Generated {total_generated:,} color staple questions")
