import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import build_salt_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 1000
console = Console()

class GenerateSaltQuestions:
    def __init__(
        self,
        game_changers_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = DEFAULT,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.game_changers_collection = game_changers_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_salt_questions(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} SALT QUESTIONS ===")

        salty_cards: list[dict] = []
        with console.status("[bold green]Extracting high-salt cards...") as status:
            salty_cards = list(
                self.game_changers_collection.find(
                    {"salt": {"$gte": 1.2}, "oracle_text": {"$exists": True, "$ne": ""}},
                    {
                        "name": 1,
                        "oracle_text": 1,
                        "type": 1,
                        "mana_cost": 1,
                        "num_decks": 1,
                        "salt": 1,
                        "tags": 1,
                        "color_identity": 1,
                    },
                ).sort("salt", -1)
            )
            status.update(f"[bold green]Extracted {len(salty_cards):,} high-salt cards")

        print(f"  → Found {len(salty_cards):,} high-salt cards (salt >= 1.2)")

        batch_size = 8
        batches = [salty_cards[i : i + batch_size] for i in range(0, len(salty_cards), batch_size)]

        batch_idx: int = 0
        for batch in batches:
            if batch_idx >= self.target_count:
                break

            if (batch_idx + 1) % 100 == 0:
                print(f"    Generated {batch_idx:,}/{self.target_count:,}...")

            prompt = build_salt_prompt(batch)
            card_names = [c.get("name", "") for c in batch]

            try:
                query_model = QueryModel()
                response = query_model.query(self.models[ModelType.GENERATION], prompt)
                qa_pairs = list(
                    map(
                        lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                        json.loads(response),
                    )
                )

                qa_context = f"Salt cards in batch: {', '.join(card_names)}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=self.models,
                    qa_pairs=qa_pairs,
                    validation_pct=self.validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="salt_analysis",
                    source_data=card_names,
                    source_template=None,
                    metrics=self.metrics,
                )

                if is_valid and doc:
                    self.save_item(doc)

            except Exception as e:
                print(f"  ✗ Error for salt batch: {type(e).__name__}: {e}")
                continue

            batch_idx = batch_idx + 1
