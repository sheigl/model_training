import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_color_identity_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print
import random

console = Console()


class GenerateColorIdentityQuestions:
    def __init__(
        self,
        cards_collection: pymongo.collection.Collection,  # type: ignore
        commanders_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 2000,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.cards_collection = cards_collection
        self.commanders_collection = commanders_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_color_identity_questions(self) -> None:
        """Generate color identity questions - returns MongoDB documents"""

        cards_collection = self.cards_collection
        commanders_collection = self.commanders_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} COLOR IDENTITY QUESTIONS ===")

        cards_sample: list[dict] = []
        commander_identities: list[tuple[str, list[str]]] = []

        with console.status("[bold green]Extracting color identity data...") as status:
            cards_sample = list(map(lambda c: {
                'name': c.get('name'),
                'colors': json.loads(c.get('colors', '[]')) if c.get('colors') else [],
                'colorIdentity': json.loads(c.get('colorIdentity', '[]')) if c.get('colorIdentity') else [],
                'manaCost': c.get('manaCost')
            }, cards_collection.find(
                {'colors': {'$exists': True}},
                {'name': 1, 'colors': 1, 'colorIdentity': 1, 'manaCost': 1}
            ).limit(500)))

            commander_identities = [('mono-red deck', ['R'])]

            for card in commanders_collection.find(
                {'color_identity': {'$exists': True}},
                {'name': 1, 'color_identity': 1}
            ).limit(100):
                commander_identities.append((card.get('name', ''), card.get('color_identity', [])))

        print(f"  → Processing {len(cards_sample)} cards...")

        num_docs = 0

        for card in random.sample(cards_sample, min(200, len(cards_sample))):
            if num_docs >= target_count:
                break

            card_name = card.get('name', '')
            card_colors = card.get('colorIdentity', card.get('colors', []))

            if not card_name:
                continue

            commander_name, commander_colors = random.choice(commander_identities)

            card_color_set = set(card_colors) if card_colors else set()
            commander_color_set = set(commander_colors)
            is_legal = card_color_set.issubset(commander_color_set)

            prompt = build_color_identity_prompt(card, commander_name, commander_colors, is_legal)

            try:
                query_model = QueryModel()
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"""
Card: {card_name}, colors: {card_colors}
Commander: {commander_name}, identity: {commander_colors}
Legal: {is_legal}
"""

                source_data: list[Any] = [card_name, commander_name, f"colors: {card_colors}", f"commander_colors: {commander_colors}", f"legal: {is_legal}"]

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=qa_pairs,
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="color_identity",
                    source_data=source_data,
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    save_item(doc)
                    num_docs += 1

            except Exception as e:
                print(f"  ✗ Error generating color identity for {card_name}/{commander_name}: {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {num_docs:,} color identity questions")
