import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import build_archetype_prompt, validate_and_loop_with_suggested_fix
from scryfall_mongodb import ScryfallMongo
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 5000
console = Console()

class GenerateArchetypes:
    def __init__(
        self,
        card_collection: pymongo.collection.Collection,  # type: ignore
        archetype_collection: pymongo.collection.Collection,  # type: ignore
        scryfall_client: ScryfallMongo,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = DEFAULT,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.card_collection = card_collection
        self.archetype_collection = archetype_collection
        self.scryfall_client = scryfall_client
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_archetypes(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} ARCHETYPE QUESTIONS ===")

        archetypes = [
            ("Aggro", "A strategy focused on dealing quick damage with low-cost creatures."),
            ("Control", "A strategy that counters threats and wins through card advantage."),
            ("Combo", "A strategy that assembles specific card combinations to win instantly."),
            ("Midrange", "A strategy that plays efficient threats and disrupts opponents."),
            ("Stax", "A control strategy using resource denial and lock pieces."),
            ("Voltron", "A strategy that equips one commander to deal lethal commander damage."),
            ("Tokens", "A strategy that swarms the board with creature tokens."),
            ("Reanimator", "A strategy that puts powerful creatures into play from the graveyard."),
            ("Storm", "A strategy that casts many spells in one turn to win with a storm payoff."),
            ("Pillow Fort", "A defensive strategy that prevents opponents from attacking you."),
        ]

        print(f"  → Processing {len(archetypes):,} archetypes...")

        i: int = 0
        for archetype, context in archetypes:
            if i >= self.target_count:
                break

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{self.target_count:,}...")

            prompt = build_archetype_prompt(archetype, context)

            try:
                query_model = QueryModel()
                response = query_model.query(self.models[ModelType.GENERATION], prompt)
                qa_pairs = list(
                    map(
                        lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                        json.loads(response),
                    )
                )

                qa_context = f"Archetype: {archetype}\nContext: {context}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=self.models,
                    qa_pairs=qa_pairs,
                    validation_pct=self.validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="archetype",
                    source_data=[archetype, context],
                    source_template=None,
                    metrics=self.metrics,
                )

                if is_valid and doc:
                    self.save_item(doc)

            except Exception as e:
                print(f"  ✗ Error for archetype '{archetype}': {type(e).__name__}: {e}")
                continue

            i = i + 1
