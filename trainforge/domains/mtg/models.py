"""Pydantic v2 domain models for MTG data with MongoDB field aliases."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator

__all__ = [
    "MongoModel",
    "CardFace",
    "Card",
    "CardWithMetadata",
    "PriceData",
    "Ruling",
    "Legality",
    "CardLegalities",
    "ComboCard",
    "ComboProduces",
    "Combo",
    "ComboWithCards",
    "Commander",
    "CommanderWithTags",
    "Archetype",
    "Article",
    "GuideChapter",
    "Guide",
    "GameState",
    "Rule",
    "GlossaryTerm",
    "Keyword",
]


# =============================================================================
# CONFIG
# =============================================================================


class MongoModel(BaseModel):
    """Base model with MongoDB-friendly config."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    def to_dict(self) -> dict:
        """Return a plain dict (alias for ``model_dump()``)."""
        return self.model_dump(exclude_none=True, by_alias=False)


# =============================================================================
# CARD MODELS
# =============================================================================


class CardFace(MongoModel):
    """Single face of a card (for DFCs, split cards, meld)."""

    name: str
    mana_cost: Optional[str] = Field(default=None, alias="manaCost")
    type_line: str = Field(alias="type")
    oracle_text: str = Field(alias="text")
    power: Optional[str] = None
    toughness: Optional[str] = None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list, alias="colorIdentity")
    keywords: list[str] = Field(default_factory=list)
    loyalty: Optional[str] = None
    defense: Optional[str] = None

    def __repr__(self) -> str:
        return f"CardFace(name={self.name!r}, type_line={self.type_line!r})"


class Card(MongoModel):
    """Core card model matching mtg_json.cards collection."""

    # Core identifiers
    name: str
    uuid: Optional[str] = None
    scryfall_id: Optional[str] = Field(default=None, alias="scryfallId")

    # Card faces (for DFCs, split cards, meld)
    faces: list[CardFace] = Field(default_factory=list)

    # Main face fields (backward compat for non-DFC cards)
    mana_cost: Optional[str] = Field(default=None, alias="manaCost")
    type: Optional[str] = None
    text: Optional[str] = None
    oracle_text: Optional[str] = Field(default=None, alias="oracleText")
    power: Optional[str] = None
    toughness: Optional[str] = None
    loyalty: Optional[str] = None
    defense: Optional[str] = None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list, alias="colorIdentity")
    subtypes: list[str] = Field(default_factory=list)
    supertypes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    # Layout & physical
    layout: Optional[str] = None
    side: Optional[str] = None  # "a", "b" for split cards
    frame: Optional[str] = None
    frame_effects: list[str] = Field(default_factory=list, alias="frameEffects")

    # Rarity (common, uncommon, rare, mythic)
    rarity: Optional[str] = None

    # EDHREC data (embedded in mtg_json.cards)
    edhrec_rank: Optional[int] = Field(default=None, alias="edhrecRank", validate_default=True)
    edhrec_salt: Optional[float] = Field(default=None, alias="edhrecSalt")
    edhrec_tags: list[str] = Field(default_factory=list, alias="edhrecTags")

    # Legalities (embedded)
    legalities: dict[str, str] = Field(default_factory=dict)

    # Prices (joined from cardPrices)
    prices: Optional[PriceData] = None

    # Rulings (joined from cardRulings)
    rulings: list[Ruling] = Field(default_factory=list)

    # Keyword details (joined from keywords)
    keyword_details: list[Keyword] = Field(default_factory=list)

    @field_validator("edhrec_rank", mode="before")
    @classmethod
    def _parse_edhrec_rank(cls, v):
        """Handle empty strings and non-numeric values for edhrecRank."""
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def cmc(self) -> float:
        """Converted mana cost parsed from mana_cost string."""
        if not self.mana_cost:
            return 0.0
        symbols = re.findall(r"\{([^}]+)\}", self.mana_cost)
        cmc = 0.0
        for sym in symbols:
            if sym.isdigit():
                cmc += int(sym)
            elif sym == "X":
                cmc += 0  # Variable
            else:
                cmc += 1  # Colored or hybrid symbol counts as 1
        return cmc

    @property
    def is_commander_legal(self) -> bool:
        """Check if legal in Commander format."""
        return self.legalities.get("commander", "").lower() == "legal"

    @property
    def is_creature(self) -> bool:
        """Check if card is a creature."""
        return "creature" in (self.type or "").lower()

    @property
    def is_legendary(self) -> bool:
        """Check if card has the legendary supertype."""
        return "legendary" in (self.type or "").lower()

    @property
    def primary_face(self) -> CardFace:
        """Get primary face for display (first face or constructed from main fields)."""
        if self.faces:
            return self.faces[0]
        return CardFace(
            name=self.name,
            manaCost=self.mana_cost,
            type=self.type or "",
            text=self.text or "",
            power=self.power,
            toughness=self.toughness,
            loyalty=self.loyalty,
            defense=self.defense,
            colors=self.colors,
            colorIdentity=self.color_identity,
            keywords=self.keywords,
        )

    def color_identity_from_face(self, face: CardFace) -> list[str]:
        """Compute color identity from a specific card face."""
        return face.color_identity or self.color_identity

    # =========================================================================
    # SERIALIZATION FOR LLM PROMPTS
    # =========================================================================

    def to_prompt_detail(
        self, include_prices: bool = True, include_rulings: bool = False
    ) -> str:
        """Format card for LLM context — consistent across all generators."""
        face = self.primary_face
        lines: list[str] = [
            f"Name: {self.name}",
            f"Mana Cost: {face.mana_cost or 'N/A'}",
            f"Type: {face.type_line or self.type or 'N/A'}",
            f"Oracle Text: {face.oracle_text or self.text or 'N/A'}",
        ]
        if face.power and face.toughness:
            lines.append(f"Power/Toughness: {face.power}/{face.toughness}")
        elif face.loyalty:
            lines.append(f"Loyalty: {face.loyalty}")
        if self.color_identity:
            lines.append(f"Color Identity: {', '.join(self.color_identity)}")
        if self.keywords:
            lines.append(f"Keywords: {', '.join(self.keywords)}")
        if self.edhrec_rank is not None:
            lines.append(f"EDHREC Rank: {self.edhrec_rank:,}")
        if self.edhrec_salt is not None:
            lines.append(f"S Salt Score: {self.edhrec_salt:.2f}")
        if self.edhrec_tags:
            lines.append(f"Tags: {', '.join(self.edhrec_tags)}")
        if include_prices and self.prices:
            bp = self.prices.best_price
            lines.append(f"Price: ${bp or 'N/A'} (USD)")
        if include_rulings and self.rulings:
            lines.append(f"Rulings: {len(self.rulings)} available")
        return "\n".join(lines)

    # =========================================================================
    # FACTORY / BACKWARD-COMPAT HELPERS
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict) -> "Card | None":
        """Create a Card from a MongoDB document dict.

        Handles both camelCase (MongoDB) and snake_case keys.
        Returns ``None`` when required fields are missing.
        """
        if not data or "name" not in data or "type" not in data:
            return None

        # Normalise list fields that may be JSON-encoded strings
        def _parse_list(key: str) -> list[str]:
            raw = data.get(key, [])
            if isinstance(raw, str):
                import json as _json

                try:
                    parsed = _json.loads(raw)
                    return parsed if isinstance(parsed, list) else []
                except (ValueError, TypeError):
                    return []
            return raw if isinstance(raw, list) else []

        return cls(
            name=data.get("name", "Unknown"),
            type=data.get("type", "Unknown"),
            mana_cost=data.get("manaCost") or data.get("mana_cost"),
            text=data.get("text", ""),
            subtypes=_parse_list("subtypes"),
            supertypes=_parse_list("supertypes"),
            color_identity=_parse_list("colorIdentity")
            or _parse_list("color_identity"),
        )

    def to_dict(self) -> dict:
        """Return a plain dict (alias for ``model_dump()``).

        Provides backward compatibility with legacy Card.toDict().
        """
        return self.model_dump(exclude_none=True, by_alias=False)

    # Legacy alias — some generators call .toDict() directly
    toDict = to_dict  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"Card(name={self.name!r})"


class CardWithMetadata(Card):
    """Card with all enrichment data populated (prices, rulings, keywords)."""

    # All fields inherited from Card; prices/rulings/keyword_details are populated.
    pass


# =============================================================================
# PRICE MODELS
# =============================================================================


class PriceData(MongoModel):
    """Price data from cardPrices collection."""

    usd: Optional[float] = None
    usd_foil: Optional[float] = Field(default=None, alias="usd_foil")
    eur: Optional[float] = None
    eur_foil: Optional[float] = Field(default=None, alias="eur_foil")
    tix: Optional[float] = None
    paper: Optional[float] = None  # Average paper price
    last_updated: Optional[datetime] = Field(default=None, alias="lastUpdated")

    @property
    def best_price(self) -> Optional[float]:
        """Lowest non-None price across all currencies."""
        prices = [p for p in (self.usd, self.eur, self.paper, self.tix) if p is not None]
        return min(prices) if prices else None

    def is_budget(self, threshold: float = 5.0) -> bool:
        """Check if card is considered budget."""
        return (self.best_price or float("inf")) <= threshold

    def __repr__(self) -> str:
        bp = self.best_price
        return f"PriceData(usd={self.usd}, best={bp})"


# =============================================================================
# RULING MODELS
# =============================================================================


class Ruling(MongoModel):
    """Official or community ruling for a card."""

    uuid: str
    date: datetime
    text: str
    source: Literal["official", "scryfall", "community"] = "official"

    def __repr__(self) -> str:
        return f"Ruling(uuid={self.uuid!r}, date={self.date})"


# =============================================================================
# LEGALITY MODELS
# =============================================================================


class Legality(MongoModel):
    """Single format legality."""

    format: str
    status: Literal["legal", "not_legal", "restricted", "banned"]

    def __repr__(self) -> str:
        return f"Legality(format={self.format!r}, status={self.status!r})"


class CardLegalities(MongoModel):
    """All legalities for a card."""

    card_uuid: str = Field(alias="uuid")
    legalities: list[Legality] = Field(default_factory=list)

    def is_legal_in(self, format_name: str) -> bool:
        """Check if the card is legal in the given format (case-insensitive)."""
        for leg in self.legalities:
            if leg.format.lower() == format_name.lower():
                return leg.status == "legal"
        return False

    def __repr__(self) -> str:
        return f"CardLegalities(uuid={self.card_uuid!r}, formats={len(self.legalities)})"


# =============================================================================
# COMBO MODELS (Commander Spellbook)
# =============================================================================


class ComboCard(MongoModel):
    """Single card in a combo."""

    name: str
    uuid: Optional[str] = None
    quantity: int = 1
    is_commander: bool = Field(default=False, alias="isCommander")
    zone: Literal["battlefield", "hand", "graveyard", "command_zone", "library"] = (
        "battlefield"
    )

    def __repr__(self) -> str:
        return f"ComboCard(name={self.name!r}, qty={self.quantity})"


class ComboProduces(MongoModel):
    """What a combo produces."""

    description: str
    infinite: bool = False
    mana: bool = False
    damage: bool = False
    tokens: bool = False
    draw: bool = False
    mill: bool = False
    life_gain: bool = Field(default=False, alias="lifeGain")
    life_loss: bool = Field(default=False, alias="lifeLoss")

    def __repr__(self) -> str:
        return f"ComboProduces(desc={self.description!r}, infinite={self.infinite})"


class Combo(MongoModel):
    """Combo from commander_spellbook.variants."""

    id: str = Field(alias="_id")
    name: Optional[str] = None
    uses: list[ComboCard] = Field(default_factory=list)
    produces: list[ComboProduces] = Field(default_factory=list)
    description: str = ""
    status: str = "OK"
    tags: list[str] = Field(default_factory=list)
    commanders: list[str] = Field(default_factory=list)

    @property
    def card_names(self) -> list[str]:
        """Names of all cards used in this combo."""
        return [c.name for c in self.uses]

    @property
    def is_infinite(self) -> bool:
        """Whether any produce effect is infinite."""
        return any(p.infinite for p in self.produces)

    @property
    def primary_colors(self) -> list[str]:
        """Placeholder — would need card lookup to resolve colors."""
        return []

    def __repr__(self) -> str:
        return f"Combo(id={self.id!r}, name={self.name!r})"


class ComboWithCards(Combo):
    """Combo with fully enriched card data for each piece."""

    cards: list[CardWithMetadata] = Field(default_factory=list)


# =============================================================================
# COMMANDER MODELS (EDHREC)
# =============================================================================


class Commander(MongoModel):
    """Commander from edhrec.commanders."""

    name: str
    color_identity: list[str] = Field(default_factory=list, alias="colorIdentity")
    tags: list[str] | None = Field(default_factory=list)
    num_decks: int = Field(default=0, alias="numDecks")
    salt: float = 0.0
    avg_deck_rank: Optional[float] = Field(default=None, alias="avgDeckRank")
    card_uuid: Optional[str] = Field(default=None, alias="cardUuid")

    @field_validator("tags", "color_identity", mode="before")
    @classmethod
    def _coerce_none_to_empty_list(cls, v):
        if v is None:
            return []
        return v

    def is_popular(self, threshold: int = 1000) -> bool:
        """Check if commander appears in enough decks to be considered popular."""
        return self.num_decks >= threshold

    @property
    def salt_level(self) -> str:
        """Human-readable salt level based on numeric score."""
        if self.salt >= 2.5:
            return "extreme"
        elif self.salt >= 1.5:
            return "high"
        elif self.salt >= 0.8:
            return "medium"
        return "low"

    def __repr__(self) -> str:
        return f"Commander(name={self.name!r}, decks={self.num_decks})"


class CommanderWithTags(Commander):
    """Commander with enriched card details and computed metrics."""

    card_details: Optional[CardWithMetadata] = None
    inclusion_pct: Optional[float] = None
    salt_score: Optional[float] = None


# =============================================================================
# ARCHETYPE MODELS
# =============================================================================


class Archetype(MongoModel):
    """Deck archetype from mtg_archetypes.archetypes."""

    name: str
    description: str = ""
    color_identities: list[list[str]] = Field(default_factory=list, alias="colorIdentities")
    key_cards: list[str] = Field(default_factory=list, alias="keyCards")
    strategy: str = ""
    win_conditions: list[str] = Field(default_factory=list, alias="winConditions")
    weaknesses: list[str] = Field(default_factory=list)
    budget_options: list[str] = Field(default_factory=list, alias="budgetOptions")

    def __repr__(self) -> str:
        return f"Archetype(name={self.name!r})"


# =============================================================================
# ARTICLE & GUIDE MODELS (EDHREC)
# =============================================================================


class Article(MongoModel):
    """EDHREC article."""

    title: str
    content: str
    excerpt: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    author: Optional[str] = None
    published_date: Optional[datetime] = Field(default=None, alias="publishedDate")
    url: Optional[str] = None

    def __repr__(self) -> str:
        return f"Article(title={self.title!r})"


class GuideChapter(MongoModel):
    """Chapter in an EDHREC guide."""

    title: str
    content: str

    def __repr__(self) -> str:
        return f"GuideChapter(title={self.title!r})"


class Guide(MongoModel):
    """EDHREC guide with chapters."""

    title: str
    chapters: list[GuideChapter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def __repr__(self) -> str:
        return f"Guide(title={self.title!r}, chapters={len(self.chapters)})"


# =============================================================================
# GAME STATE MODEL (for training data)
# =============================================================================


class GameState(MongoModel):
    """Game state for decision-making training data."""

    turn: int
    phase: str
    player_state: dict  # Flexible — life, hand, board, etc.
    decision_point: str
    optimal_action: str

    def __repr__(self) -> str:
        return f"GameState(turn={self.turn}, phase={self.phase!r})"


# =============================================================================
# RULES & KEYWORD MODELS
# =============================================================================


class Rule(MongoModel):
    """MTG Comprehensive Rule."""

    rule_number: str = Field(alias="ruleNumber")
    section: str
    text: str
    category: Optional[str] = None
    subrules: list[Rule] = Field(default_factory=list)

    def __repr__(self) -> str:
        return f"Rule({self.rule_number}: {self.text[:40]}...)"


class GlossaryTerm(MongoModel):
    """MTG Glossary term."""

    term: str
    definition: str
    related_terms: list[str] = Field(default_factory=list, alias="relatedTerms")

    def __repr__(self) -> str:
        return f"GlossaryTerm(term={self.term!r})"


class Keyword(MongoModel):
    """MTG Keyword ability/action."""

    keyword: str
    description: str
    reminder_text: Optional[str] = Field(default=None, alias="reminderText")
    rule_numbers: list[str] = Field(default_factory=list, alias="ruleNumbers")
    is_evergreen: bool = Field(default=False, alias="isEvergreen")
    is_deciduous: bool = Field(default=False, alias="isDeciduous")

    def __repr__(self) -> str:
        return f"Keyword(keyword={self.keyword!r})"


# =============================================================================
# MODEL REBUILD (resolve forward refs)
# =============================================================================

Card.model_rebuild()
Combo.model_rebuild()
Rule.model_rebuild()
