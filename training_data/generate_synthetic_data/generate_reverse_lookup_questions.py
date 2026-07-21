"""Generate Reverse Lookup Questions using BaseGenerator and MTGDataAccess.

Generates Q&A pairs for reverse lookup queries (feature → cards) across four categories:
1. mechanic_search - "What cards have [mechanic/keyword]?"
2. tribal_search - "What are the best [creature type] cards for Commander?"
3. utility_search - "What cards can [utility effect]?"
4. commander_search - "What commanders support [theme/mechanic]?"
"""

from __future__ import annotations

import random
from typing import Any, Iterator
from dataclasses import dataclass

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .models import Model, ModelType, ValidationMetrics
from .domain_models import CardWithMetadata, Keyword
from .common import MTG_NOTATION_LEGEND, SYSTEM_MESSAGE, OUTPUT_FORMAT
from .query_model import QueryModel


# Keyword/Mechanic categories for reverse lookup
LOOKUP_CATEGORIES = {
    "mechanics": [
        "landfall", "magecraft", "proliferate", "cascade", "storm", "affinity",
        "delve", "convoke", "emerge", "escape", "foretell", "mutate",
        "companion", "partner", "background", "doctor's companion",
    ],
    "keywords": [
        "flying", "trample", "deathtouch", "lifelink", "first strike",
        "double strike", "haste", "vigilance", "reach", "menace", "ward",
        "indestructible", "hexproof", "protection",
    ],
    "tribes": [
        "elf", "goblin", "zombie", "spirit", "human", "merfolk", "dragon",
        "angel", "demon", "vampire", "werewolf", "sliver", "ally", "cleric",
        "wizard", "warrior", "soldier", "knight", "rogue", "shaman",
    ],
    "utility": [
        "protect commander", "draw on creature death", "sacrifice outlet",
        "mana sink", "graveyard hate", "artifact hate", "enchantment hate",
        "land destruction", "counterspell", "board wipe", "tutor", "ramp",
        "card draw",
    ],
}


# Rule section mapping for keywords/mechanics
RULE_SECTIONS = {
    "landfall": "702.144",
    "magecraft": "702.157",
    "proliferate": "701.27",
    "cascade": "702.85",
    "storm": "702.40",
    "affinity": "702.41",
    "delve": "702.66",
    "convoke": "702.51",
    "emerge": "702.119",
    "escape": "702.138",
    "foretell": "702.143",
    "mutate": "702.140",
    "companion": "702.139",
    "partner": "702.123",
    "background": "702.155",
    "doctor's companion": "702.156",
    "flying": "702.9",
    "trample": "702.19",
    "deathtouch": "702.2",
    "lifelink": "702.15",
    "first strike": "702.7",
    "double strike": "702.4",
    "haste": "702.10",
    "vigilance": "702.20",
    "reach": "702.17",
    "menace": "702.111",
    "ward": "702.158",
    "indestructible": "702.12",
    "hexproof": "702.11",
    "protection": "702.16",
}


@dataclass(frozen=True)
class KeywordContext:
    """Context for a keyword/mechanic including definition and example cards."""
    name: str
    category: str
    description: str
    rule_section: str | None
    example_cards: list[CardWithMetadata]


class GenerateReverseLookupQuestions(BaseGenerator[KeywordContext]):
    """Generate reverse lookup questions (feature → cards) using BaseGenerator."""

    TEMPLATES: list[TemplateConfig] = [
        TemplateConfig(
            template_id="mechanic_search",
            task_instruction=(
                "Generate 3 Q&A pairs for: \"What cards have [mechanic/keyword]?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"What cards have [mechanic]?\"\n"
                "- \"Which cards feature [mechanic]?\"\n"
                "- \"Is there a card with [mechanic]?\"\n\n"
                "Answers MUST:\n"
                "1. List 3-5 specific cards from the provided examples\n"
                "2. Explain HOW each card uses the mechanic (quote oracle text)\n"
                "3. Cite the relevant rule section if provided\n"
                "4. Be 3-5 sentences per card mentioned\n"
                "5. Use MTG notation ({T}, {W}, {U}, etc.)"
            ),
            weight=1.0,
            validation_rules=[
                "Answer lists 3-5 specific cards from the provided examples",
                "Answer explains how EACH card uses the mechanic with oracle text quotes",
                "Answer cites rule section when provided",
                "Answer is at least 200 characters",
                "Answer does not reference rule numbers directly (explain conversationally)",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=200,
        ),
        TemplateConfig(
            template_id="tribal_search",
            task_instruction=(
                "Generate 3 Q&A pairs for: \"What are the best [creature type] cards for Commander?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"What are the best [tribe] cards for Commander?\"\n"
                "- \"Which [tribe] cards should I run in my tribal deck?\"\n"
                "- \"Top [tribe] cards for EDH?\"\n\n"
                "Answers MUST:\n"
                "1. Mention tribal synergies (lords, tribal payoffs, kindred effects)\n"
                "2. Include at least one lord effect (creature that buffs the tribe)\n"
                "3. Include at least one tribal support card (non-creature that helps the tribe)\n"
                "4. List 3-5 specific cards from the provided examples with EDHREC stats\n"
                "5. Explain WHY each card is good for the tribe\n"
                "6. Be 3-5 sentences per card"
            ),
            weight=1.0,
            validation_rules=[
                "Answer mentions tribal synergies (lords, payoffs, kindred)",
                "Answer includes at least one lord effect",
                "Answer includes at least one tribal support card",
                "Answer lists 3-5 specific cards with EDHREC stats",
                "Answer explains why each card is good for the tribe",
                "Answer is at least 200 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=200,
        ),
        TemplateConfig(
            template_id="utility_search",
            task_instruction=(
                "Generate 3 Q&A pairs for: \"What cards can [utility effect]?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"What cards can [utility effect]?\"\n"
                "- \"How do I [utility effect] in Commander?\"\n"
                "- \"Best cards for [utility effect]?\"\n\n"
                "Answers MUST:\n"
                "1. Solve the specific utility problem stated in the question\n"
                "2. Explain HOW each card solves the problem (mechanics)\n"
                "3. List 3-5 specific cards from the provided examples\n"
                "4. Include EDHREC rank and price context\n"
                "5. Be 3-5 sentences per card"
            ),
            weight=1.0,
            validation_rules=[
                "Answer solves the specific utility problem stated",
                "Answer explains how EACH card solves the problem mechanically",
                "Answer lists 3-5 specific cards from provided examples",
                "Answer includes EDHREC rank and price context",
                "Answer is at least 200 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=200,
        ),
        TemplateConfig(
            template_id="commander_search",
            task_instruction=(
                "Generate 3 Q&A pairs for: \"What commanders support [theme/mechanic]?\"\n\n"
                "Questions should be natural variations like:\n"
                "- \"What commanders support [theme]?\"\n"
                "- \"Best commanders for a [theme] deck?\"\n"
                "- \"Which legendary creatures work with [mechanic]?\"\n\n"
                "Answers MUST:\n"
                "1. Check color identity of each commander\n"
                "2. Explain commander's synergy with the theme/mechanic\n"
                "3. List 3-5 legendary creatures from the provided examples\n"
                "4. Include EDHREC deck count and salt score\n"
                "5. Explain HOW the commander enables the theme (abilities, color identity)\n"
                "6. Be 3-5 sentences per commander"
            ),
            weight=1.0,
            validation_rules=[
                "Answer checks color identity of each commander",
                "Answer explains commander's synergy with theme/mechanic",
                "Answer lists 3-5 legendary creatures from provided examples",
                "Answer includes EDHREC deck count and salt score",
                "Answer explains HOW commander enables the theme",
                "Answer is at least 200 characters",
                "Answer contains no markdown formatting",
            ],
            min_answer_length=200,
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: callable,
        metrics: ValidationMetrics | None = None,
        generator_name: str | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
    ):
        """Initialize the generator.

        Args:
            data_access: MTGDataAccess instance for querying cards and keywords
            models: Dict with ModelType.GENERATION and ModelType.VALIDATION keys
            validation_pct: Percentage of items to validate (0.0-1.0)
            target_count: Target number of items to generate
            save_item: Callback to save a validated QuestionAnswerEnhanced
            metrics: Optional ValidationMetrics instance
            generator_name: Name for metrics tracking
            dry_run: If True, don't call save_item
            max_regeneration_attempts: Max retries after validation failure
            batch_size: Items per generation batch
            templates_per_item: Number of templates to apply per data item
            enable_extra_validation: Enable detailed verification checklist
        """
        self.data_access = data_access
        self._keyword_taxonomy: dict[str, list[str]] | None = None
        self._all_keywords: list[tuple[str, str]] = []  # (name, category)

        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name=generator_name,
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
        )

    def get_source_category(self) -> str:
        """Return the source category for metrics."""
        return "reverse_lookup"

    def get_data_batches(self) -> Iterator[KeywordContext]:
        """Fetch and yield keyword contexts for generation.

        Builds keyword taxonomy from cards.keywords + cards.subtypes + cards.types,
        then for each keyword/mechanic fetches top 15 cards by EDHREC rank.
        """
        # Build keyword list on first call
        if not self._all_keywords:
            self._build_keyword_list()

        # Shuffle for variety
        random.shuffle(self._all_keywords)

        for keyword_name, category in self._all_keywords:
            if self.generated_count >= self.target_count:
                break

            context = self._build_keyword_context(keyword_name, category)
            if context and context.example_cards:
                yield context

    def _build_keyword_list(self) -> None:
        """Build comprehensive keyword list from taxonomy and categories."""
        # Get keyword taxonomy from database
        taxonomy = self.data_access.get_keyword_taxonomy()

        # Add keywords from taxonomy
        for keyword in taxonomy.keys():
            # Categorize based on LOOKUP_CATEGORIES
            category = self._categorize_keyword(keyword)
            self._all_keywords.append((keyword.lower(), category))

        # Add explicit categories from LOOKUP_CATEGORIES
        for category, keywords in LOOKUP_CATEGORIES.items():
            for keyword in keywords:
                if not any(k[0] == keyword.lower() for k in self._all_keywords):
                    self._all_keywords.append((keyword.lower(), category))

    def _categorize_keyword(self, keyword: str) -> str:
        """Categorize a keyword based on LOOKUP_CATEGORIES."""
        keyword_lower = keyword.lower()
        for category, keywords in LOOKUP_CATEGORIES.items():
            if keyword_lower in [k.lower() for k in keywords]:
                return category
        # Default categorization based on keyword taxonomy
        return "keywords"

    def _build_keyword_context(self, keyword_name: str, category: str) -> KeywordContext | None:
        """Build context for a keyword/mechanic including definition and example cards."""
        # Get description from taxonomy
        taxonomy = self.data_access.get_keyword_taxonomy()
        description = ""
        if keyword_name in taxonomy:
            desc_list = taxonomy[keyword_name]
            description = desc_list[0] if desc_list else ""

        # Get rule section
        rule_section = RULE_SECTIONS.get(keyword_name.lower())

        # Fetch example cards based on category
        example_cards = self._fetch_example_cards(keyword_name, category)

        if not example_cards:
            return None

        # Sort by EDHREC rank (lower is better) and take top 15
        example_cards.sort(key=lambda c: c.edhrec_rank or 999999)
        example_cards = example_cards[:15]

        return KeywordContext(
            name=keyword_name,
            category=category,
            description=description,
            rule_section=rule_section,
            example_cards=example_cards,
        )

    def _fetch_example_cards(self, keyword_name: str, category: str) -> list[CardWithMetadata]:
        """Fetch example cards for a keyword/mechanic based on category."""
        cards = []

        if category == "mechanics":
            # Search by keyword/mechanic name
            cards = self.data_access.get_cards_by_keyword_mechanic(keyword_name, limit=50)
            # Also try text search for mechanics not in keywords
            if not cards:
                cards = self.data_access.search_cards_text(keyword_name, limit=50)

        elif category == "keywords":
            # Search by keyword
            cards = self.data_access.get_cards_by_keyword_mechanic(keyword_name, limit=50)

        elif category == "tribes":
            # Search by creature subtype
            cards = self.data_access.search_cards_text(
                rf"\b{keyword_name}\b",  # Word boundary for subtype
                filters={"type": {"$regex": "creature", "$options": "i"}},
                limit=50
            )

        elif category == "utility":
            # Map utility terms to search patterns
            utility_patterns = {
                "protect commander": r"protect.*commander|commander.*protect|indestructible.*commander|hexproof.*commander",
                "draw on creature death": r"draw.*creature.*dies|creature dies.*draw|whenever a creature dies.*draw",
                "sacrifice outlet": r"sacrifice.*creature.*draw|sacrifice.*creature.*mana|sacrifice.*creature.*damage|sacrifice.*creature.*card",
                "mana sink": r"mana sink|{X}.*{T}|{X}.*activate|sink.*mana",
                "graveyard hate": r"exile.*graveyard|graveyard.*exile|rest in peace|leyline of the void|grafdigger's cage",
                "artifact hate": r"destroy.*artifact|artifact.*destroy|shatter|vandalblast|reclamation sage",
                "enchantment hate": r"destroy.*enchantment|enchantment.*destroy|disenchant|naturalize|krosan grip",
                "land destruction": r"destroy.*land|land.*destroy|strip mine|wasteland|ghost quarter",
                "counterspell": r"counter target spell|counter.*spell|mana drain|force of will|pact of negation",
                "board wipe": r"destroy all creature|destroy all nonland|wrath of god|damnation|supreme verdict|cyclonic rift",
                "tutor": r"search.*library|tutor|demonic tutor|vampiric tutor|worldly tutor|mystical tutor",
                "ramp": r"search.*library.*land|put.*land.*battlefield|rampant growth|kodama's reach|cultivate|explosive vegetation",
                "card draw": r"draw.*card|draw a card|card draw|rhystic study|necropotence|phyrexian arena",
            }
            pattern = utility_patterns.get(keyword_name.lower(), keyword_name)
            cards = self.data_access.search_cards_text(pattern, limit=50)

        return cards

    def build_prompt(self, template: TemplateConfig, data_batch: KeywordContext) -> str:
        """Build the LLM prompt for a specific template and keyword context."""
        context = data_batch

        # Build card details for prompt
        card_details = self._format_cards_for_prompt(context.example_cards)

        # Build rule section reference
        rule_ref = f"\nRelevant rule section: {context.rule_section}" if context.rule_section else ""

        # Build description
        desc = f"\nMechanic/Keyword: {context.name}\nDescription: {context.description}{rule_ref}\n" if context.description else f"\nMechanic/Keyword: {context.name}{rule_ref}\n"

        prompt = f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

{OUTPUT_FORMAT}

{template.task_instruction}

{desc}

Matching cards (top 15 by EDHREC rank):
{card_details}

Generate 3 Q&A pairs in JSON format. The answer MUST be a single string, not an array.
"""
        return prompt

    def _format_cards_for_prompt(self, cards: list[CardWithMetadata]) -> str:
        """Format cards for prompt context."""
        lines = []
        for i, card in enumerate(cards, 1):
            face = card.primary_face
            lines.append(
                f"{i}. {card.name} (EDHREC Rank: {card.edhrec_rank or 'N/A'}, "
                f"Price: ${card.prices.best_price if card.prices and card.prices.best_price else 'N/A'})"
            )
            lines.append(f"   Type: {face.type_line or card.type or 'N/A'}")
            lines.append(f"   Cost: {face.mana_cost or card.mana_cost or 'N/A'}")
            lines.append(f"   Oracle Text: {face.oracle_text or card.text or 'N/A'}")
            if card.color_identity:
                lines.append(f"   Color Identity: {', '.join(card.color_identity)}")
            if card.keywords:
                lines.append(f"   Keywords: {', '.join(card.keywords)}")
            if card.edhrec_tags:
                lines.append(f"   Tags: {', '.join(card.edhrec_tags)}")
            lines.append("")
        return "\n".join(lines)

    def build_context(self, template: TemplateConfig, data_batch: KeywordContext) -> str:
        """Build validation context for the generated Q&A."""
        context = data_batch
        return (
            f"Category: {self.get_source_category()}\n"
            f"Template: {template.template_id}\n"
            f"Keyword/Mechanic: {context.name}\n"
            f"Category: {context.category}\n"
            f"Description: {context.description}\n"
            f"Rule Section: {context.rule_section or 'N/A'}\n"
            f"Example Cards: {len(context.example_cards)} cards\n"
            f"Card Names: {', '.join(c.name for c in context.example_cards[:5])}"
        )

    def get_source_data(self, data_batch: KeywordContext) -> list[Any]:
        """Extract source data references for the generated document."""
        return [card.name for card in data_batch.example_cards[:5]]


# Backward compatibility wrapper for old main.py interface
class GenerateReverseLookupQuestionsLegacy:
    """Legacy wrapper for backward compatibility with main.py."""

    def __init__(
        self,
        cards_collection,
        save_item: callable,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 3000,
        metrics: ValidationMetrics | None = None,
    ):
        self.cards_collection = cards_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_reverse_lookup_questions(self) -> None:
        """Legacy method - delegates to new BaseGenerator implementation."""
        # Create data access
        data_access = MTGDataAccess()
        data_access.connect()

        try:
            generator = GenerateReverseLookupQuestions(
                data_access=data_access,
                models=self.models,
                validation_pct=self.validation_pct,
                target_count=self.target_count,
                save_item=self.save_item,
                metrics=self.metrics,
                generator_name="GenerateReverseLookupQuestions",
            )
            generator.generate()
        finally:
            data_access.close()