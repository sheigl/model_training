import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import build_staple_analysis_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 2000
console = Console()

class GenerateStapleAnalysis:
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

    def generate_staple_analysis(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} STAPLE ANALYSIS QUESTIONS ===")

        cards: list[dict] = []
        with console.status("[bold green]Extracting game-changer cards...") as status:
            all_changers = list(
                self.game_changers_collection.find(
                    {"game_changer": True, "oracle_text": {"$exists": True, "$ne": ""}},
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
                ).sort("num_decks", -1)
            )
            cards = all_changers[: self.target_count + int(self.target_count * 0.25)]
            status.update(f"[bold green]Extracted {len(cards):,} game-changer cards")

        print(f"  → Processing {len(cards):,} cards...")

        i: int = 0
        for card in cards:
            if i >= self.target_count:
                break

            name = card.get("name", "")
            if not name:
                continue

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{self.target_count:,}...")

            prompt = build_staple_analysis_prompt(card)

            try:
                query_model = QueryModel()
                response = query_model.query(self.models[ModelType.GENERATION], prompt)
                qa_pairs = list(
                    map(
                        lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                        json.loads(response),
                    )
                )

                qa_context = f"Card: {name}\nDecks played in: {card.get('num_decks', 0):,}\nSalt score: {card.get('salt', 0):.2f}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=self.models,
                    qa_pairs=qa_pairs,
                    validation_pct=self.validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="staple_analysis",
                    source_data=[name],
                    source_template=None,
                    metrics=self.metrics,
                )

                if is_valid and doc:
                    self.save_item(doc)

            except Exception as e:
                print(f"  ✗ Error for card '{name}': {type(e).__name__}: {e}")
                continue

            i = i + 1
