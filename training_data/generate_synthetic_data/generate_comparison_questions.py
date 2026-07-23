"""Generate card comparison Q&A pairs using BaseGenerator and MTGDataAccess."""

import random
from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .domain_models import CardWithMetadata
from .models import Model, ModelType, ValidationMetrics
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    SYSTEM_MESSAGE,
)
from .logger import print


# =============================================================================
# COMPARISON CATEGORIES - Effect categories with MongoDB query filters
# =============================================================================

COMPARISON_CATEGORIES = [
    {
        "effect": "Fast Mana",
        "filters": {"oracleText": {"$regex": "add.*mana|add {C}", "$options": "i"}, "types": ["Artifact"]},
    },
    {
        "effect": "Green Ramp",
        "filters": {"oracleText": {"$regex": "search.*land", "$options": "i"}, "colors": ["G"]},
    },
    {
        "effect": "Removal",
        "filters": {"oracleText": {"$regex": "destroy|exile", "$options": "i"}},
    },
    {
        "effect": "Card Draw",
        "filters": {"oracleText": {"$regex": "draw.*card", "$options": "i"}},
    },
    {
        "effect": "Counterspells",
        "filters": {"oracleText": {"$regex": "counter target", "$options": "i"}, "types": ["Instant"]},
    },
    {
        "effect": "Board Wipes",
        "filters": {"oracleText": {"$regex": "destroy all|exile all", "$options": "i"}},
    },
    {
        "effect": "Tutors",
        "filters": {"oracleText": {"$regex": "search.*library", "$options": "i"}},
    },
    {
        "effect": "Reanimation",
        "filters": {"oracleText": {"$regex": "return.*creature.*graveyard", "$options": "i"}},
    },
    {
        "effect": "Protection",
        "filters": {"oracleText": {"$regex": "indestructible|hexproof|ward", "$options": "i"}},
    },
    {
        "effect": "Token Generation",
        "filters": {"oracleText": {"$regex": "create.*token", "$options": "i"}},
    },
]


# =============================================================================
# VALIDATION RULES FOR EACH TEMPLATE TYPE
# =============================================================================

POWER_LEVEL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not compare EDHREC rank of both cards.
2. Answer does not mention inclusion percentage (num_decks / total_decks) for both cards.
3. Answer does not reference salt score for either card.
4. Answer does not cite or closely paraphrase oracle text when explaining power level.
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly — mechanics must be explained conversationally.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. EDHREC rank comparison is explicit (lower rank = more popular).
2. Inclusion percentage is calculated or referenced for both cards.
3. Salt score is mentioned and interpreted (higher = more controversial).
4. Oracle text is quoted/paraphrased to justify power level assessment.
5. Context-dependent recommendation is given (not "X is always better").
"""

MANA_EFFICIENCY_VALIDATION = """
HARD REJECT RULES:
1. Answer does not calculate and compare mana value (CMC) of both cards.
2. Answer does not compare CMC to effect (what you get for the cost).
3. Answer does not mention tempo implications (speed of value generation).
4. Answer contains markdown formatting (bold, italics, bullet points).
5. Answer references rule numbers directly.
6. Answer is less than 80 characters.
7. JSON parsing fails.

VALIDATION CHECKLIST:
1. Mana value (CMC) is explicitly stated for both cards.
2. Net mana advantage/disadvantage is calculated (e.g., "costs 2, taps for 2 = net zero").
3. Tempo is discussed: when does value come online? (turn 1, turn 2, delayed).
4. Colored vs colorless mana production is distinguished.
5. Activation costs vs casting costs are distinguished correctly.
"""

COMMANDER_SUITABILITY_VALIDATION = """
HARD REJECT RULES:
1. Answer does not check color identity legality for the example commander.
2. Answer does not mention commander synergy (how the card interacts with the commander's abilities).
3. Answer contains markdown formatting (bold, italics, bullet points).
4. Answer references rule numbers directly.
5. Answer is less than 80 characters.
6. JSON parsing fails.

VALIDATION CHECKLIST:
1. Color identity of both cards is stated and compared to commander's color identity.
2. Legality verdict (legal/illegal) is explicit for each card in the example commander deck.
3. Commander synergy is explained: how the card works with the commander's abilities/theme.
4. If one card is illegal, the answer explains why (color identity rule).
5. Context-dependent recommendation based on commander strategy.
"""

SYNERGY_POTENTIAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not identify shared keywords/mechanics between the two cards.
2. Answer does not explain the interaction/synergy between the cards and the theme.
3. Answer contains markdown formatting (bold, italics, bullet points).
4. Answer references rule numbers directly.
5. Answer is less than 80 characters.
6. JSON parsing fails.

VALIDATION CHECKLIST:
1. Shared keywords/mechanics are explicitly named (e.g., "both have ETB triggers", "both care about artifacts").
2. The interaction with the named theme is explained mechanically.
3. Specific examples of how the synergy plays out in-game are given.
4. Differences in synergy potential between the two cards are compared.
"""


# =============================================================================
# TEMPLATE CONFIGURATIONS
# =============================================================================

COMPARISON_TEMPLATES = [
    TemplateConfig(
        template_id="power_level",
        task_instruction="""Generate exactly 2 Q&A pairs comparing the POWER LEVEL of these two cards for a specific archetype.

Question format: "Which is stronger: [card1] or [card2] for [archetype]?"

Answers MUST:
- Compare EDHREC rank (lower = more popular/stronger)
- Compare inclusion percentage (num_decks context)
- Compare salt score (controversy level)
- Cite oracle text to justify power assessment
- Give context-dependent recommendation (not absolute)
- Mention card types and their implications (creature vs non-creature vulnerability)""",
        validation_rules=POWER_LEVEL_VALIDATION.strip().split("\n"),
        weight=1.0,
    ),
    TemplateConfig(
        template_id="mana_efficiency",
        task_instruction="""Generate exactly 2 Q&A pairs comparing the MANA EFFICIENCY of these two cards.

Question format: "Which gives better mana value: [card1] or [card2]?"

Answers MUST:
- State the mana value (CMC) of each card explicitly
- Calculate net mana advantage: what you get minus what you pay
- Discuss tempo: when does the value come online? (turn 1, turn 2, delayed)
- Distinguish colored vs colorless mana production
- Distinguish casting cost vs activation cost
- Identify if a card is mana conversion (cost X, produce X) vs actual ramp""",
        validation_rules=MANA_EFFICIENCY_VALIDATION.strip().split("\n"),
        weight=1.0,
    ),
    TemplateConfig(
        template_id="commander_suitability",
        task_instruction="""Generate exactly 2 Q&A pairs comparing COMMANDER SUITABILITY for a specific example commander.

Question format: "Should I run [card1] or [card2] in my [commander] deck?"

Answers MUST:
- State the example commander's name and color identity
- Check color identity legality for BOTH cards against that commander
- Explicitly state legal/illegal for each card
- Explain commander synergy: how each card interacts with the commander's abilities/theme
- If a card is illegal, explain why (color identity rule)
- Give context-dependent recommendation based on commander strategy""",
        validation_rules=COMMANDER_SUITABILITY_VALIDATION.strip().split("\n"),
        weight=1.0,
    ),
    TemplateConfig(
        template_id="synergy_potential",
        task_instruction="""Generate exactly 2 Q&A pairs comparing SYNERGY POTENTIAL with a specific theme/mechanic.

Question format: "Which has better synergy with [theme]: [card1] or [card2]?"

Answers MUST:
- Identify the theme/mechanic (e.g., "artifacts matter", "graveyard recursion", "token doubling")
- Name shared keywords/mechanics between each card and the theme
- Explain the mechanical interaction: how the card's abilities work with the theme
- Give specific in-game examples of the synergy playing out
- Compare which card has stronger/deeper synergy and why""",
        validation_rules=SYNERGY_POTENTIAL_VALIDATION.strip().split("\n"),
        weight=1.0,
    ),
]


# =============================================================================
# EXAMPLE COMMANDERS FOR COMMANDER_SUITABILITY TEMPLATE
# =============================================================================

EXAMPLE_COMMANDERS = [
    {"name": "Atraxa, Praetors' Voice", "color_identity": ["W", "U", "B", "G"], "theme": "proliferate/superfriends"},
    {"name": "Krenko, Mob Boss", "color_identity": ["R"], "theme": "goblin tribal/token swarm"},
    {"name": "Tymna the Weaver + Thrasios, Triton Hero", "color_identity": ["W", "U", "B", "G"], "theme": "value/control"},
    {"name": "Meren of Clan Nel Toth", "color_identity": ["B", "G"], "theme": "reanimation/experience counters"},
    {"name": "Urza, Lord Protector", "color_identity": ["U"], "theme": "artifacts/constructs"},
    {"name": "Korvold, Fae-Cursed King", "color_identity": ["B", "R", "G"], "theme": "sacrifice/aristocrats"},
    {"name": "Teshar, Ancestor's Apostle", "color_identity": ["W"], "theme": "historic/artifacts recursion"},
    {"name": "The Gitrog Monster", "color_identity": ["B", "G"], "theme": "lands matter/graveyard"},
    {"name": "Niv-Mizzet, Parun", "color_identity": ["U", "R"], "theme": "spells matter/card draw"},
    {"name": "Edgar Markov", "color_identity": ["W", "B", "R"], "theme": "vampire tribal/tokens"},
]


# =============================================================================
# SYNERGY THEMES FOR SYNERGY_POTENTIAL TEMPLATE
# =============================================================================

SYNERGY_THEMES = [
    "artifacts matter",
    "graveyard recursion",
    "token doubling",
    "enter-the-battlefield triggers",
    "sacrifice outlets",
    "landfall",
    "spellslinger",
    "enchantress",
    "aristocrats",
    "superfriends/proliferate",
    "equipment/voltron",
    "wheel effects",
    "mana doubling",
    "counter manipulation",
    "tribal synergies",
]


# =============================================================================
# GENERATOR CLASS
# =============================================================================

class GenerateComparisonQuestions(BaseGenerator[tuple[CardWithMetadata, CardWithMetadata]]):
    """Generate card comparison Q&A pairs from enriched card data."""

    TEMPLATES = COMPARISON_TEMPLATES

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 2000,
        save_item: callable = None,
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
        **kwargs,
    ):
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateComparisonQuestions",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
            **kwargs,
        )
        self.data_access = data_access
        self._card_pairs: list[tuple[CardWithMetadata, CardWithMetadata]] = []
        self._pair_index = 0

    def get_data_batches(self) -> Iterator[tuple[CardWithMetadata, CardWithMetadata]]:
        """Fetch and yield card pairs for comparison generation."""
        # Build card pairs on first call
        if not self._card_pairs:
            self._build_card_pairs()

        # Yield pairs until target count or exhaustion
        for pair in self._card_pairs:
            if self._pair_index >= self.target_count:
                break
            self._pair_index += 1
            yield pair

    def _build_card_pairs(self) -> None:
        """Build card pairs from comparison categories using enriched data."""
        print(f"\n[bold cyan]Building card pairs from {len(COMPARISON_CATEGORIES)} comparison categories...[/bold cyan]")

        for category in COMPARISON_CATEGORIES:
            effect_name = category["effect"]
            filters = category["filters"]

            print(f"  → Fetching cards for: {effect_name}")

            # Fetch 15-20 enriched cards per category
            cards = self.data_access.get_cards_enriched(filters=filters, limit=20)

            if len(cards) < 2:
                print(f"    ⚠ Only {len(cards)} cards found for {effect_name}, skipping")
                continue

            # Filter to cards with EDHREC data for meaningful comparisons
            cards_with_edhrec = [c for c in cards if c.edhrec_rank is not None]
            if len(cards_with_edhrec) < 2:
                cards_with_edhrec = cards  # Fallback to all cards

            print(f"    Found {len(cards_with_edhrec)} cards with EDHREC data")

            # Create pairs using different strategies
            pairs = self._create_pairs(cards_with_edhrec, effect_name)
            self._card_pairs.extend(pairs)

            if len(self._card_pairs) >= self.target_count * 2:  # 2x buffer for validation failures
                break

        # Shuffle pairs for variety
        random.shuffle(self._card_pairs)
        print(f"  ✓ Built {len(self._card_pairs)} card pairs")

    def _create_pairs(
        self, cards: list[CardWithMetadata], effect_name: str
    ) -> list[tuple[CardWithMetadata, CardWithMetadata]]:
        """Create card pairs using multiple strategies."""
        pairs = []

        if len(cards) < 2:
            return pairs

        # Strategy 1: Adjacent in EDHREC rank (similar popularity tier)
        sorted_by_rank = sorted(cards, key=lambda c: c.edhrec_rank or 999999)
        for i in range(len(sorted_by_rank) - 1):
            pairs.append((sorted_by_rank[i], sorted_by_rank[i + 1]))

        # Strategy 2: Same CMC, different effects/colors
        by_cmc: dict[float, list[CardWithMetadata]] = {}
        for card in cards:
            cmc = card.cmc
            if cmc not in by_cmc:
                by_cmc[cmc] = []
            by_cmc[cmc].append(card)

        for cmc, cmc_cards in by_cmc.items():
            if len(cmc_cards) >= 2:
                # Pair cards with different color identities
                for i in range(len(cmc_cards) - 1):
                    for j in range(i + 1, min(i + 3, len(cmc_cards))):
                        if set(cmc_cards[i].color_identity) != set(cmc_cards[j].color_identity):
                            pairs.append((cmc_cards[i], cmc_cards[j]))

        # Strategy 3: Same effect category, different colors (already filtered by category)
        # Pair across color identities within the same effect
        by_color_id: dict[str, list[CardWithMetadata]] = {}
        for card in cards:
            key = "".join(sorted(card.color_identity)) or "C"
            if key not in by_color_id:
                by_color_id[key] = []
            by_color_id[key].append(card)

        color_ids = list(by_color_id.keys())
        for i in range(len(color_ids)):
            for j in range(i + 1, len(color_ids)):
                if by_color_id[color_ids[i]] and by_color_id[color_ids[j]]:
                    pairs.append((by_color_id[color_ids[i]][0], by_color_id[color_ids[j]][0]))

        # Deduplicate pairs (order doesn't matter)
        seen = set()
        unique_pairs = []
        for c1, c2 in pairs:
            key = tuple(sorted([c1.uuid or c1.name, c2.uuid or c2.name]))
            if key not in seen:
                seen.add(key)
                unique_pairs.append((c1, c2))

        return unique_pairs[:10]  # Limit pairs per category

    def build_prompt(self, template: TemplateConfig, data_batch: tuple[CardWithMetadata, CardWithMetadata]) -> str:
        """Build the LLM prompt for a card pair and template."""
        card1, card2 = data_batch

        # Select context based on template
        if template.template_id == "commander_suitability":
            commander = random.choice(EXAMPLE_COMMANDERS)
            context = self._build_commander_context(card1, card2, commander)
        elif template.template_id == "synergy_potential":
            theme = random.choice(SYNERGY_THEMES)
            context = self._build_synergy_context(card1, card2, theme)
        elif template.template_id == "power_level":
            archetype = self._infer_archetype(card1, card2)
            context = self._build_power_level_context(card1, card2, archetype)
        else:  # mana_efficiency
            context = self._build_mana_efficiency_context(card1, card2)

        # Build detailed card information for both cards
        card1_detail = card1.to_prompt_detail(include_prices=True, include_rulings=True)
        card2_detail = card2.to_prompt_detail(include_prices=True, include_rulings=True)

        prompt = f"""
{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<cards>
CARD 1:
{card1_detail}

CARD 2:
{card2_detail}
</cards>

<comparison_context>
{context}
</comparison_context>

<task>
{template.task_instruction}

REQUIREMENTS:
- Output exactly 2 Q&A pairs in JSON format
- Questions must follow the specified format for this template
- Answers must be 3-5 sentences with clear reasoning
- Cite specific card text, stats, and mechanics
- No markdown formatting in answers
- The answer field MUST be a single string (not an array)

{OUTPUT_FORMAT}
</task>"""

        return prompt

    def _build_power_level_context(self, card1: CardWithMetadata, card2: CardWithMetadata, archetype: str) -> str:
        """Build context for power level comparison."""
        return f"""Compare POWER LEVEL for {archetype} archetype.

Card 1: {card1.name} (EDHREC Rank: {card1.edhrec_rank or 'N/A'}, Salt: {card1.edhrec_salt or 'N/A'}, Tags: {', '.join(card1.edhrec_tags) if card1.edhrec_tags else 'none'})
Card 2: {card2.name} (EDHREC Rank: {card2.edhrec_rank or 'N/A'}, Salt: {card2.edhrec_salt or 'N/A'}, Tags: {', '.join(card2.edhrec_tags) if card2.edhrec_tags else 'none'})

Question format: "Which is stronger: {card1.name} or {card2.name} for {archetype}?"
"""

    def _build_mana_efficiency_context(self, card1: CardWithMetadata, card2: CardWithMetadata) -> str:
        """Build context for mana efficiency comparison."""
        return f"""Compare MANA EFFICIENCY.

Card 1: {card1.name} (CMC: {card1.cmc}, Mana Cost: {card1.mana_cost or 'N/A'})
Card 2: {card2.name} (CMC: {card2.cmc}, Mana Cost: {card2.mana_cost or 'N/A'})

Question format: "Which gives better mana value: {card1.name} or {card2.name}?"
"""

    def _build_commander_context(
        self, card1: CardWithMetadata, card2: CardWithMetadata, commander: dict
    ) -> str:
        """Build context for commander suitability comparison."""
        cmd_name = commander["name"]
        cmd_colors = commander["color_identity"]
        cmd_theme = commander["theme"]

        # Check color identity legality
        def is_legal(card: CardWithMetadata) -> bool:
            card_colors = set(card.color_identity)
            commander_colors = set(cmd_colors)
            return card_colors.issubset(commander_colors)

        legal1 = is_legal(card1)
        legal2 = is_legal(card2)

        return f"""Compare COMMANDER SUITABILITY for {cmd_name} ({', '.join(cmd_colors)}) - {cmd_theme} theme.

Card 1: {card1.name} (Color Identity: {', '.join(card1.color_identity) if card1.color_identity else 'Colorless'}) - Legal in {cmd_name}: {'YES' if legal1 else 'NO'}
Card 2: {card2.name} (Color Identity: {', '.join(card2.color_identity) if card2.color_identity else 'Colorless'}) - Legal in {cmd_name}: {'YES' if legal2 else 'NO'}

Question format: "Should I run {card1.name} or {card2.name} in my {cmd_name} deck?"
"""

    def _build_synergy_context(
        self, card1: CardWithMetadata, card2: CardWithMetadata, theme: str
    ) -> str:
        """Build context for synergy potential comparison."""
        return f"""Compare SYNERGY POTENTIAL with "{theme}" theme.

Card 1: {card1.name} (Keywords: {', '.join(card1.keywords) if card1.keywords else 'none'}, Type: {card1.type or 'N/A'})
Card 2: {card2.name} (Keywords: {', '.join(card2.keywords) if card2.keywords else 'none'}, Type: {card2.type or 'N/A'})

Question format: "Which has better synergy with {theme}: {card1.name} or {card2.name}?"
"""

    def _infer_archetype(self, card1: CardWithMetadata, card2: CardWithMetadata) -> str:
        """Infer an archetype from card tags and keywords."""
        tags = set(card1.edhrec_tags or []) | set(card2.edhrec_tags or [])
        keywords = set(card1.keywords or []) | set(card2.keywords or [])

        # Map tags/keywords to archetypes
        archetype_map = {
            "ramp": "ramp/big mana",
            "card-draw": "card advantage",
            "removal": "control",
            "counterspell": "control",
            "board-wipe": "control",
            "tutor": "combo/tutor",
            "reanimation": "reanimator",
            "tokens": "token swarm",
            "aristocrats": "aristocrats",
            "equipment": "voltron/equipment",
            "enchantments": "enchantress",
            "lands-matter": "lands matter",
            "spellslinger": "spellslinger",
            "proliferate": "superfriends/proliferate",
            "graveyard": "graveyard value",
            "artifacts": "artifacts",
        }

        for tag in tags:
            tag_lower = tag.lower()
            for key, archetype in archetype_map.items():
                if key in tag_lower:
                    return archetype

        for kw in keywords:
            kw_lower = kw.lower()
            for key, archetype in archetype_map.items():
                if key in kw_lower:
                    return archetype

        return "midrange/value"

    def get_source_category(self) -> str:
        return "comparison"

    def get_source_data(self, data_batch: tuple[CardWithMetadata, CardWithMetadata]) -> list:
        """Extract source data references for the generated document."""
        card1, card2 = data_batch
        return [
            {"name": card1.name, "uuid": card1.uuid, "edhrec_rank": card1.edhrec_rank},
            {"name": card2.name, "uuid": card2.uuid, "edhrec_rank": card2.edhrec_rank},
        ]

    def build_context(self, template: TemplateConfig, data_batch: tuple[CardWithMetadata, CardWithMetadata]) -> str:
        """Build validation context for the generated Q&A."""
        card1, card2 = data_batch

        card1_detail = card1.to_prompt_detail(include_prices=True, include_rulings=True)
        card2_detail = card2.to_prompt_detail(include_prices=True, include_rulings=True)

        template_specific = ""
        if template.template_id == "power_level":
            archetype = self._infer_archetype(card1, card2)
            template_specific = f"""
POWER LEVEL VALIDATION CHECKLIST:
1. EDHREC rank comparison: {card1.name} (rank: {card1.edhrec_rank or 'N/A'}) vs {card2.name} (rank: {card2.edhrec_rank or 'N/A'})
2. Inclusion percentage context must be provided
3. Salt score mentioned: {card1.name} ({card1.edhrec_salt or 'N/A'}) vs {card2.name} ({card2.edhrec_salt or 'N/A'})
4. Oracle text cited for power assessment
5. Archetype context: {archetype}
"""
        elif template.template_id == "mana_efficiency":
            template_specific = f"""
MANA EFFICIENCY VALIDATION CHECKLIST:
1. CMC stated: {card1.name} ({card1.cmc}) vs {card2.name} ({card2.cmc})
2. Net mana advantage calculated
3. Tempo discussed (when value comes online)
4. Colored vs colorless distinguished
5. Casting vs activation costs distinguished
"""
        elif template.template_id == "commander_suitability":
            commander = random.choice(EXAMPLE_COMMANDERS)
            cmd_colors = set(commander["color_identity"])
            legal1 = set(card1.color_identity).issubset(cmd_colors)
            legal2 = set(card2.color_identity).issubset(cmd_colors)
            template_specific = f"""
COMMANDER SUITABILITY VALIDATION CHECKLIST:
1. Commander: {commander['name']} ({', '.join(commander['color_identity'])})
2. {card1.name} color identity: {card1.color_identity} - Legal: {'YES' if legal1 else 'NO'}
3. {card2.name} color identity: {card2.color_identity} - Legal: {'YES' if legal2 else 'NO'}
4. Commander synergy explained for both cards
5. Color identity rule cited if illegal
"""
        elif template.template_id == "synergy_potential":
            theme = random.choice(SYNERGY_THEMES)
            template_specific = f"""
SYNERGY POTENTIAL VALIDATION CHECKLIST:
1. Theme: {theme}
2. Shared keywords/mechanics identified for both cards
3. Mechanical interaction with theme explained
4. Specific in-game examples given
5. Comparative synergy strength assessed
"""

        return f"""Category: {self.get_source_category()}
Template: {template.template_id}

Cards:
{card1_detail}

{card2_detail}

{template_specific}

VALIDATION REQUIREMENTS:
- Answer must be 3-5 sentences minimum
- No markdown formatting (bold, italics, bullets)
- No rule number references
- Must cite specific card text and statistics
- Context-dependent recommendation (not absolute)
- Minimum 80 characters"""