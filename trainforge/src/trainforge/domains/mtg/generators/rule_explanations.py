"""Rule explanations generator — explains individual MTG rules in plain language."""

from __future__ import annotations

import logging
import re
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


_RULE_NUM_RE = re.compile(r"(\d+)")


def _extract_section(rule: dict[str, Any]) -> int:
    """Extract the top-level section number from a rule dict."""
    rule_num = rule.get("ruleNumber", "")
    m = _RULE_NUM_RE.match(rule_num)
    return int(m.group(1)) if m else 0


class RuleExplanationsGenerator(BaseGenerator[dict[str, Any]]):
    """Generate Q&A explaining individual MTG rules in accessible language.

    Category: rule_explanations
    Data batches: Rule dicts (skipping intro sections 000-005 and 900+),
                  text > 50 chars
    Templates: plain_english, in_game_scenario, edge_case (from templates.yaml)
    """

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch rules excluding intro sections (000-005) and appendices (900+).

        Only returns rules with sufficient text content (> 50 chars).
        """
        ds = self.domain.get_data_source()
        raw = ds.get_rules(limit=500)

        batches = [
            r
            for r in raw
            if self._include_rule(r) and len(r.get("text", "")) > 50
        ]
        logger.info(
            "Loaded %d rules (from %d raw, excluded 000-005 and 900s, text > 50 chars)",
            len(batches),
            len(raw),
        )
        return batches

    def build_prompt(self, template: TemplateConfig, data_batch: dict[str, Any]) -> str:
        """Build the LLM prompt explaining a rule.

        Formats the template's ``task_instruction`` with ``{rule_number}``,
        ``{rule_text}``, and ``{section}`` so templates can reference the
        rule data directly. Falls back gracefully if templates don't contain
        placeholders.
        """
        rule_number = data_batch.get("ruleNumber", "")
        rule_text = data_batch.get("text", "")
        section = data_batch.get("section", "")

        task_instruction = template.task_instruction.format(
            rule_number=rule_number,
            rule_text=rule_text,
            section=section,
        )
        notation = self.domain.notation_legend
        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def build_context(self, data_batch: dict[str, Any]) -> str | None:
        """Build metadata context with rule number, section, and text."""
        return (
            f"Category: {self.get_source_category()}\n"
            f"Rule: {data_batch.get('ruleNumber', '')}\n"
            f"Section: {data_batch.get('section', '')}\n"
            f"Text: {data_batch.get('text', '')}"
        )

    def get_source_category(self) -> str:
        return "rule_explanations"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _include_rule(rule: dict[str, Any]) -> bool:
        """Check if a rule should be included: skip sections 000-005 and 900+."""
        section = _extract_section(rule)
        if section == 0:
            return False  # Unparseable rule number
        if section <= 5:
            return False  # Intro sections
        if section >= 900:
            return False  # Glossary / appendices
        return True
