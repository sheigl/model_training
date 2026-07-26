"""Rule interactions generator — generates Q&A about how two MTG rules interact."""

from __future__ import annotations

import logging
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


def _extract_section(rule: dict[str, Any]) -> str:
    """Extract the top-level section number (prefix) from a rule dict.

    Examples:
        "601.1"  -> "601"
        "100.1a" -> "100"
        "100"    -> "100"
    """
    num = rule.get("ruleNumber", "")
    if "." in num:
        return num.split(".")[0]
    return num[:3]


class RuleInteractionsGenerator(BaseGenerator[tuple[dict, dict]]):
    """Generate Q&A about how two MTG rules interact.

    Category: rule_interactions
    Data batches: Tuple ``(rule1, rule2)`` of rule dicts from interacting
                  sections defined in ``INTERACTION_PAIRS``.
    Templates: plain_english, in_game_scenario, edge_case (from templates.yaml)
    """

    # fmt: off
    INTERACTION_PAIRS: list[tuple[str, str]] = [
        # -- Core gameplay interactions ----------------------------------
        ("601", "116"),  # Casting + Priority
        ("603", "116"),  # Triggered abilities + Priority
        ("603", "704"),  # Triggered abilities + SBAs
        ("608", "603"),  # Resolving spells + Triggered abilities
        ("702", "120"),  # Keywords + Damage
        ("702", "704"),  # Keywords + SBAs
        ("706", "603"),  # Copying + Triggered abilities
        ("601", "117"),  # Casting + Costs
        ("700", "116"),  # Additional rules + Priority
        ("800", "116"),  # Multiplayer + Priority
        ("903", "603"),  # Commander + Triggered abilities
        ("120", "704"),  # Damage + SBAs
        ("118", "117"),  # Paying costs + Costs
        ("604", "603"),  # Static abilities + Triggered abilities
        # -- Zone changes ------------------------------------------------
        ("400", "603"),  # Zone changes + Triggered abilities
        ("404", "603"),  # Exile zone + Triggered abilities
        ("406", "603"),  # Stack + Triggered abilities
        ("400", "704"),  # Zone changes + SBAs
        # -- Replacement effects -----------------------------------------
        ("614", "603"),  # Replacement effects + Triggered abilities
        ("614", "704"),  # Replacement effects + SBAs
        ("614", "120"),  # Replacement effects + Damage
        ("614", "116"),  # Replacement effects + Priority
        # -- Layers ------------------------------------------------------
        ("613", "604"),  # Layers + Static abilities
        ("613", "702"),  # Layers + Keywords
        # -- Combat ------------------------------------------------------
        ("506", "116"),  # Combat + Priority
        ("506", "603"),  # Combat + Triggered abilities
        ("506", "704"),  # Combat + SBAs
        ("510", "120"),  # Combat damage + Damage rules
        ("510", "704"),  # Combat damage + SBAs
        # -- Counters ----------------------------------------------------
        ("121", "704"),  # Counters + SBAs
        ("121", "603"),  # Counters + Triggered abilities
        # -- Mana --------------------------------------------------------
        ("106", "117"),  # Mana + Costs
        ("106", "601"),  # Mana + Casting
        # -- Commander specific ------------------------------------------
        ("903", "116"),  # Commander + Priority
        ("903", "704"),  # Commander + SBAs
        ("903", "614"),  # Commander + Replacement effects
        ("903", "400"),  # Commander + Zone changes
    ]
    # fmt: on

    def get_data_batches(self) -> list[tuple[dict, dict]]:
        """Fetch rules and build interaction pairs.

        Groups rules by their top-level section number, then for each
        interaction pair finds matching rules from each section.

        Returns:
            List of ``(rule1, rule2)`` tuples representing interacting rules.
        """
        ds = self.domain.get_data_source()
        raw = ds.get_rules(limit=500)

        # Group rules by section prefix
        rules_by_section: dict[str, list[dict]] = {}
        for rule in raw:
            text = rule.get("text", "")
            if len(text) <= 60:
                continue
            section = _extract_section(rule)
            if not section:
                continue
            rules_by_section.setdefault(section, []).append(rule)

        # Build pairs from interaction definitions
        batches: list[tuple[dict, dict]] = []
        seen: set[str] = set()

        for sec1, sec2 in self.INTERACTION_PAIRS:
            rules1 = rules_by_section.get(sec1, [])
            rules2 = rules_by_section.get(sec2, [])
            if not rules1 or not rules2:
                continue

            rule1 = rules1[0]
            rule2 = rules2[0]
            pair_key = f"{rule1['ruleNumber']}+{rule2['ruleNumber']}"
            if pair_key in seen:
                continue
            seen.add(pair_key)

            batches.append((rule1, rule2))

        logger.info(
            "Built %d rule interaction pairs (from %d raw rules, "
            "%d interaction types)",
            len(batches),
            len(raw),
            len(self.INTERACTION_PAIRS),
        )
        return batches

    def build_prompt(
        self, template: TemplateConfig, data_batch: tuple[dict, dict]
    ) -> str:
        """Build the LLM prompt explaining how two rules interact.

        Args:
            template: TemplateConfig with task_instruction. Supports
                      ``{rule1_number}``, ``{rule1_text}``,
                      ``{rule2_number}``, ``{rule2_text}`` placeholders.
            data_batch: Tuple ``(rule1, rule2)`` of rule dicts.

        Returns:
            Full prompt string with notation legend, rules, and task.
        """
        rule1, rule2 = data_batch
        rule1_number = rule1.get("ruleNumber", "")
        rule1_text = rule1.get("text", "")
        rule2_number = rule2.get("ruleNumber", "")
        rule2_text = rule2.get("text", "")

        notation = self.domain.notation_legend

        task_instruction = template.task_instruction.format(
            rule1_number=rule1_number,
            rule1_text=rule1_text,
            rule2_number=rule2_number,
            rule2_text=rule2_text,
        )

        return (
            f"{notation}\n\n"
            f"<rules>\n"
            f"AUTHORITATIVE RULES — treat these as ground truth:\n\n"
            f"Rule {rule1_number}: {rule1_text}\n\n"
            f"Rule {rule2_number}: {rule2_text}\n"
            f"</rules>\n\n"
            f"<task>\n"
            f"{task_instruction}\n\n"
            f"REQUIREMENTS:\n"
            f"1. At least one question MUST come from the perspective of a "
            f"player mid-game who doesn't know the rules terminology.\n"
            f"2. At least one question MUST address a common misconception "
            f"where one rule might be applied without considering the other.\n"
            f"3. Questions must be natural-sounding. Do not reference rule "
            f"numbers in questions.\n"
            f"4. Answers must explain how both rules interact, quoting or "
            f"paraphrasing relevant text from each.\n"
            f"5. Every answer MUST state the concrete final game outcome.\n"
            f"6. Answers must explain which rule applies first or takes "
            f"precedence.\n"
            f"7. Do NOT reference rule numbers in answers — explain "
            f"mechanics conversationally.\n"
            f"8. Answers must be plain text only (no markdown formatting).\n"
            f"9. The answer field MUST be a single string (not an array).\n\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"</task>"
        )

    def get_source_category(self) -> str:
        return "rule_interactions"

    def build_context(self, data_batch: tuple[dict, dict]) -> str | None:
        """Build metadata context for the generated Q&A."""
        rule1, rule2 = data_batch
        return (
            f"Category: {self.get_source_category()}\n"
            f"Rule 1: {rule1.get('ruleNumber', '')}\n"
            f"Rule 2: {rule2.get('ruleNumber', '')}\n"
            f"Sections: {_extract_section(rule1)} + {_extract_section(rule2)}"
        )
