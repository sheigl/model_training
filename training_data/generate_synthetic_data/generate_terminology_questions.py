from rich.console import Console
from query_model import QueryModel
from common import validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateTerminologyQuestions:
    def __init__(
        self,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=1000,
        metrics: ValidationMetrics | None = None) -> None:

        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_terminology_questions(self) -> None:
        """Generate MTG terminology/slang questions - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} TERMINOLOGY QUESTIONS ===")

        # Curated MTG terminology
        terminology = [
            ("CEDH", "CEDH stands for Competitive EDH (Elder Dragon Highlander/Commander). It's Commander played at the highest power level with optimized decks, fast combos, and competitive mindset."),
            ("pillow fort", "A 'pillow fort' is a defensive strategy that uses enchantments and effects to discourage opponents from attacking you, like Ghostly Prison, Propaganda, and Sphere of Safety."),
            ("MLD", "MLD stands for Mass Land Destruction - effects that destroy all or most lands, like Armageddon. It's generally frowned upon in casual Commander."),
            ("staple", "A 'staple' is a card that's commonly played across many decks because it's powerful and generically useful, like Sol Ring, Arcane Signet, or Swords to Plowshares."),
            ("salt", "In Commander, 'salt' refers to cards or strategies that make opponents unhappy or frustrated, often because they're seen as unfun or oppressive."),
            ("aristocrats", "Aristocrats is a sacrifice-based strategy that generates value from creatures dying, using cards like Blood Artist, Zulaport Cutthroat, and sacrifice outlets."),
            ("voltron", "Voltron is a strategy focused on making one creature (usually your commander) extremely large and powerful with equipment, auras, and buffs to win through commander damage."),
            ("group hug", "Group hug is a political strategy that gives benefits to all players (card draw, mana, etc.) to make friends and avoid being targeted, sometimes hiding a secret win condition."),
            ("stax", "Stax (from 'The Stacks') is a prison strategy that uses tax effects and restrictions to slow down opponents while you build towards a win."),
            ("GY", "GY is shorthand for 'graveyard' - the zone where cards go when they die, are discarded, or milled."),
            ("ETB", "ETB stands for 'enters the battlefield' - refers to triggered abilities that happen when a permanent comes into play."),
            ("LTB", "LTB stands for 'leaves the battlefield' - refers to triggered abilities when a permanent is removed from play."),
            ("ramp", "Ramp refers to cards and strategies that accelerate your mana production, letting you cast bigger spells earlier than usual."),
            ("tutor", "A tutor is any card that lets you search your library for specific cards, named after the card Demonic Tutor."),
            ("wheel", "A wheel effect forces all players to discard their hand and draw a new hand of seven cards, named after Wheel of Fortune."),
            ("pod", "Pod refers to sacrifice-and-search effects like Birthing Pod, letting you sacrifice a creature to find one that costs more."),
            ("blink", "Blink effects temporarily exile a creature and return it immediately, retriggering ETB abilities. Named after the card Momentary Blink."),
            ("flicker", "Flicker is synonymous with blink - temporarily exiling and returning permanents to retrigger ETB effects."),
            ("bounce", "Bounce means returning permanents from the battlefield to hand, like with Cyclonic Rift or Unsummon."),
            ("hatedraft", "Hatedraft means drafting a card not for your deck, but to prevent opponents from getting it. Not relevant in Commander but part of MTG terminology."),
        ]

        print(f"  → Using {len(terminology)} terms...")
        query_model = QueryModel()
        total_generated = 0

        for term, definition in terminology:
            if total_generated >= target_count:
                break

            # Create multiple question phrasings
            questions = [
                f"What is {term}?",
                f"What does {term} mean?",
                f"What's {term} in Magic?",
                f"Explain {term}",
                f"What does '{term}' refer to?",
            ]

            for question in questions[:3]:  # Use 3 variations per term
                if total_generated >= target_count:
                    break

                qa_pairs = [QuestionAnswer(question, definition)]
                qa_context = f"MTG Term: {term}\nDefinition: {definition}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=models,
                    qa_pairs=qa_pairs,
                    validation_pct=validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="terminology",
                    source_data=[term],
                    source_template=None,
                    metrics=self.metrics
                )

                if is_valid and doc:
                    doc.term = term  # type: ignore[attr-defined]
                    save_item(doc)
                    total_generated += 1

        print(f"  ✓ Generated {total_generated:,} terminology questions")
