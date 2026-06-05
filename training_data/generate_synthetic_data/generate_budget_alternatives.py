import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_budget_alternative_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()


class GenerateBudgetAlternatives:
    def __init__(
        self,
        cards_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 2000,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.cards_collection = cards_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_budget_alternatives(self) -> None:
        """Generate budget alternative questions - returns MongoDB documents"""

        cards_collection = self.cards_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} BUDGET ALTERNATIVE QUESTIONS ===")

        expensive_patterns = [
            {'effect': 'ramp', 'query': {'text': {'$regex': 'search.*land|add.*mana', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
            {'effect': 'removal', 'query': {'text': {'$regex': 'destroy|exile', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
            {'effect': 'card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
            {'effect': 'tutors', 'query': {'text': {'$regex': 'search.*library', '$options': 'i'}, 'rarity': {'$in': ['mythic', 'rare']}}},
        ]

        num_docs = 0

        for pattern in expensive_patterns:
            if num_docs >= target_count:
                break

            print(f"  → {pattern['effect']}")

            expensive_cards = list(cards_collection.find(
                pattern['query'],
                {'name': 1, 'text': 1, 'rarity': 1}
            ).limit(10))

            budget_query = pattern['query'].copy()
            budget_query['rarity'] = {'$in': ['uncommon', 'common']}

            budget_cards = list(cards_collection.find(
                budget_query,
                {'name': 1, 'text': 1, 'rarity': 1}
            ).limit(15))

            if not expensive_cards or not budget_cards:
                continue

            for exp_card in expensive_cards[:5]:
                if num_docs >= target_count:
                    break

                exp_name = exp_card.get('name', '')
                if not exp_name:
                    continue

                budget_names = [c.get('name', '') for c in budget_cards[:5]]
                budget_details = "\n".join([f"  - {c.get('name', '')} ({c.get('rarity', '')})" for c in budget_cards[:5]])

                prompt = build_budget_alternative_prompt(exp_card, budget_details)

                try:
                    query_model = QueryModel()
                    response = query_model.query(models[ModelType.GENERATION], prompt)
                    response = response.replace("```json", "").replace("```", "").strip()
                    qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                    qa_context = f"""
Expensive card: {exp_name} (rare/mythic)
Text: {exp_card.get('text', '')}
Budget alternatives:
{budget_details}
"""

                    source_data: list[Any] = [exp_name] + budget_names

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=qa_pairs,
                        validation_pct=validation_pct,
                        enable_extra_validation=False,
                        build_context=lambda: qa_context,
                        source_category="budget_alternative",
                        source_data=source_data,
                        source_template=None,
                        metrics=self.metrics
                    )

                    if is_valid and doc:
                        save_item(doc)
                        num_docs += 1

                except Exception as e:
                    print(f"  ✗ Error generating budget alt for {exp_name}: {type(e).__name__}: {e}")
                    continue

        print(f"  ✓ Generated {num_docs:,} budget alternative questions")
