"""MTG (Magic: The Gathering) domain plugin for TrainForge."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from trainforge.data_source import DataSource
from trainforge.domain import DomainPlugin, get_registry
from .data_source import MTGDataAccess

logger = logging.getLogger(__name__)


class MTGDomain(DomainPlugin):
    """Magic: The Gathering domain plugin.

    Provides system message, notation legend, data access, and template loading
    for all 27 MTG generation categories.
    """

    # -- Domain identity -------------------------------------------------

    @property
    def name(self) -> str:
        return "mtg"

    @property
    def display_name(self) -> str:
        return "Magic: The Gathering"

    # -- LLM context (loaded from templates.yaml) ------------------------

    def __init__(self):
        self._system_message: str = ""
        self._notation_legend: str = ""
        self._templates_yaml: dict[str, Any] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load system message and notation legend from templates.yaml."""
        templates_path = Path(__file__).parent / "templates.yaml"
        if not templates_path.exists():
            logger.warning(
                "templates.yaml not found at %s — using empty defaults", templates_path
            )
            return

        data = self.load_templates_yaml(templates_path)
        self._system_message = data.get("system_message", "").strip()
        self._notation_legend = data.get("notation_legend", "").strip()
        self._templates_yaml = data

    @property
    def system_message(self) -> str:
        return self._system_message or (
            "<system>\n"
            "You are an expert Magic: The Gathering rules advisor. You generate "
            "accurate, natural Q&A training data about card combos. You output "
            "ONLY valid JSON — no preamble, no explanation, no markdown fences.\n"
            "</system>"
        )

    @property
    def notation_legend(self) -> str:
        return self._notation_legend or ""

    # -- Data access -----------------------------------------------------

    def get_data_source(
        self, config: dict[str, Any] | None = None
    ) -> DataSource:
        """Create an MTGDataAccess instance connected to MongoDB."""
        cfg = config or {}
        return MTGDataAccess(
            uri=cfg.get("uri", "mongodb://localhost:27017"),
            username=cfg.get("username", "root"),
            password=cfg.get("password", "whatever"),
            auth_source=cfg.get("auth_source", "admin"),
        )

    # -- Generators (will be populated when generator migration is done) ---

    def get_generators(self) -> list[type]:
        """Return list of generator classes available in this domain.

        Currently includes 7 topic-based + 16 data-driven = 23 generators.
        """
        from .generators import (
            ArchetypesGenerator,
            ArticleQAGenerator,
            BudgetAlternativesGenerator,
            ColorIdentityQuestionsGenerator,
            ColorStaplesGenerator,
            ComboQueriesGenerator,
            GameTheoryGenerator,
            GenerateCardSearchQueries,
            GenerateCommanderBuilding,
            GenerateCommanderKnowledge,
            GenerateComparisonQuestions,
            GenerateDeckbuildingTheory,
            GenerateReverseLookupQuestions,
            GenerateSynergyQuestions,
            GenerateTerminologyQuestions,
            GlossaryWithExamplesGenerator,
            GuideQAGenerator,
            MetaKnowledgeGenerator,
            MultiCardUsageGenerator,
            QuickGuidelinesGenerator,
            RuleEdgeCasesGenerator,
            RuleExplanationsGenerator,
            RuleInteractionsGenerator,
            RuleWhyQuestionsGenerator,
            RulesScenariosGenerator,
            SaltQuestionsGenerator,
            StapleAnalysisGenerator,
        )
        return [
            ArchetypesGenerator,
            ArticleQAGenerator,
            BudgetAlternativesGenerator,
            ColorIdentityQuestionsGenerator,
            ColorStaplesGenerator,
            ComboQueriesGenerator,
            GameTheoryGenerator,
            GenerateCardSearchQueries,
            GenerateCommanderBuilding,
            GenerateCommanderKnowledge,
            GenerateComparisonQuestions,
            GenerateDeckbuildingTheory,
            GenerateReverseLookupQuestions,
            GenerateSynergyQuestions,
            GenerateTerminologyQuestions,
            GlossaryWithExamplesGenerator,
            GuideQAGenerator,
            MetaKnowledgeGenerator,
            MultiCardUsageGenerator,
            QuickGuidelinesGenerator,
            RuleEdgeCasesGenerator,
            RuleExplanationsGenerator,
            RuleInteractionsGenerator,
            RuleWhyQuestionsGenerator,
            RulesScenariosGenerator,
            SaltQuestionsGenerator,
            StapleAnalysisGenerator,
        ]

    # -- Categories -------------------------------------------------------

    def get_categories(self) -> list[str]:
        """Return all 27 MTG generation category identifiers."""
        if self._templates_yaml:
            categories = self._templates_yaml.get("categories", {})
            return sorted(categories.keys())
        return [
            "combo_query", "article_qa", "card_search", "comparison",
            "reverse_lookup", "synergy", "budget", "color_identity",
            "guidelines", "terminology", "deckbuilding_theory",
            "commander_building", "rules_scenarios", "archetypes",
            "game_theory", "meta_knowledge", "commander_knowledge",
            "rule_explanations", "rule_interactions", "glossary_with_examples",
            "rule_edge_cases", "rule_why_questions", "guide_qa",
            "staple_analysis", "color_staples", "salt_questions",
            "multi_card_usage",
        ]

    # -- Template loading override ----------------------------------------

    def get_templates_for_category(
        self, templates_yaml: dict[str, Any] | None = None, category: str = ""
    ):
        """Use pre-loaded templates if available."""
        yaml_data = templates_yaml or self._templates_yaml
        return super().get_templates_for_category(yaml_data, category)


# =============================================================================
# AUTO-REGISTRATION
# =============================================================================

_registry = get_registry()
_registry.register(MTGDomain())
logger.info("MTG domain auto-registered with DomainRegistry")
