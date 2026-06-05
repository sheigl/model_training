import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_synergy_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()


class GenerateSynergyQuestions:
    def __init__(
        self,
        cards_collection: pymongo.collection.Collection,  # type: ignore
        combos_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = 3000,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.cards_collection = cards_collection
        self.combos_collection = combos_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_synergy_questions(self) -> None:
        """Generate synergy discovery questions - returns MongoDB documents"""

        cards_collection = self.cards_collection
        combos_collection = self.combos_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} SYNERGY QUESTIONS ===")

        all_combos: list[dict] = []
        popular_cards: list[tuple[str, int]] = []

        with console.status("[bold green]Extracting synergy data...") as status:
            all_combos = list(combos_collection.find({'status': 'OK'}).limit(5000))

            card_combo_count: dict[str, int] = {}
            for combo in all_combos:
                cards = combo.get('uses', [])
                for card_info in cards:
                    card_name = card_info.get('card', {}).get('name', '')
                    if card_name:
                        card_combo_count[card_name] = card_combo_count.get(card_name, 0) + 1

            popular_cards = sorted(card_combo_count.items(), key=lambda x: x[1], reverse=True)[:200]

        print(f"  → Processing {len(popular_cards)} popular combo cards...")

        num_docs = 0

        for card_name, combo_count in popular_cards:
            if num_docs >= target_count:
                break

            if (num_docs + 1) % 200 == 0:
                print(f"    Generated {num_docs:,}/{target_count:,}...")

            card = cards_collection.find_one({'name': card_name})
            if not card:
                continue

            card_combos = [c for c in all_combos if card_name in str(c.get('uses', []))][:3]

            synergy_cards: set[str] = set()
            for combo in card_combos:
                cards = combo.get('uses', [])
                for c in cards:
                    other_name = c.get('card', {}).get('name', '')
                    if other_name and other_name != card_name:
                        synergy_cards.add(other_name)

            if not synergy_cards:
                continue

            prompt = build_synergy_prompt(card, synergy_cards)

            try:
                query_model = QueryModel()
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"""
Card: {card_name}
Card text: {card.get('text', '')}
Synergy cards: {', '.join(list(synergy_cards)[:10])}
"""

                source_data: list[Any] = [card_name] + list(synergy_cards)[:5]

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=qa_pairs,
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="synergy",
                    source_data=source_data,
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    save_item(doc)
                    num_docs += 1

            except Exception as e:
                print(f"  ✗ Error generating synergy for {card_name}: {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {num_docs:,} synergy questions")
