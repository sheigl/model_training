"""Generate card search query Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .domain_models import CardWithMetadata
from .models import Model, ModelType, ValidationMetrics
from .common import (
    MTG_NOTATION_LEGEND,
    NEW_LINE,
    build_card_detail,
)
from .query_model import QueryModel


# =============================================================================
# VALIDATION RULES PER TEMPLATE
# =============================================================================

COMPETITIVE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not cite EDHREC rank for at least one recommended card.
2. Answer does not mention inclusion percentage or deck prevalence for at least one card.
3. Answer does not mention at least one top-tier competitive card (EDHREC rank < 500).
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. At least one card's EDHREC rank is cited.
2. At least one card's inclusion percentage or deck prevalence is mentioned.
3. At least one top-tier competitive card (EDHREC rank < 500) is recommended.
4. Answer explains WHY these cards are competitive choices.
5. No markdown formatting.
6. No rule number references.
"""

BUDGET_VALIDATION = """
HARD REJECT RULES:
1. Answer does not cite actual USD prices for at least one recommended card.
2. Answer does not mention budget alternatives under $5.
3. Answer recommends cards over $5 without noting they exceed budget.
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. At least one card's actual price (USD) is cited.
2. All recommended cards are under $5 or explicitly noted as budget alternatives.
3. Answer explains what each budget card does and why it's a good alternative.
4. No markdown formatting.
5. No rule number references.
"""

COMMANDER_SPECIFIC_VALIDATION = """
HARD REJECT RULES:
1. Answer does not check color identity legality for the commander.
2. Answer does not mention commander synergy or why cards work with that commander.
3. Answer recommends cards illegal in the commander's color identity.
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. Color identity legality is explicitly checked and stated.
2. Commander synergy is explained (why these cards work with that commander).
3. All recommended cards are legal in the commander's color identity.
4. At least one card's interaction with the commander's abilities is described.
5. No markdown formatting.
6. No rule number references.
"""

THEMATIC_VALIDATION = """
HARD REJECT RULES:
1. Answer does not explain mechanic synergy or how cards interact with the theme.
2. Answer does not cite keyword interactions or mechanic-specific synergies.
3. Answer lists cards without explaining thematic relevance.
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. Mechanic/theme synergy is explicitly explained.
2. Keyword interactions are cited (e.g., "works with treasure tokens because...").
3. Each recommended card's thematic relevance is explained.
4. At least one specific keyword or mechanic interaction is described.
5. No markdown formatting.
6. No rule number references.
"""

BEGINNER_VALIDATION = """
HARD REJECT RULES:
1. Answer uses MTG jargon without explanation (e.g., "ramp", "tutor", "ETB", "value" without defining).
2. Answer does not give concrete card examples with simple explanations.
3. Answer assumes knowledge of competitive concepts (EDHREC rank, meta, cEDH).
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. Jargon is either avoided or explained in simple terms.
2. At least 3 concrete card examples are given with plain-language explanations.
3. Advice is framed for a beginner (budget-friendly, easy to understand).
4. No competitive jargon (EDHREC, meta, cEDH, salt score) without explanation.
5. No markdown formatting.
6. No rule number references.
"""


# =============================================================================
# SEARCH PATTERNS
# =============================================================================

SEARCH_PATTERNS = [
    {
        "name": "Green Ramp",
        "filters": {"text_regex": "search.*land", "colors": ["G"]},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Zombie Tokens",
        "filters": {"text_regex": "zombie.*token"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Treasure Tokens",
        "filters": {"text_regex": "treasure"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "White Removal",
        "filters": {"text_regex": "exile|destroy", "colors": ["W"]},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Blue Card Draw",
        "filters": {"text_regex": "draw.*card", "colors": ["U"]},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "ETB Effects",
        "filters": {"text_regex": "enters the battlefield"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Black Removal",
        "filters": {"text_regex": "destroy.*creature", "colors": ["B"]},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Red Burn",
        "filters": {"text_regex": "deals.*damage", "colors": ["R"]},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Counterspells",
        "filters": {"text_regex": "counter target", "colors": ["U"]},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Board Wipes",
        "filters": {"text_regex": "destroy all|exile all"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Tutors",
        "filters": {"text_regex": "search.*library"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Reanimation",
        "filters": {"text_regex": "return.*creature.*graveyard|graveyard.*battlefield"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Protection",
        "filters": {"text_regex": "protection from|hexproof|indestructible|ward"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Sacrifice Outlets",
        "filters": {"text_regex": "sacrifice.*creature|sacrifice.*permanent"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Artifact Ramp",
        "filters": {"text_regex": "add.*mana|tap.*add", "colors": []},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Graveyard Hate",
        "filters": {"text_regex": "exile.*graveyard|graveyard.*exile"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Politics/Group Hug",
        "filters": {"text_regex": "each player|all players|each opponent"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Landfall",
        "filters": {"text_regex": "landfall|whenever.*land.*enters"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Proliferate",
        "filters": {"text_regex": "proliferate"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
    {
        "name": "Blink/Flicker",
        "filters": {"text_regex": "exile.*return|blink|flicker"},
        "templates": ["competitive", "budget", "commander_specific", "thematic", "beginner"],
    },
]


# =============================================================================
# COMMANDER POOL FOR COMMANDER_SPECIFIC TEMPLATE
# =============================================================================

COMMON_COMMANDERS = [
    {"name": "Atraxa, Praetors' Voice", "colors": ["W", "U", "B", "G"]},
    {"name": "Edgar Markov", "colors": ["W", "B", "R"]},
    {"name": "The Ur-Dragon", "colors": ["W", "U", "B", "R", "G"]},
    {"name": "Krenko, Mob Boss", "colors": ["R"]},
    {"name": "Meren of Clan Nel Toth", "colors": ["B", "G"]},
    {"name": "Korvold, Fae-Cursed King", "colors": ["B", "R", "G"]},
    {"name": "Tatyova, Benthic Druid", "colors": ["G", "U"]},
    {"name": "Lathril, Blade of the Elves", "colors": ["B", "G"]},
    {"name": "Miirym, Sentinel Wyrm", "colors": ["R", "G", "U"]},
    {"name": "Prosper, Tome-Bound", "colors": ["B", "R"]},
    {"name": "Sissay, Weatherlight Captain", "colors": ["W", "U", "B", "R", "G"]},
    {"name": "Tymna the Weaver", "colors": ["W", "B"]},
    {"name": "Kinnan, Bonder Prodigy", "colors": ["G", "U"]},
    {"name": "Rograkh, Son of Rohgahh", "colors": ["R"]},
    {"name": "Tivit, Seller of Secrets", "colors": ["W", "U", "B"]},
]


# =============================================================================
# GENERATOR CLASS
# =============================================================================

class GenerateCardSearchQueries(BaseGenerator[CardWithMetadata]):
    """Generate card search query Q&A pairs from enriched card data."""

    TEMPLATES = [
        TemplateConfig(
            template_id="competitive",
            task_instruction="""Generate exactly 3 Q&A pairs for COMPETITIVE Commander players asking about the best cards for this effect.
Focus on: EDHREC rank, inclusion percentage, top-tier competitive staples, and why these cards dominate the meta.
At least one question must be phrased as a competitive player optimizing their deck.""",
            validation_rules=COMPETITIVE_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="budget",
            task_instruction="""Generate exactly 3 Q&A pairs for BUDGET-CONSCIOUS Commander players asking about affordable options for this effect.
Focus on: actual USD prices (cite specific prices), cards under $5, budget alternatives, and value-for-money.
At least one question must be phrased as a player with a strict budget (e.g., "under $5 per card").""",
            validation_rules=BUDGET_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="commander_specific",
            task_instruction="""Generate exactly 3 Q&A pairs for players building around a SPECIFIC COMMANDER asking what cards with this effect work well in that deck.
Focus on: color identity legality, commander synergy (how the effect interacts with the commander's abilities), and deck-specific strategy.
At least one question must name a specific commander and ask about synergy.""",
            validation_rules=COMMANDER_SPECIFIC_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="thematic",
            task_instruction="""Generate exactly 3 Q&A pairs for players building a THEMATIC/MECHANIC-FOCUSED deck asking what cards support this strategy.
Focus on: mechanic synergy, keyword interactions, how cards enable the theme, and thematic coherence.
At least one question must ask about the mechanic/theme by name (e.g., "What cards support a treasure strategy?").""",
            validation_rules=THEMATIC_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="beginner",
            task_instruction="""Generate exactly 3 Q&A pairs for BEGINNER Commander players asking what cards with this effect they should consider.
Focus on: simple explanations (no jargon or explain it), concrete card examples with plain-language descriptions, budget-friendly options, and why each card is good for learning.
At least one question must be phrased as a new player (e.g., "I'm new to Commander...").""",
            validation_rules=BEGINNER_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 5000,
        save_item: callable = None,
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
    ):
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateCardSearchQueries",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
        )
        self.data_access = data_access
        self._query_model = QueryModel()

    def get_data_batches(self) -> Iterator[list[CardWithMetadata]]:
        """Fetch card batches for each search pattern and template combination."""
        # We'll iterate through patterns and yield cards for each
        for pattern in SEARCH_PATTERNS:
            filters = self._build_filters(pattern["filters"])
            cards = self.data_access.get_cards_enriched(filters=filters, limit=20)
            
            if not cards:
                continue
            
            # Yield cards for each template this pattern supports
            for template_id in pattern.get("templates", ["competitive", "budget", "commander_specific", "thematic", "beginner"]):
                # Create copies of cards with pattern/template metadata attached
                # (avoid mutating shared card objects across template iterations)
                batch = []
                for card in cards:
                    # Create a shallow copy with metadata attached
                    card_copy = card.model_copy(deep=False)
                    card_copy._search_pattern = pattern
                    card_copy._template_id = template_id
                    batch.append(card_copy)
                yield batch

    def _build_filters(self, pattern_filters: dict) -> dict:
        """Convert pattern filters to MongoDB query filters."""
        filters = {}
        
        if "text_regex" in pattern_filters:
            filters["oracleText"] = {"$regex": pattern_filters["text_regex"], "$options": "i"}
        
        if "colors" in pattern_filters and pattern_filters["colors"]:
            filters["colorIdentity"] = {"$all": pattern_filters["colors"]}
        
        # Add common filters for Commander playability
        filters["legalities.commander"] = "legal"
        
        return filters

    def build_prompt(self, template: TemplateConfig, data_batch: list[CardWithMetadata]) -> str:
        """Build the LLM prompt for a specific template and card batch."""
        if not data_batch:
            return ""
        
        pattern = data_batch[0]._search_pattern
        template_id = data_batch[0]._template_id
        
        # Build card details for prompt
        card_details = NEW_LINE.join(
            map(lambda c: build_card_detail(card_number=None, card=c), data_batch[:10])
        )
        
        # Get pattern name and effect description
        effect_name = pattern["name"]
        
        # Build template-specific context
        if template_id == "commander_specific":
            commander = random.choice(COMMON_COMMANDERS)
            commander_context = f"\nCommander: {commander['name']} (Color Identity: {', '.join(commander['colors'])})"
        else:
            commander_context = ""
        
        if template_id == "thematic":
            theme_context = f"\nTheme/Mechanic: {effect_name}"
        else:
            theme_context = ""
        
        # Build the prompt
        prompt = f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<cards>
{card_details}
</cards>

<task>
{template.task_instruction}

Effect/Theme: {effect_name}{commander_context}{theme_context}

REQUIREMENTS:
{NEW_LINE.join(f"{i+1}. {req}" for i, req in enumerate(REQUIREMENTS_BASE))}

{OUTPUT_FORMAT}
</task>"""
        
        return prompt

    def get_source_category(self) -> str:
        return "card_search"

    def get_source_data(self, data_batch: list[CardWithMetadata]) -> list:
        """Extract source data references for the generated document."""
        if not data_batch:
            return []
        return [card.to_dict() for card in data_batch[:10]]

    def build_context(self, template: TemplateConfig, data_batch: list[CardWithMetadata]) -> str:
        """Build validation context for the generated Q&A."""
        if not data_batch:
            return f"Category: {self.get_source_category()}\nTemplate: {template.template_id}"
        
        pattern = data_batch[0]._search_pattern
        template_id = data_batch[0]._template_id
        
        # Build rich context with card details for validation
        card_context_lines = []
        for card in data_batch[:10]:
            price_str = "N/A"
            if card.prices and card.prices.best_price:
                price_str = f"${card.prices.best_price:.2f}"
            
            edhrec_str = f"EDHREC Rank: {card.edhrec_rank:,}" if card.edhrec_rank else "EDHREC Rank: N/A"
            inclusion_str = ""
            if card.edhrec_rank and card.edhrec_rank < 10000:
                # Rough inclusion estimate based on rank
                inclusion_str = f" ~Top {card.edhrec_rank//100}%"
            
            keywords_str = f"Keywords: {', '.join(card.keywords)}" if card.keywords else "Keywords: None"
            legalities_str = "Legal in Commander" if card.is_commander_legal else "NOT legal in Commander"
            
            card_context_lines.append(
                f"  - {card.name} | {price_str} | {edhrec_str}{inclusion_str} | "
                f"Color ID: {', '.join(card.color_identity) if card.color_identity else 'Colorless'} | "
                f"{keywords_str} | {legalities_str}"
            )
        
        card_context = NEW_LINE.join(card_context_lines)
        
        # Oracle text snippets for validation
        oracle_snippets = NEW_LINE.join(
            f"  - {card.name}: {card.primary_face.oracle_text[:150]}..." 
            for card in data_batch[:5] if card.primary_face.oracle_text
        )
        
        return f"""Category: {self.get_source_category()}
Template: {template.template_id}
Search Pattern: {pattern['name']}

Card Details for Validation:
{card_context}

Oracle Text Snippets:
{oracle_snippets}

Validation Focus for {template_id}:
{self._get_validation_focus(template_id)}"""

    def _get_validation_focus(self, template_id: str) -> str:
        """Get template-specific validation focus."""
        focuses = {
            "competitive": "Must cite EDHREC rank, inclusion %, mention top-tier cards (rank < 500)",
            "budget": "Must cite actual USD prices, mention budget alternatives under $5",
            "commander_specific": "Must check color identity legality, mention commander synergy",
            "thematic": "Must explain mechanic synergy, cite keyword interactions",
            "beginner": "Must explain in simple terms, avoid jargon, give concrete examples",
        }
        return focuses.get(template_id, "Standard validation")


# =============================================================================
# SHARED CONSTANTS (from constants.py)
# =============================================================================

SYSTEM_MESSAGE = """
<system>
You are an expert Magic: The Gathering Commander advisor. You generate accurate, natural Q&A training data about card search queries. You output ONLY valid JSON — no preamble, no explanation, no markdown fences.
</system>
"""

OUTPUT_FORMAT = """
OUTPUT FORMAT — respond with this JSON structure and nothing else:
    [
        {"question": "...", "answer": "..."},
        {"question": "...", "answer": "..."},
        {"question": "...", "answer": "..."}
    ]
"""

REQUIREMENTS_BASE = [
    "At least one question MUST come from the perspective of a player who doesn't know the exact card names — someone searching for cards by effect. Examples: \"What are the best cards for [effect] in competitive Commander?\" or \"I'm new to Commander, what [effect] cards should I consider?\"",
    "Questions must be varied and natural-sounding.",
    "Answers must accurately explain what the cards do and why they're good for this purpose, based solely on the card data above.",
    "Every answer MUST cite specific cards from the <cards> block above. Do not invent cards not listed.",
    "When explaining why a card is good, quote or closely paraphrase the relevant part of the card's oracle text from the <cards> block.",
    "The answer field MUST be a single string (not an array).",
    "No markdown formatting (bold, italics, bullet points).",
    "No rule number references — explain mechanics conversationally.",
]