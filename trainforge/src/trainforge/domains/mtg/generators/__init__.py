"""MTG generators — topic-based and data-driven Q&A generators."""

from __future__ import annotations

from .archetypes import ArchetypesGenerator
from .article_qa import ArticleQAGenerator
from .budget_alternatives import BudgetAlternativesGenerator
from .card_search_queries import GenerateCardSearchQueries
from .color_identity_questions import ColorIdentityQuestionsGenerator
from .color_staples import ColorStaplesGenerator
from .combo_queries import ComboQueriesGenerator
from .commander_building import GenerateCommanderBuilding
from .commander_knowledge import GenerateCommanderKnowledge
from .comparison_questions import GenerateComparisonQuestions
from .deckbuilding_theory import GenerateDeckbuildingTheory
from .game_theory import GameTheoryGenerator
from .glossary_with_examples import GlossaryWithExamplesGenerator
from .guide_qa import GuideQAGenerator
from .meta_knowledge import MetaKnowledgeGenerator
from .multi_card_usage import MultiCardUsageGenerator
from .quick_guidelines import QuickGuidelinesGenerator
from .reverse_lookup_questions import GenerateReverseLookupQuestions
from .rule_edge_cases import RuleEdgeCasesGenerator
from .rule_explanations import RuleExplanationsGenerator
from .rule_interactions import RuleInteractionsGenerator
from .rule_why_questions import RuleWhyQuestionsGenerator
from .rules_scenarios import RulesScenariosGenerator
from .salt_questions import SaltQuestionsGenerator
from .staple_analysis import StapleAnalysisGenerator
from .synergy_questions import GenerateSynergyQuestions
from .terminology_questions import GenerateTerminologyQuestions

__all__ = [
    "ArchetypesGenerator",
    "ArticleQAGenerator",
    "BudgetAlternativesGenerator",
    "ColorIdentityQuestionsGenerator",
    "ColorStaplesGenerator",
    "ComboQueriesGenerator",
    "GenerateCardSearchQueries",
    "GenerateCommanderBuilding",
    "GenerateCommanderKnowledge",
    "GenerateComparisonQuestions",
    "GenerateDeckbuildingTheory",
    "GameTheoryGenerator",
    "GlossaryWithExamplesGenerator",
    "GuideQAGenerator",
    "MetaKnowledgeGenerator",
    "MultiCardUsageGenerator",
    "QuickGuidelinesGenerator",
    "GenerateReverseLookupQuestions",
    "RuleEdgeCasesGenerator",
    "RuleExplanationsGenerator",
    "RuleInteractionsGenerator",
    "RuleWhyQuestionsGenerator",
    "RulesScenariosGenerator",
    "SaltQuestionsGenerator",
    "StapleAnalysisGenerator",
    "GenerateSynergyQuestions",
    "GenerateTerminologyQuestions",
]
