from rich.console import Console
from query_model import QueryModel
import json
from common import build_rules_scenario_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

console = Console()

class GenerateRulesScenarios:
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

    def generate_rules_scenarios(self) -> None:
        """Generate scenario-based rules Q&A - returns MongoDB documents via save_item."""
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count

        print(f"\n=== GENERATING {target_count:,} RULES SCENARIO QUESTIONS ===")

        scenarios = [
            (
                "spell resolution and the stack",
                "Last in first out stack resolution, responding to spells, fizzling spells, counterspells"
            ),
            (
                "combat damage and blocking",
                "Assigning combat damage, trample, first strike, double strike, deathtouch in combat, lifelink in combat"
            ),
            (
                "triggered abilities and timing",
                "When triggered abilities go on the stack, controlling the order of your own triggers, missed triggers"
            ),
            (
                "state-based actions",
                "Creatures dying from lethal damage or 0 toughness, legend rule, planeswalker uniqueness rule, poison counters"
            ),
            (
                "activated abilities and costs",
                "Paying costs for activated abilities, tapping as a cost, sacrifice as a cost, mana abilities"
            ),
            (
                "replacement effects and prevention effects",
                "How replacement effects modify events, prevention effects, damage prevention, redirection"
            ),
            (
                "keyword abilities interactions",
                "How keywords interact: hexproof vs targeting, shroud vs targeting, indestructible vs destroy vs exile, regenerate"
            ),
            (
                "Commander-specific rules",
                "Commander tax, commander damage, moving to command zone vs graveyard, color identity in deck building"
            ),
            (
                "planeswalker rules",
                "Activating planeswalker abilities, attacking planeswalkers, the planeswalker uniqueness rule, loyalty counters"
            ),
            (
                "token and copy rules",
                "Creating tokens, copying spells, copying permanents, token characteristics, copy effects on the stack"
            ),
            (
                "priority and passing priority",
                "When players receive priority, how to sequence actions, when you can and cannot respond"
            ),
            (
                "enters the battlefield and leaves the battlefield triggers",
                "ETB triggers, LTB triggers, flicker effects, blink, phasing, bouncing permanents"
            ),
            (
                "targeting and illegal targets",
                "Choosing targets on announcement, targets becoming illegal before resolution, fizzling"
            ),
            (
                "mana and casting",
                "Mana pool, emptying the mana pool, split second, flash, timing restrictions for casting spells"
            ),
            (
                "graveyard and exile interactions",
                "Cards going to graveyard, replacement effects for dying, exile vs graveyard, returning from exile"
            ),
        ]

        query_model = QueryModel()
        total_generated = 0

        for scenario, rules in scenarios:
            if total_generated >= target_count:
                break

            print(f"  → {scenario}")
            prompt = build_rules_scenario_prompt(scenario, rules)

            try:
                response = query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))

                qa_context = f"Rules topic: {scenario}\nRelevant rules: {rules}"

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
                        source_category="rules_scenario",
                        source_data=["comprehensive_rules"],
                        source_template=None,
                        metrics=self.metrics
                    )

                    if is_valid and doc:
                        doc.rules_topic = scenario  # type: ignore[attr-defined]
                        save_item(doc)
                        total_generated += 1

            except Exception as e:
                print(f"  ✗ Error for scenario '{scenario}': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {total_generated:,} rules scenario questions")
