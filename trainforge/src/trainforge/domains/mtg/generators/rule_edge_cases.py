"""Rule edge-cases generator — unusual or non-obvious rule interactions."""

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


class RuleEdgeCasesGenerator(BaseGenerator[dict[str, Any]]):
    """Generate Q&A exploring edge cases in MTG rules.

    Category: rule_edge_cases
    Data batches: Rule dicts from complex sections (701-708),
                  text >= 80 chars
    Templates: unusual_interaction (from templates.yaml)
    """

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch rules from complex section ranges (keyword actions/abilities)."""
        ds = self.domain.get_data_source()
        raw = ds.get_rules(limit=500)

        batches = [
            r
            for r in raw
            if self._in_complex_section(r) and len(r.get("text", "")) >= 80
        ]
        logger.info(
            "Loaded %d complex-section rules (from %d raw, filtered text >= 80 chars)",
            len(batches),
            len(raw),
        )
        return batches

    def build_prompt(self, template: TemplateConfig, data_batch: dict[str, Any]) -> str:
        """Build the LLM prompt exploring an edge case.

        Formats the template instruction with rule data, then wraps with
        notation legend and <task> tags.
        """
        text = data_batch.get("text", "")
        section = data_batch.get("section", "")

        task_instruction = template.task_instruction.format(
            rule_number=data_batch.get("ruleNumber", ""),
            rule_text=text,
            section=section,
        )
        notation = self.domain.notation_legend
        prompt_body = (
            f"Explain this edge case: {text} from section {section}. "
            f"What tricky situations can arise?"
        )
        return f"{notation}\n\n<task>\n{task_instruction}\n\n{prompt_body}\n</task>"

    def build_context(self, data_batch: dict[str, Any]) -> str | None:
        """Build metadata context with rule number, section, and text."""
        return (
            f"Category: {self.get_source_category()}\n"
            f"Rule: {data_batch.get('ruleNumber', '')}\n"
            f"Section: {data_batch.get('section', '')}\n"
            f"Text: {data_batch.get('text', '')}"
        )

    def get_source_category(self) -> str:
        return "rule_edge_cases"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _in_complex_section(rule: dict[str, Any]) -> bool:
        """Check if a rule belongs to sections 701-708 (keyword actions/abilities)."""
        section = _extract_section(rule)
        return 701 <= section <= 708
