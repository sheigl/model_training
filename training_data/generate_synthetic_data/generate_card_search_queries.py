import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_card_detail, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Card, Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print
import random

console = Console()


class GenerateCardSearchQueries:
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

    def generate_card_search_queries(self) -> None:
        """Generate card search queries - returns MongoDB documents"""

        cards_collection = self.cards_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} CARD SEARCH QUERIES ===")

        search_patterns = [
            {'name': 'Green ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
            {'name': 'Zombie tokens', 'query': {'text': {'$regex': 'zombie.*token', '$options': 'i'}}},
            {'name': 'Treasure tokens', 'query': {'text': {'$regex': 'treasure', '$options': 'i'}}},
            {'name': 'White removal', 'query': {'text': {'$regex': 'exile|destroy', '$options': 'i'}, 'colors': ['W']}},
            {'name': 'Blue card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'colors': ['U']}},
            {'name': 'ETB effects', 'query': {'text': {'$regex': 'enters the battlefield', '$options': 'i'}}},
            {'name': 'Black removal', 'query': {'text': {'$regex': 'destroy.*creature', '$options': 'i'}, 'colors': ['B']}},
            {'name': 'Red burn', 'query': {'text': {'$regex': 'deals.*damage', '$options': 'i'}, 'colors': ['R']}},
        ]

        num_docs = 0

        for pattern in search_patterns:
            if num_docs >= target_count:
                break

            print(f"  → {pattern['name']}")

            matching_cards: list[Card] = []
            for card in cards_collection.find(pattern['query'], {'name': 1, 'text': 1, 'manaCost': 1, 'type': 1, 'subtypes': 1, 'supertypes': 1, 'colorIdentity': 1}).limit(15):
                if not card or 'name' not in card or 'type' not in card or 'manaCost' not in card or 'text' not in card:
                    continue
                mapped_card = Card(
                    name=card.get('name', 'Unknown'),
                    type=card.get('type', 'Unknown'),
                    mana_cost=card.get('manaCost', 'Unknown'),
                    text=card.get('text', ''),
                    subtypes=json.loads(card.get('subtypes', '[]')) if card.get('subtypes') else [],
                    supertypes=json.loads(card.get('supertypes', '[]')) if card.get('supertypes') else [],
                    color_identity=json.loads(card.get('colorIdentity', '[]')) if card.get('colorIdentity') else [],
                    zone_locations=[]
                )
                matching_cards.append(mapped_card)

            if not matching_cards:
                continue

            card_names = [c.name for c in matching_cards]

            prompt = self.__build_card_search_prompt(pattern, matching_cards[:10])

            try:
                query_model = QueryModel()
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"""
Search pattern: {pattern['name']}
Matching cards:
{NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), matching_cards[:10]))}
"""

                source_data: list[Any] = card_names[:10]

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=qa_pairs,
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="card_search",
                    source_data=source_data,
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    save_item(doc)
                    num_docs += 1

            except Exception as e:
                print(f"  ✗ Error generating for {pattern['name']}: {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {num_docs:,} card search queries")

    def __build_card_search_prompt(self, pattern: dict, cards: list[Card]) -> str:
        """Generate card search prompt with MTG notation guide."""

        prompt = f"""{MTG_NOTATION_LEGEND}

    Generate 5 Q&A pairs for: {pattern['name']}

    Example cards:
    {NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards))}

    Output JSON with natural questions and helpful answers listing 3-5 best cards.
    Answers should explain what the cards do and why they're good for this purpose.
    Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
        return prompt
