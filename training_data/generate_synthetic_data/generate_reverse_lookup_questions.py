import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_reverse_lookup_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()


class GenerateReverseLookupQuestions:
    def __init__(
        self,
        cards_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 3000,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.cards_collection = cards_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_reverse_lookup_questions(self) -> None:
        """Generate reverse lookup questions (feature → card) - returns MongoDB documents"""

        cards_collection = self.cards_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} REVERSE LOOKUP QUESTIONS ===")

        feature_patterns = [
            {'feature': 'play lands from graveyard', 'regex': 'play.*land.*graveyard|land.*graveyard.*battlefield'},
            {'feature': 'tutor for artifacts', 'regex': 'search.*library.*artifact'},
            {'feature': 'tutor for creatures', 'regex': 'search.*library.*creature'},
            {'feature': 'destroy all creatures', 'regex': 'destroy all creature|destroy all nonland'},
            {'feature': 'destroy all artifacts', 'regex': 'destroy all artifact'},
            {'feature': 'destroy all enchantments', 'regex': 'destroy all enchantment|destroy target enchantment'},
            {'feature': 'exile from graveyard', 'regex': 'exile.*graveyard'},
            {'feature': 'return creatures from graveyard', 'regex': 'return.*creature.*graveyard'},
            {'feature': 'draw cards when creatures die', 'regex': 'draw.*card.*creature.*dies|creature dies.*draw'},
            {'feature': 'create treasure tokens', 'regex': 'create.*treasure|treasure token'},
            {'feature': 'create zombie tokens', 'regex': 'create.*zombie|zombie token'},
            {'feature': 'sacrifice creatures for value', 'regex': 'sacrifice.*creature.*draw|sacrifice.*creature.*mana'},
            {'feature': 'give creatures haste', 'regex': 'creatures.*have haste|creatures you control have haste'},
            {'feature': 'give creatures flying', 'regex': 'creatures.*have flying|creatures you control have flying'},
            {'feature': 'untap all creatures', 'regex': 'untap all creature|untap target creature'},
            {'feature': 'copy spells', 'regex': 'copy.*instant|copy.*sorcery|copy target spell'},
            {'feature': 'double mana', 'regex': 'double.*mana|add.*equal to'},
            {'feature': 'prevent combat damage', 'regex': 'prevent.*combat damage|creatures can.?t attack'},
        ]

        num_docs = 0

        for pattern in feature_patterns:
            if num_docs >= target_count:
                break

            print(f"  → {pattern['feature']}")

            matching_cards = list(cards_collection.find(
                {'text': {'$regex': pattern['regex'], '$options': 'i'}},
                {'name': 1, 'text': 1, 'type': 1}
            ).limit(15))

            if not matching_cards:
                continue

            card_names = [c.get('name', '') for c in matching_cards]
            card_details = "\n".join([f"  - {c.get('name', '')}: {c.get('text', '')[:80]}..." for c in matching_cards[:5]])

            prompt = build_reverse_lookup_prompt(pattern, card_details)

            try:
                query_model = QueryModel()
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"""
Feature: {pattern['feature']}
Matching cards:
{card_details}
"""

                source_data: list[Any] = card_names[:5]

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=qa_pairs,
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="reverse_lookup",
                    source_data=source_data,
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    save_item(doc)
                    num_docs += 1

            except Exception as e:
                print(f"  ✗ Error generating reverse lookup for '{pattern['feature']}': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {num_docs:,} reverse lookup questions")
