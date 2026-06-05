import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_card_detail, build_card_comparision_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Card, Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()


class GenerateComparisonQuestions:
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

    def generate_comparison_questions(self) -> None:
        """Generate card comparison questions - returns MongoDB documents"""

        cards_collection = self.cards_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} COMPARISON QUESTIONS ===")

        comparison_patterns = [
            {'effect': 'fast mana', 'query': {'text': {'$regex': 'add.*mana|add {{C}}', '$options': 'i'}, 'type': {'$regex': 'Artifact'}}},
            {'effect': 'ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
            {'effect': 'removal', 'query': {'text': {'$regex': 'destroy|exile', '$options': 'i'}}},
            {'effect': 'card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}}},
            {'effect': 'counterspells', 'query': {'text': {'$regex': 'counter target', '$options': 'i'}, 'type': {'$regex': 'Instant'}}},
            {'effect': 'board wipes', 'query': {'text': {'$regex': 'destroy all|exile all', '$options': 'i'}}},
            {'effect': 'tutors', 'query': {'text': {'$regex': 'search.*library', '$options': 'i'}}},
            {'effect': 'reanimation', 'query': {'text': {'$regex': 'return.*creature.*graveyard', '$options': 'i'}}},
        ]

        num_docs = 0

        with console.status("[bold green]Extracting comparison data...") as status:
            for pattern in comparison_patterns:
                if num_docs >= target_count:
                    break

                print(f"  → {pattern['effect']}")

                similar_cards_raw = list(cards_collection.find(
                    pattern['query'],
                    {'name': 1, 'text': 1, 'manaCost': 1, 'type': 1, 'subtypes': 1, 'supertypes': 1, 'colorIdentity': 1}
                ).limit(20))

                similar_cards: list[Card] = []
                for c in similar_cards_raw:
                    if not c or 'name' not in c or 'type' not in c or 'manaCost' not in c or 'text' not in c:
                        continue
                    mapped = Card(
                        name=c.get('name', 'Unknown'),
                        type=c.get('type', 'Unknown'),
                        mana_cost=c.get('manaCost', 'Unknown'),
                        text=c.get('text', ''),
                        subtypes=json.loads(c.get('subtypes', '[]')) if c.get('subtypes') else [],
                        supertypes=json.loads(c.get('supertypes', '[]')) if c.get('supertypes') else [],
                        color_identity=json.loads(c.get('colorIdentity', '[]')) if c.get('colorIdentity') else [],
                        zone_locations=[]
                    )
                    similar_cards.append(mapped)

                if len(similar_cards) < 2:
                    continue

                for i in range(0, len(similar_cards) - 1, 2):
                    if num_docs >= target_count:
                        break

                    card1 = similar_cards[i]
                    card2 = similar_cards[i + 1]

                    card1_name = card1.name
                    card2_name = card2.name

                    prompt = build_card_comparision_prompt(card1, card2)

                    try:
                        query_model = QueryModel()
                        response = query_model.query(models[ModelType.GENERATION], prompt)
                        response = response.replace("```json", "").replace("```", "").strip()
                        qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                        qa_context = f"""
Compare {card1_name} and {card2_name} for {pattern['effect']}.
{build_card_detail(1, card1)}
{build_card_detail(2, card2)}
"""

                        source_data: list[Any] = [card1_name, card2_name]

                        is_valid, doc = validate_and_loop_with_suggested_fix(
                            query_model=query_model,
                            models=models,
                            qa_pairs=qa_pairs,
                            validation_pct=validation_pct,
                            enable_extra_validation=False,
                            build_context=lambda: qa_context,
                            source_category="comparison",
                            source_data=source_data,
                            source_template=None,
                            metrics=self.metrics
                        )

                        if is_valid and doc:
                            save_item(doc)
                            num_docs += 1

                    except Exception as e:
                        print(f"  ✗ Error generating comparison for {card1_name} vs {card2_name}: {type(e).__name__}: {e}")
                        continue

        print(f"  ✓ Generated {num_docs:,} comparison questions")
