"""Rule why-questions generator — explains the design rationale behind MTG rules."""

from __future__ import annotations

import logging
import re
from typing import Any

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator

logger = logging.getLogger(__name__)


_RULE_NUM_RE = re.compile(r"(\d+)")


def _extract_section(rule: dict[str, Any]) -> int:
    """Extract the top-level section number from a rule dict.

    Parses the leading digits from ``ruleNumber`` (e.g. ``"100.1"`` → ``100``).
    Falls back to 0 if parsing fails.
    """
    rule_num = rule.get("ruleNumber", "")
    m = _RULE_NUM_RE.match(rule_num)
    return int(m.group(1)) if m else 0


class RuleWhyQuestionsGenerator(BaseGenerator[dict[str, Any]]):
    """Generate Q&A explaining WHY specific MTG rules exist.

    Category: rule_why_questions
    Data batches: Rule dicts from principle sections (100-199, 400-499, 700-799)
    Templates: why_this_rule (from templates.yaml)
    """

    PRINCIPLE_SECTIONS: set[range] = {
        range(100, 200),  # Game concepts
        range(400, 500),  # Playing
        range(700, 800),  # Keyword abilities
    }

    def get_data_batches(self) -> list[dict[str, Any]]:
        """Fetch rules from principle sections with sufficient text."""
        ds = self.domain.get_data_source()
        raw = ds.get_rules(limit=500)

        def _in_principle_sections(rule: dict[str, Any]) -> bool:
            section = _extract_section(rule)
            return any(section in r for r in self.PRINCIPLE_SECTIONS)

        batches = [
            r
            for r in raw
            if _in_principle_sections(r) and len(r.get("text", "")) >= 100
        ]
        logger.info(
            "Loaded %d principle-section rules (from %d raw, filtered text >= 100 chars)",
            len(batches),
            len(raw),
        )
        return batches

    def build_prompt(self, template: TemplateConfig, data_batch: dict[str, Any]) -> str:
        """Build the LLM prompt asking why this rule exists.

        Formats the template instruction with rule data, then wraps with
        notation legend and <task> tags.
        """
        rule_number = data_batch.get("ruleNumber", "")
        text = data_batch.get("text", "")

        task_instruction = template.task_instruction.format(
            rule_number=rule_number,
            rule_text=text,
            section=data_batch.get("section", ""),
        )
        notation = self.domain.notation_legend
        prompt_body = (
            f"Explain WHY MTG rule {rule_number} exists: {text}. "
            f"Why was this designed this way?"
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
        return "rule_why_questions"
