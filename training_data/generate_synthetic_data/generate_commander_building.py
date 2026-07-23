"""Generate Commander-specific deckbuilding Q&A pairs using BaseGenerator.

Enriches prompts with real commanders, key cards, EDHREC articles/guides,
and archetype data (win conditions, weaknesses) from MongoDB.
"""

from dataclasses import dataclass, field
from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    SYSTEM_MESSAGE,
    NEW_LINE,
    build_card_detail,
    clean_html,
)
from .data_access import MTGDataAccess
from .domain_models import Article, CommanderWithTags, Guide, CardWithMetadata
from .models import Model, ModelType, ValidationMetrics
from .logger import print


# =============================================================================
# VALIDATION RULES PER TEMPLATE
# =============================================================================

COMMANDER_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide Commander-specific deckbuilding advice — generic advice that applies to any format is a validation failure.
2. Answer does not reference at least one specific card or commander from the provided context.
3. Answer contains markdown formatting (bold, italics, bullet points).
4. Answer references rule numbers directly — mechanics must be explained conversationally.
5. Answer is less than 80 characters.
6. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer provides specific advice for building the given Commander archetype.
2. The answer references real cards or commanders from the provided context.
3. The answer addresses Commander-specific challenges (100-card singleton, multiplayer dynamics, commander tax, etc.).
4. At least one question comes from a practical deckbuilding perspective (e.g., "How do I build around...?" or "What's the right approach to...?").
"""

COMMANDER_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete card example relevant to the archetype.
2. Answer references a card that does not exist or describes its abilities incorrectly.
3. Answer contains markdown formatting (bold, italics, bullet points).
4. Answer references rule numbers directly — mechanics must be explained conversationally.
5. Answer is less than 80 characters.
6. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one specific card example from the provided <key_cards> or <commanders>.
2. The card's abilities are described accurately (cross-reference oracle text from context).
3. The answer explains WHY that card fits the archetype in Commander specifically.
"""


# =============================================================================
# DATA BATCH
# =============================================================================

@dataclass
class CommanderBuildingBatch:
    """Rich data batch for commander building prompt generation."""
    archetype_name: str
    archetype_description: str
    example_commanders: list[CommanderWithTags] = field(default_factory=list)
    key_cards: list[CardWithMetadata] = field(default_factory=list)
    win_conditions: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    relevant_articles: list[Article] = field(default_factory=list)
    relevant_guides: list[Guide] = field(default_factory=list)


# =============================================================================
# ARCHETYPE → DATA MAPPINGS
# =============================================================================

# Maps archetype names to oracle text keywords for commander matching
# (Commander DB tags are too generic: 'ramp', 'draw', 'recursion', etc.)
ARCHETYPE_KEYWORD_MAP: dict[str, list[str]] = {
    "sacrifice/aristocrats": ["sacrifice", "dies", "whenever a creature dies", "sacrifice a creature"],
    "spellslinger/magecraft": ["instant", "sorcery", "magecraft", "prowess", "whenever you cast"],
    "token swarm": ["create", "token", "creature token", "create a"],
    "reanimator": ["graveyard", "return", "from your graveyard", "put onto the battlefield"],
    "combo": ["whenever", "untap", "infinite", "whenever you"],
    "control": ["counter", "return", "exile", "draw a card"],
    "voltron": ["equipment", "aura", "equipped", "enchant", "equipped creature"],
    "stax/prison": ["tap", "can't", "don't", "whenever", "skip"],
    "landfall/lands matter": ["land", "landfall", "whenever a land", "additional lands"],
    "graveyard value": ["graveyard", "flashback", "delve", "dredge", "escape"],
    "turbo draw/card advantage": ["draw a card", "draw two", "draw three", "whenever you draw"],
    "midrange goodstuff": [],  # Fallback: include all commanders
}

# Maps archetype names to likely DB archetype collection names
ARCHETYPE_DB_MAP: dict[str, str] = {
    "sacrifice/aristocrats": "Aristocrats",
    "spellslinger/magecraft": "Spellslinger",
    "token swarm": "Tokens",
    "reanimator": "Reanimator",
    "combo": "Combo",
    "control": "Control",
    "voltron": "Voltron",
    "stax/prison": "Stax",
    "landfall/lands matter": "Landfall",
    "graveyard value": "Graveyard",
    "turbo draw/card advantage": "Card Draw",
    "midrange goodstuff": "Midrange",
}

# Fallback key cards per archetype when DB has no match
ARCHETYPE_KEY_CARDS: dict[str, list[str]] = {
    "sacrifice/aristocrats": [
        "Blood Artist", "Zulaport Cutthroat", "Viscera Seer", "Phyrexian Altar",
        "Ashnod's Altar", "Grave Pact", "Dictate of Erebos", "Skrelv's Hive",
    ],
    "spellslinger/magecraft": [
        "Guttersnipe", "Archmage Emeritus", "Storm-Kiln Artist", "Ral, Storm Conduit",
        "Thousand-Year Storm", "Manamorphose", "Desperate Ritual", "Pyretic Ritual",
    ],
    "token swarm": [
        "Annointed Procession", "Doubling Season", "Parallel Lives", "Beastmaster Ascension",
        "Cathars' Crusade", "Secure the Wastes", "Martial Coup", "Finale of Glory",
    ],
    "reanimator": [
        "Animate Dead", "Dance of the Dead", "Necromancy", "Reanimate",
        "Entomb", "Buried Alive", "Victimize", "Living Death",
    ],
    "combo": [
        "Thassa's Oracle", "Demonic Consultation", "Isochron Scepter", "Dramatic Reversal",
        "Scepter of Domination", "Basalt Monolith", "Rings of Brighthearth", "Staff of Domination",
    ],
    "control": [
        "Cyclonic Rift", "Farewell", "Toxic Deluge", "Rhystic Study",
        "Mystic Remora", "Smothering Tithe", "Blind Obedience", "Ghostly Prison",
    ],
    "voltron": [
        "Lightning Greaves", "Swiftfoot Boots", "Sword of the Animist", "Puresteel Paladin",
        "Stoneforge Mystic", "Open the Armory", "Sigarda's Aid", "Blackblade Reforged",
    ],
    "stax/prison": [
        "Winter Orb", "Static Orb", "Smokestack", "Tangle Wire",
        "Drannith Magistrate", "Aven Mindcensor", "Hushbringer", "Rule of Law",
    ],
    "landfall/lands matter": [
        "Azusa, Lost but Seeking", "Courser of Kruphix", "Ramunap Excavator",
        "Splendid Reclamation", "Scute Swarm", "Rampaging Baloths", "Avenger of Zendikar",
        "Stone-Seeder Hierophant",
    ],
    "graveyard value": [
        "Underworld Breach", "Dredge", "Life from the Loam", "Deep Analysis",
        "Mystic Sanctuary", "Snapcaster Mage", "Tasigur, the Golden Fang", "Gurmag Angler",
    ],
    "turbo draw/card advantage": [
        "Rhystic Study", "Mystic Remora", "Sylvan Library", "Necropotence",
        "Phyrexian Arena", "Dark Confidant", "The One Ring", "Black Market Connections",
    ],
    "midrange goodstuff": [
        "Sol Ring", "Command Tower", "Arcane Signet", "Swords to Plowshares",
        "Beast Within", "Chaos Warp", "Cyclonic Rift", "Farewell",
    ],
}


# =============================================================================
# GENERATOR CLASS
# =============================================================================

class GenerateCommanderBuilding(BaseGenerator[CommanderBuildingBatch]):
    """Generate Commander-specific deckbuilding Q&A with enriched card data."""

    TEMPLATES = [
        TemplateConfig(
            template_id="general_advice",
            task_instruction="""You are an expert Commander deckbuilder. Generate exactly 3 Q&A pairs about building a {archetype} Commander deck.

Use the provided commanders, key cards, and strategy context to give specific, grounded advice.
Reference actual card names from the <key_cards> and <commanders> blocks.
Explain WHY specific cards fit this archetype in Commander.

Questions should be specific to Commander format construction challenges.
Cover topics like: choosing a commander, building around themes, threat density, political considerations, power level calibration.
Answers must address Commander-specific constraints (100-card singleton, multiplayer dynamics).
Do NOT invent cards that are not in the provided context.

Output JSON array with question/answer pairs. Keep answers 3-6 sentences with Commander-specific advice and reasoning.
{output_format}""",
            validation_rules=COMMANDER_GENERAL_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
        TemplateConfig(
            template_id="example_driven",
            task_instruction="""You are an expert Commander deckbuilder. Generate exactly 3 Q&A pairs about building a {archetype} Commander deck using concrete card examples.

Use the provided commanders, key cards, and strategy context. Each answer MUST include at least one specific card or commander from the <key_cards> or <commanders> blocks.
Explain WHY that card is a good fit for this strategy in Commander specifically.
Do NOT invent cards that are not in the provided context.

Output JSON array with question/answer pairs. Keep answers 3-6 sentences with Commander-specific advice and reasoning.
{output_format}""",
            validation_rules=COMMANDER_EXAMPLE_VALIDATION.strip().split("\n"),
            weight=1.0,
        ),
    ]

    # All archetypes preserved from the original generator
    ARCHETYPES = [
        (
            "sacrifice/aristocrats",
            "Decks that sacrifice creatures for value, using Blood Artist-style effects, sac outlets, and token generators. Key challenge: balancing fodder, payoffs, and sac outlets.",
        ),
        (
            "spellslinger/magecraft",
            "Decks that cast lots of instants and sorceries, using magecraft triggers, prowess, and spell-based win conditions. Key challenge: protecting your win condition while staying low to the ground.",
        ),
        (
            "token swarm",
            "Decks that generate many creature tokens and win through wide attacks or combo. Key challenge: having enough anthems and ways to win through chump blockers.",
        ),
        (
            "reanimator",
            "Decks that put big creatures in the graveyard and reanimate them cheaply. Key challenge: filling the graveyard, protecting the reanimation target, winning with the reanimated creature.",
        ),
        (
            "combo",
            "Decks that assemble a specific combination of cards to win instantly or lock opponents out. Key challenge: finding the combo pieces, protecting the combo, having backup win conditions.",
        ),
        (
            "control",
            "Decks that answer every threat and win through superior card advantage in the late game. Key challenge: staying relevant in multiplayer, having a win condition that can close through disruption.",
        ),
        (
            "voltron",
            "Decks that buff one creature (usually the commander) with equipment and auras to win through commander damage. Key challenge: protecting your commander, rebuilding after removal, winning through 21 combat damage.",
        ),
        (
            "stax/prison",
            "Decks that use symmetrical or asymmetrical effects to slow opponents while you advance your own game plan. Key challenge: calibrating the lock pieces so you can still win, not making the game unfun.",
        ),
        (
            "landfall/lands matter",
            "Decks that trigger off lands entering the battlefield, using extra land effects and landfall payoffs. Key challenge: getting enough lands into play per turn, balancing consistency with power.",
        ),
        (
            "graveyard value",
            "Decks that use the graveyard as a resource without necessarily being reanimator — flashback, delve, threshold, cycling. Key challenge: filling the graveyard efficiently, playing around graveyard hate.",
        ),
        (
            "turbo draw/card advantage",
            "Decks built around drawing as many cards as possible to find combo pieces or assemble overwhelming card advantage. Key challenge: using the cards drawn effectively, not decking yourself.",
        ),
        (
            "midrange goodstuff",
            "Decks that play powerful cards at every part of the curve without a focused synergy strategy. Key challenge: distinguishing this from a tuned synergy deck, knowing when to choose goodstuff over theme.",
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 3000,
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
            generator_name="GenerateCommanderBuilding",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
            **kwargs,
        )
        self.data_access = data_access
        self._commander_cache: dict[str, list[CommanderWithTags]] = {}
        self._key_card_cache: dict[str, list[CardWithMetadata]] = {}
        self._articles: list[Article] = []
        self._guides: list[Guide] = []
        self._archetypes_db: dict[str, object] = {}

    # =========================================================================
    # DATA FETCHING
    # =========================================================================

    def _ensure_data_loaded(self) -> None:
        """Lazily load all shared data on first call."""
        if self._commander_cache:
            return

        print("  → Fetching commanders from EDHREC...")
        all_commanders = self.data_access.get_commanders_enriched(limit=2000)
        print(f"    Fetched {len(all_commanders)} commanders")

        # Index commanders by their tags
        for cmd in all_commanders:
            for tag in (cmd.tags or []):
                self._commander_cache.setdefault(tag, []).append(cmd)

        print("  → Fetching archetype data...")
        archetypes = self.data_access.get_archetype_data()
        self._archetypes_db = {a.name: a for a in archetypes}
        print(f"    Fetched {len(archetypes)} archetypes from DB")

        print("  → Fetching EDHREC articles...")
        self._articles = self.data_access.get_articles(limit=200)
        print(f"    Fetched {len(self._articles)} articles")

        print("  → Fetching EDHREC guides...")
        self._guides = self.data_access.get_guides(limit=200)
        print(f"    Fetched {len(self._guides)} guides")

    def _fetch_commanders_for_archetype(self, archetype_name: str) -> list[CommanderWithTags]:
        """Get top commanders matching this archetype by oracle text keywords."""
        keywords = ARCHETYPE_KEYWORD_MAP.get(archetype_name, [])
        if not keywords:
            # Fallback: return most popular commanders overall
            all_cmd = []
            for cmds in self._commander_cache.values():
                all_cmd.extend(cmds)
            seen = set()
            unique = []
            for cmd in all_cmd:
                if cmd.name not in seen:
                    seen.add(cmd.name)
                    unique.append(cmd)
            unique.sort(key=lambda c: c.num_decks, reverse=True)
            return unique[:5]

        scored: list[tuple[int, CommanderWithTags]] = []
        for cmds in self._commander_cache.values():
            for cmd in cmds:
                oracle = ""
                if cmd.card_details:
                    oracle = getattr(cmd.card_details, "text", "") or ""
                oracle_lower = oracle.lower()
                matches = sum(1 for kw in keywords if kw.lower() in oracle_lower)
                if matches > 0:
                    scored.append((matches, cmd))
        # Deduplicate, sort by keyword matches then popularity
        seen: set[str] = set()
        unique_scored: list[tuple[int, CommanderWithTags]] = []
        for matches, cmd in scored:
            if cmd.name not in seen:
                seen.add(cmd.name)
                unique_scored.append((matches, cmd))
        unique_scored.sort(key=lambda x: (x[0], x[1].num_decks), reverse=True)
        return [cmd for _, cmd in unique_scored[:5]]

    def _fetch_key_cards_for_archetype(self, archetype_name: str) -> list[CardWithMetadata]:
        """Get key cards from DB archetype data or fallback to curated list."""
        cache_key = archetype_name
        if cache_key in self._key_card_cache:
            return self._key_card_cache[cache_key]

        card_names: list[str] = []

        # Try DB archetype first
        db_name = ARCHETYPE_DB_MAP.get(archetype_name)
        if db_name and db_name in self._archetypes_db:
            archetype = self._archetypes_db[db_name]
            card_names = list(getattr(archetype, "key_cards", []) or [])

        # Fallback to curated list
        if not card_names:
            card_names = ARCHETYPE_KEY_CARDS.get(archetype_name, [])

        if not card_names:
            return []

        # Look up enriched cards (deduplicate by name — DB has multiple printings)
        cards = self.data_access.get_cards_enriched(
            filters={"name": {"$in": card_names}},
            limit=len(card_names) * 3,
            lite=True,
        )
        seen_names: set[str] = set()
        unique_cards: list[CardWithMetadata] = []
        for card in cards:
            if card.name not in seen_names:
                seen_names.add(card.name)
                unique_cards.append(card)
        self._key_card_cache[cache_key] = unique_cards
        return unique_cards

    def _fetch_archetype_details(self, archetype_name: str) -> tuple[list[str], list[str]]:
        """Get win conditions and weaknesses from DB archetype data."""
        db_name = ARCHETYPE_DB_MAP.get(archetype_name)
        if db_name and db_name in self._archetypes_db:
            archetype = self._archetypes_db[db_name]
            return (
                list(getattr(archetype, "win_conditions", []) or []),
                list(getattr(archetype, "weaknesses", []) or []),
            )
        return ([], [])

    def _fetch_articles_for_archetype(self, archetype_name: str) -> list[Article]:
        """Get EDHREC articles relevant to this archetype."""
        keywords = ARCHETYPE_KEYWORD_MAP.get(archetype_name, [])
        if not keywords:
            return []
        kw_set = {kw.lower() for kw in keywords}
        scored = []
        for article in self._articles:
            article_text = f"{article.title} {' '.join(article.tags or [])}".lower()
            overlap = sum(1 for kw in kw_set if kw in article_text)
            if overlap > 0:
                scored.append((overlap, article))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:2]]

    def _fetch_guides_for_archetype(self, archetype_name: str) -> list[Guide]:
        """Get EDHREC guides relevant to this archetype."""
        keywords = ARCHETYPE_KEYWORD_MAP.get(archetype_name, [])
        if not keywords:
            return []
        kw_set = {kw.lower() for kw in keywords}
        scored = []
        for guide in self._guides:
            guide_text = f"{guide.title} {' '.join(guide.tags or [])}".lower()
            overlap = sum(1 for kw in kw_set if kw in guide_text)
            if overlap > 0:
                scored.append((overlap, guide))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [g for _, g in scored[:2]]

    # =========================================================================
    # BASE GENERATOR OVERRIDES
    # =========================================================================

    def get_data_batches(self) -> Iterator[CommanderBuildingBatch]:
        """Yield enriched data batches for each archetype."""
        self._ensure_data_loaded()

        while True:
            for archetype_name, archetype_desc in self.ARCHETYPES:
                if self.generated_count >= self.target_count:
                    return

                commanders = self._fetch_commanders_for_archetype(archetype_name)
                key_cards = self._fetch_key_cards_for_archetype(archetype_name)
                win_conditions, weaknesses = self._fetch_archetype_details(archetype_name)
                articles = self._fetch_articles_for_archetype(archetype_name)
                guides = self._fetch_guides_for_archetype(archetype_name)

                yield CommanderBuildingBatch(
                    archetype_name=archetype_name,
                    archetype_description=archetype_desc,
                    example_commanders=commanders,
                    key_cards=key_cards,
                    win_conditions=win_conditions,
                    weaknesses=weaknesses,
                    relevant_articles=articles,
                    relevant_guides=guides,
                )

    def build_prompt(self, template: TemplateConfig, data_batch: CommanderBuildingBatch) -> str:
        """Build enriched LLM prompt with commanders, key cards, articles, and guides."""
        batch = data_batch

        # Format commanders
        commander_blocks = []
        for i, cmd in enumerate(batch.example_commanders):
            cd = cmd.card_details
            if cd:
                commander_blocks.append(
                    f"{i+1}. {cmd.name} ({cmd.num_decks:,} decks, tags: {', '.join(cmd.tags or [])})"
                    f"\n   Mana Cost: {getattr(cd, 'mana_cost', 'N/A')}"
                    f"\n   Type: {getattr(cd, 'type', 'N/A')}"
                    f"\n   Text: {getattr(cd, 'text', 'N/A')}"
                    f"\n   Color Identity: {', '.join(cmd.color_identity)}"
                )
            else:
                commander_blocks.append(
                    f"{i+1}. {cmd.name} ({cmd.num_decks:,} decks, tags: {', '.join(cmd.tags or [])})"
                    f"\n   Color Identity: {', '.join(cmd.color_identity)}"
                )
        commanders_xml = NEW_LINE.join(commander_blocks) if commander_blocks else "No matching commanders found."

        # Format key cards
        card_blocks = []
        for i, card in enumerate(batch.key_cards):
            card_blocks.append(build_card_detail(card_number=i+1, card=card))
        key_cards_xml = NEW_LINE.join(card_blocks) if card_blocks else "No key cards available."

        # Format articles
        article_blocks = []
        for article in batch.relevant_articles:
            content = clean_html(article.content or "")[:500]
            article_blocks.append(f'"{article.title}" — {content}')
        articles_xml = NEW_LINE.join(article_blocks) if article_blocks else "No relevant articles found."

        # Format guides
        guide_blocks = []
        for guide in batch.relevant_guides:
            chapter_summaries = []
            for ch in (guide.chapters or [])[:3]:
                chapter_summaries.append(f'  Chapter "{ch.title}": {clean_html(ch.content or "")[:200]}')
            guide_blocks.append(f'"{guide.title}"' + NEW_LINE + NEW_LINE.join(chapter_summaries))
        guides_xml = NEW_LINE.join(guide_blocks) if guide_blocks else "No relevant guides found."

        # Format win conditions and weaknesses
        wc_text = "; ".join(batch.win_conditions) if batch.win_conditions else "Not specified"
        weakness_text = "; ".join(batch.weaknesses) if batch.weaknesses else "Not specified"

        task_instruction = template.task_instruction.format(
            archetype=batch.archetype_name,
            output_format=OUTPUT_FORMAT.strip(),
        )

        prompt = f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<commanders>
{commanders_xml}
</commanders>

<key_cards>
{key_cards_xml}
</key_cards>

<archetype>
Name: {batch.archetype_name}
Description: {batch.archetype_description}
Win Conditions: {wc_text}
Weaknesses: {weakness_text}
</archetype>

<strategy_articles>
{articles_xml}
</strategy_articles>

<strategy_guides>
{guides_xml}
</strategy_guides>

<task>
{task_instruction}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "commander_building"

    def get_source_data(self, data_batch: CommanderBuildingBatch) -> list:
        """Extract source data references for the generated document."""
        sources = []
        for cmd in data_batch.example_commanders:
            sources.append({"name": cmd.name, "num_decks": cmd.num_decks, "tags": cmd.tags})
        for card in data_batch.key_cards:
            sources.append({"name": card.name, "edhrec_rank": card.edhrec_rank})
        for article in data_batch.relevant_articles:
            sources.append({"title": article.title, "url": article.url})
        for guide in data_batch.relevant_guides:
            sources.append({"title": guide.title})
        return sources

    def build_context(self, template: TemplateConfig, data_batch: CommanderBuildingBatch) -> str:
        """Build validation context with commander and card details."""
        batch = data_batch

        commander_context = NEW_LINE.join(
            f"  {cmd.name}: {getattr(cmd.card_details, 'text', 'N/A') if cmd.card_details else 'N/A'} (decks: {cmd.num_decks})"
            for cmd in batch.example_commanders
        ) or "  None"

        card_context = NEW_LINE.join(
            f"  {card.name}: {card.primary_face.oracle_text[:150] if card.primary_face else 'N/A'}"
            for card in batch.key_cards
            if card.primary_face and card.primary_face.oracle_text
        ) or "  None"

        return f"""Category: {self.get_source_category()}
Template: {template.template_id}

Archetype: {batch.archetype_name}
Description: {batch.archetype_description}

Commanders (reference these for accuracy):
{commander_context}

Key Cards (reference these for accuracy):
{card_context}

Win Conditions: {'; '.join(batch.win_conditions) if batch.win_conditions else 'Not specified'}
Weaknesses: {'; '.join(batch.weaknesses) if batch.weaknesses else 'Not specified'}"""
