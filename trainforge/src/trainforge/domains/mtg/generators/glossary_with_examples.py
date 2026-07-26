"""Glossary term with example generator — MTG glossary terms with in-game examples."""

from __future__ import annotations

import logging

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import GlossaryTerm

logger = logging.getLogger(__name__)


class GlossaryWithExamplesGenerator(BaseGenerator[GlossaryTerm]):
    """Generate glossary term Q&A with concrete in-game examples.

    Category: glossary_with_examples
    Data batches: GlossaryTerm objects from the MTG glossary (definitions > 30 chars)
    Templates: term_with_example (from templates.yaml)
    """

    def get_data_batches(self) -> list[GlossaryTerm]:
        """Fetch glossary entries, filter for sufficiently long definitions, convert to models."""
        ds = self.domain.get_data_source()
        raw = ds.get_glossary(limit=200)
        terms: list[GlossaryTerm] = []
        for item in raw:
            definition = item.get("definition", "")
            if len(definition) > 30:
                terms.append(GlossaryTerm(**item))
        logger.info(
            "Loaded %d glossary terms (from %d raw, filtered def > 30 chars)",
            len(terms),
            len(raw),
        )
        return terms

    def build_prompt(self, template: TemplateConfig, data_batch: GlossaryTerm) -> str:
        """Build the LLM prompt for a glossary term with example.

        Injects the term name and definition into the prompt so the LLM
        can generate a question and answer about that term.
        """
        task_instruction = template.task_instruction.format(
            term=data_batch.term,
            definition=data_batch.definition,
        )
        notation = self.domain.notation_legend
        return f"{notation}\n\n<task>\n{task_instruction}\n</task>"

    def build_context(self, data_batch: GlossaryTerm) -> str | None:
        """Build metadata context with term and definition."""
        return (
            f"Category: {self.get_source_category()}\n"
            f"Term: {data_batch.term}\n"
            f"Definition: {data_batch.definition}"
        )

    def get_source_category(self) -> str:
        return "glossary_with_examples"
