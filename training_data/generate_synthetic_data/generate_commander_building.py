from rich.console import Console
from query_model import QueryModel
import json
from common import build_commander_building_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateCommanderBuilding:
    def __init__(
        self,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=3000,
        metrics: ValidationMetrics | None = None) -> None:

        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_commander_building(self) -> None:
        """Generate Commander-specific deckbuilding Q&A - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} COMMANDER BUILDING QUESTIONS ===")

        archetypes = [
            (
                "sacrifice/aristocrats",
                "Decks that sacrifice creatures for value, using Blood Artist-style effects, sac outlets, and token generators. Key challenge: balancing fodder, payoffs, and sac outlets."
            ),
            (
                "spellslinger/magecraft",
                "Decks that cast lots of instants and sorceries, using magecraft triggers, prowess, and spell-based win conditions. Key challenge: protecting your win condition while staying low to the ground."
            ),
            (
                "token swarm",
                "Decks that generate many creature tokens and win through wide attacks or combo. Key challenge: having enough anthems and ways to win through chump blockers."
            ),
            (
                "reanimator",
                "Decks that put big creatures in the graveyard and reanimate them cheaply. Key challenge: filling the graveyard, protecting the reanimation target, winning with the reanimated creature."
            ),
            (
                "combo",
                "Decks that assemble a specific combination of cards to win instantly or lock opponents out. Key challenge: finding the combo pieces, protecting the combo, having backup win conditions."
            ),
            (
                "control",
                "Decks that answer every threat and win through superior card advantage in the late game. Key challenge: staying relevant in multiplayer, having a win condition that can close through disruption."
            ),
            (
                "voltron",
                "Decks that buff one creature (usually the commander) with equipment and auras to win through commander damage. Key challenge: protecting your commander, rebuilding after removal, winning through 21 combat damage."
            ),
            (
                "stax/prison",
                "Decks that use symmetrical or asymmetrical effects to slow opponents while you advance your own game plan. Key challenge: calibrating the lock pieces so you can still win, not making the game unfun."
            ),
            (
                "landfall/lands matter",
                "Decks that trigger off lands entering the battlefield, using extra land effects and landfall payoffs. Key challenge: getting enough lands into play per turn, balancing consistency with power."
            ),
            (
                "graveyard value",
                "Decks that use the graveyard as a resource without necessarily being reanimator — flashback, delve, threshold, cycling. Key challenge: filling the graveyard efficiently, playing around graveyard hate."
            ),
            (
                "turbo draw/card advantage",
                "Decks built around drawing as many cards as possible to find combo pieces or assemble overwhelming card advantage. Key challenge: using the cards drawn effectively, not decking yourself."
            ),
            (
                "midrange goodstuff",
                "Decks that play powerful cards at every part of the curve without a focused synergy strategy. Key challenge: distinguishing this from a tuned synergy deck, knowing when to choose goodstuff over theme."
            ),
        ]

        query_model = QueryModel()
        total_generated = 0

        for archetype, context in archetypes:
            if total_generated >= target_count:
                break

            print(f"  → {archetype}")
            prompt = build_commander_building_prompt(archetype, context)

            try:
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"Archetype: {archetype}\nContext: {context}"

                for qa in qa_pairs:
                    if total_generated >= target_count:
                        break

                    if len(qa.answer) <= 100:
                        print(f"    ✗ REJECTED (too short): {qa.question[:80]}")
                        continue

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=[qa],
                        validation_pct=validation_pct,
                        enable_extra_validation=False,
                        build_context=lambda: qa_context,
                        source_category="commander_building",
                        source_data=["commander_format"],
                        source_template=None,
                        metrics=self.metrics
                    )

                    if is_valid and doc:
                        doc.archetype = archetype  # type: ignore[attr-defined]
                        save_item(doc)
                        total_generated += 1

            except Exception as e:
                print(f"  ✗ Error for archetype '{archetype}': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {total_generated:,} Commander building questions")
