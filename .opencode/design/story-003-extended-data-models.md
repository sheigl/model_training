# Design: Extended Data Models (Story 003)

## Overview
Create comprehensive Pydantic v2 models in `training_data/generate_synthetic_data/domain_models.py` for all MTG domain objects. These models replace the minimal `Card` class in `models.py` and provide rich, typed data structures with MongoDB field aliases, computed properties, and serialization helpers for LLM prompt building.

## User Story Reference
`.opencode/discovery/story-003-extended-data-models.md`

---

## Architecture Decisions

### 1. Pydantic v2 with `ConfigDict` and Field Aliases
**Decision**: Use Pydantic v2 (`BaseModel`, `Field`, `ConfigDict`) with `populate_by_name=True` and MongoDB field aliases (camelCase).
**Why**: 
- MongoDB stores fields as camelCase (`colorIdentity`, `edhrecRank`, `manaCost`)
- Pydantic v2 aliases enable seamless deserialization from MongoDB dicts
- `extra="ignore"` handles extra fields gracefully
**Trade-offs**:
- ✅ Direct `Model(**mongo_doc)` works without manual field mapping
- ✅ IDE autocomplete for both snake_case (Python) and camelCase (MongoDB)
- ⚠️ Must maintain alias sync with MongoDB schema

### 2. Composed Models with Forward References
**Decision**: Use composition (`CardWithMetadata` contains `PriceData`, `list[Ruling]`, etc.) with string annotations for circular refs.
**Why**: 
- Rich domain objects need nested data (card + prices + rulings + legalities)
- Forward references (`"PriceData"`) resolve circular imports
**Trade-offs**:
- ✅ Clean object graph, type-safe navigation
- ⚠️ `model_rebuild()` needed after all models defined

### 3. Computed Properties for Derived Data
**Decision**: Use `@property` for CMC, color identity, commander legality, creature check, etc.
**Why**: 
- Derived data shouldn't be stored; computed from source fields
- Consistent logic across all generators
- Usable in prompt templates (`card.cmc`, `card.is_commander_legal`)
**Trade-offs**:
- ✅ Single source of truth, no stale computed fields
- ⚠️ Not serialized by default (use `to_prompt_detail()` for LLM context)

### 4. Serialization Helpers for LLM Prompts
**Decision**: `to_prompt_detail()` method on each model produces consistent, readable text for LLM context.
**Why**: 
- Current `build_card_detail()` in `common.py` is duplicated/inconsistent
- Centralized formatting ensures all generators provide same quality context
- Easy to update format globally
**Trade-offs**:
- ✅ Consistent LLM context, single point of change
- ⚠️ Must keep in sync with model fields

### 5. Minimal Required Fields (All Optional Except Identifiers)
**Decision**: Only `name`/`uuid` required; all other fields `Optional` with defaults.
**Why**: 
- MongoDB documents vary (some cards lack prices, rulings, EDHREC data)
- Generators must handle partial data gracefully
**Trade-offs**:
- ✅ Robust to missing data
- ⚠️ Callers must check `None` before accessing

---

## Files to Create/Modify

### New Files
| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `training_data/generate_synthetic_data/domain_models.py` | All Pydantic domain models | Card, Combo, Commander, Ruling, Price, Legalities, Archetype, GameState, Article, Guide, Keyword, Rule, GlossaryTerm models |

### Modified Files
| File | Changes | Reason |
|------|---------|--------|
| `training_data/generate_synthetic_data/models.py` | Deprecate `Card`, `ProjectedCombo`, `Requirement`; import from `domain_models` | Single source of truth for domain models |
| `training_data/generate_synthetic_data/common.py` | Replace `build_card_detail()` with `card.to_prompt_detail()` | Use model's serialization |
| `training_data/generate_synthetic_data/data_access.py` | (Story 2) Return typed models from this file | Data access layer consumes these models |
| `training_data/generate_synthetic_data/base_generator.py` | (Story 1) Type hints use domain models | Generators work with rich typed objects |

---

## Task Breakdown (Ordered by Dependency)

### Task 1: Core Card Models (`CardFace`, `Card`, `CardWithMetadata`)
- **Files**: `domain_models.py`
- **Description**: Base card models with all MTG JSON fields, EDHREC data, and enrichment fields
- **Acceptance Criteria**:
  - `CardFace` for DFC/split card faces with aliases (`manaCost`, `type`, `text`, `colorIdentity`)
  - `Card` with all core fields, EDHREC fields (`edhrecRank`, `edhrecSalt`, `edhrecTags`), legalities dict
  - `CardWithMetadata` extends `Card` with `prices: PriceData | None`, `rulings: list[Ruling]`, `keyword_details: list[Keyword]`
  - Computed properties: `cmc`, `is_commander_legal`, `is_creature`, `primary_face`, `color_identity_from_face()`
  - `to_prompt_detail()` returns formatted string for LLM context
  - `model_config = ConfigDict(populate_by_name=True, extra="ignore", arbitrary_types_allowed=True)`

### Task 2: Price, Ruling, Legality Models
- **Files**: `domain_models.py`
- **Description**: Supporting models for card enrichment
- **Acceptance Criteria**:
  - `PriceData`: `usd`, `usd_foil`, `eur`, `eur_foil`, `tix`, `paper`, `last_updated` with aliases; `best_price` and `is_budget(threshold)` properties
  - `Ruling`: `uuid`, `date`, `text`, `source` (official/scryfall/community)
  - `Legality`: `format`, `status` (legal/not_legal/restricted/banned)
  - `CardLegalities`: `card_uuid`, `legalities: list[Legality]`; `is_legal_in(format)` method

### Task 3: Combo Models (`ComboCard`, `ComboProduces`, `Combo`, `ComboWithCards`)
- **Files**: `domain_models.py`
- **Description**: Commander Spellbook combo models with full card enrichment
- **Acceptance Criteria**:
  - `ComboCard`: `name`, `uuid`, `quantity`, `is_commander`, `zone` (battlefield/hand/graveyard/command_zone/library)
  - `ComboProduces`: `description`, `infinite`, `mana`, `damage`, `tokens`, `draw`, `mill`, `life_gain`, `life_loss`
  - `Combo`: `id` (alias `_id`), `name`, `uses: list[ComboCard]`, `produces: list[ComboProduces]`, `description`, `status`, `tags`, `commanders`
  - Properties: `card_names`, `is_infinite`, `primary_colors`
  - `ComboWithCards`: extends `Combo` with `cards: list[CardWithMetadata]` for each piece

### Task 4: Commander & EDHREC Models (`Commander`, `CommanderWithTags`)
- **Files**: `domain_models.py`
- **Description**: EDHREC commander data with tags and metadata
- **Acceptance Criteria**:
  - `Commander`: `name`, `color_identity`, `tags`, `num_decks`, `salt`, `avg_deck_rank`, `card_uuid`
  - Properties: `is_popular(threshold)`, `salt_level` (low/medium/high/extreme)
  - `CommanderWithTags`: extends `Commander` with `card_details: CardWithMetadata | None`, `inclusion_pct`, `salt_score`

### Task 5: Archetype, Article, Guide, GameState Models
- **Files**: `domain_models.py`
- **Description**: Strategy/content models for deckbuilding and training data
- **Acceptance Criteria**:
  - `Archetype`: `name`, `description`, `color_identities`, `key_cards`, `strategy`, `win_conditions`, `weaknesses`, `budget_options`
  - `Article`: `title`, `content`, `excerpt`, `tags`, `author`, `published_date`, `url`
  - `GuideChapter`: `title`, `content`
  - `Guide`: `title`, `chapters: list[GuideChapter]`, `tags`
  - `GameState`: `turn`, `phase`, `player_state`, `decision_point`, `optimal_action`

### Task 6: Rules & Keyword Models (`Rule`, `GlossaryTerm`, `Keyword`)
- **Files**: `domain_models.py`
- **Description**: MTG Comprehensive Rules and keyword models
- **Acceptance Criteria**:
  - `Rule`: `rule_number`, `section`, `text`, `category`, `subrules: list[Rule]` (recursive)
  - `GlossaryTerm`: `term`, `definition`, `related_terms`
  - `Keyword`: `keyword`, `description`, `reminder_text`, `rule_numbers`, `is_evergreen`, `is_deciduous`

### Task 7: Integration & Migration
- **Files**: `models.py`, `common.py`, `data_access.py`, `base_generator.py`
- **Description**: Update imports, replace old models, update prompt builders
- **Acceptance Criteria**:
  - `models.py` imports and re-exports from `domain_models` (backward compat)
  - `common.py` `build_card_detail()` delegates to `card.to_prompt_detail()`
  - `data_access.py` methods return typed domain models
  - `base_generator.py` type hints use domain models
  - All generators work without modification (backward compatible)

---

## Data Models / Interfaces

### Complete Model Definitions

```python
# domain_models.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, computed_field
from bson import ObjectId

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
    
    # EDHREC data (embedded in mtg_json.cards)
    edhrec_rank: Optional[int] = Field(default=None, alias="edhrecRank")
    edhrec_salt: Optional[float] = Field(default=None, alias="edhrecSalt")
    edhrec_tags: list[str] = Field(default_factory=list, alias="edhrecTags")
    
    # Legalities (embedded)
    legalities: dict[str, str] = Field(default_factory=dict)
    
    # Prices (joined from cardPrices)
    prices: Optional["PriceData"] = None
    
    # Rulings (joined from cardRulings)
    rulings: list["Ruling"] = Field(default_factory=list)
    
    # Keyword details (joined from keywords)
    keyword_details: list["Keyword"] = Field(default_factory=list)
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @property
    def cmc(self) -> float:
        """Converted mana cost from mana_cost."""
        if not self.mana_cost:
            return 0.0
        # Parse {X}{W}{U} etc. - simplified
        import re
        symbols = re.findall(r'\{([^}]+)\}', self.mana_cost)
        cmc = 0.0
        for sym in symbols:
            if sym.isdigit():
                cmc += int(sym)
            elif sym == 'X':
                cmc += 0  # Variable
            else:
                cmc += 1  # Colored symbol
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
            colors=self.colors,
            colorIdentity=self.color_identity,
            keywords=self.keywords,
        )
    
    def color_identity_from_face(self, face: CardFace) -> list[str]:
        """Compute color identity from a face (mana symbols + color indicator)."""
        # Simplified - real implementation parses mana_cost and color_indicator
        return face.color_identity or self.color_identity
    
    # =========================================================================
    # SERIALIZATION FOR LLM PROMPTS
    # =========================================================================
    
    def to_prompt_detail(self, include_prices: bool = True, include_rulings: bool = False) -> str:
        """Format card for LLM context - consistent across all generators."""
        face = self.primary_face
        lines = [
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
        if self.edhrec_rank:
            lines.append(f"EDHREC Rank: {self.edhrec_rank:,}")
        if self.edhrec_salt is not None:
            lines.append(f"Salt Score: {self.edhrec_salt:.2f}")
        if self.edhrec_tags:
            lines.append(f"Tags: {', '.join(self.edhrec_tags)}")
        if include_prices and self.prices:
            lines.append(f"Price: ${self.prices.best_price or 'N/A'} (USD)")
        if include_rulings and self.rulings:
            lines.append(f"Rulings: {len(self.rulings)} available")
        return "\n".join(lines)

class CardWithMetadata(Card):
    """Card with all enrichment data populated (prices, rulings, keywords)."""
    # All fields inherited from Card; prices/rulings/keyword_details are populated
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
        prices = [p for p in [self.usd, self.eur, self.paper, self.tix] if p is not None]
        return min(prices) if prices else None
    
    def is_budget(self, threshold: float = 5.0) -> bool:
        """Check if card is considered budget."""
        return (self.best_price or float('inf')) <= threshold

# =============================================================================
# RULING MODELS
# =============================================================================

class Ruling(MongoModel):
    """Official or community ruling for a card."""
    uuid: str
    date: datetime
    text: str
    source: Literal["official", "scryfall", "community"] = "official"

# =============================================================================
# LEGALITY MODELS
# =============================================================================

class Legality(MongoModel):
    """Single format legality."""
    format: str
    status: Literal["legal", "not_legal", "restricted", "banned"]

class CardLegalities(MongoModel):
    """All legalities for a card."""
    card_uuid: str = Field(alias="uuid")
    legalities: list[Legality] = Field(default_factory=list)
    
    def is_legal_in(self, format_name: str) -> bool:
        for leg in self.legalities:
            if leg.format.lower() == format_name.lower():
                return leg.status == "legal"
        return False

# =============================================================================
# COMBO MODELS (Commander Spellbook)
# =============================================================================

class ComboCard(MongoModel):
    """Single card in a combo."""
    name: str
    uuid: Optional[str] = None
    quantity: int = 1
    is_commander: bool = Field(default=False, alias="isCommander")
    zone: Literal["battlefield", "hand", "graveyard", "command_zone", "library"] = "battlefield"

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
        return [c.name for c in self.uses]
    
    @property
    def is_infinite(self) -> bool:
        return any(p.infinite for p in self.produces)
    
    @property
    def primary_colors(self) -> list[str]:
        # Would need card lookup - placeholder
        return []

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
    tags: list[str] = Field(default_factory=list)
    num_decks: int = Field(default=0, alias="numDecks")
    salt: float = 0.0
    avg_deck_rank: Optional[float] = Field(default=None, alias="avgDeckRank")
    card_uuid: Optional[str] = Field(default=None, alias="cardUuid")
    
    def is_popular(self, threshold: int = 1000) -> bool:
        return self.num_decks >= threshold
    
    @property
    def salt_level(self) -> str:
        if self.salt >= 2.5:
            return "extreme"
        elif self.salt >= 1.5:
            return "high"
        elif self.salt >= 0.8:
            return "medium"
        return "low"

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

class GuideChapter(MongoModel):
    """Chapter in an EDHREC guide."""
    title: str
    content: str

class Guide(MongoModel):
    """EDHREC guide with chapters."""
    title: str
    chapters: list[GuideChapter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

# =============================================================================
# GAME STATE MODEL (for training data)
# =============================================================================

class GameState(MongoModel):
    """Game state for decision-making training data."""
    turn: int
    phase: str
    player_state: dict  # Flexible - life, hand, board, etc.
    decision_point: str
    optimal_action: str

# =============================================================================
# RULES & KEYWORD MODELS
# =============================================================================

class Rule(MongoModel):
    """MTG Comprehensive Rule."""
    rule_number: str = Field(alias="ruleNumber")
    section: str
    text: str
    category: Optional[str] = None
    subrules: list["Rule"] = Field(default_factory=list)

class GlossaryTerm(MongoModel):
    """MTG Glossary term."""
    term: str
    definition: str
    related_terms: list[str] = Field(default_factory=list, alias="relatedTerms")

class Keyword(MongoModel):
    """MTG Keyword ability/action."""
    keyword: str
    description: str
    reminder_text: Optional[str] = Field(default=None, alias="reminderText")
    rule_numbers: list[str] = Field(default_factory=list, alias="ruleNumbers")
    is_evergreen: bool = Field(default=False, alias="isEvergreen")
    is_deciduous: bool = Field(default=False, alias="isDeciduous")

# =============================================================================
# MODEL REBUILD (resolve forward refs)
# =============================================================================

# Must be called after all models defined
Card.model_rebuild()
Combo.model_rebuild()
Rule.model_rebuild()
```

---

## MongoDB Field Mapping Reference

| MongoDB Field | Model Field | Model |
|---------------|-------------|-------|
| `_id` | `id` | `Combo` |
| `manaCost` | `mana_cost` | `Card`, `CardFace` |
| `type` | `type` | `Card` |
| `text` | `text` | `Card` |
| `oracleText` | `oracle_text` | `Card` |
| `colorIdentity` | `color_identity` | `Card`, `CardFace` |
| `edhrecRank` | `edhrec_rank` | `Card` |
| `edhrecSalt` | `edhrec_salt` | `Card` |
| `edhrecTags` | `edhrec_tags` | `Card` |
| `scryfallId` | `scryfall_id` | `Card` |
| `frameEffects` | `frame_effects` | `Card` |
| `isCommander` | `is_commander` | `ComboCard` |
| `lifeGain` | `life_gain` | `ComboProduces` |
| `lifeLoss` | `life_loss` | `ComboProduces` |
| `colorIdentity` | `color_identity` | `Commander` |
| `numDecks` | `num_decks` | `Commander` |
| `avgDeckRank` | `avg_deck_rank` | `Commander` |
| `cardUuid` | `card_uuid` | `Commander` |
| `colorIdentities` | `color_identities` | `Archetype` |
| `keyCards` | `key_cards` | `Archetype` |
| `winConditions` | `win_conditions` | `Archetype` |
| `budgetOptions` | `budget_options` | `Archetype` |
| `publishedDate` | `published_date` | `Article` |
| `ruleNumber` | `rule_number` | `Rule` |
| `reminderText` | `reminder_text` | `Keyword` |
| `ruleNumbers` | `rule_numbers` | `Keyword` |
| `isEvergreen` | `is_evergreen` | `Keyword` |
| `isDeciduous` | `is_deciduous` | `Keyword` |
| `relatedTerms` | `related_terms` | `GlossaryTerm` |
| `lastUpdated` | `last_updated` | `PriceData` |
| `usd_foil` | `usd_foil` | `PriceData` |
| `eur_foil` | `eur_foil` | `PriceData` |

---

## Integration Points

### 1. `models.py` - Backward Compatibility Layer
```python
# models.py - Keep existing imports working
from domain_models import (
    Card, CardWithMetadata, CardFace,
    Combo, ComboWithCards, ComboCard, ComboProduces,
    Commander, CommanderWithTags,
    PriceData, Ruling, Legality, CardLegalities,
    Archetype, Article, Guide, GuideChapter, GameState,
    Rule, GlossaryTerm, Keyword,
    QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics,
    ModelType, Model, ModelProvider, Requirement,
)

# Re-export for existing code
__all__ = [
    "Card", "CardWithMetadata", "CardFace",
    "Combo", "ComboWithCards", "ComboCard", "ComboProduces",
    "Commander", "CommanderWithTags",
    "PriceData", "Ruling", "Legality", "CardLegalities",
    "Archetype", "Article", "Guide", "GuideChapter", "GameState",
    "Rule", "GlossaryTerm", "Keyword",
    "QuestionAnswer", "QuestionAnswerEnhanced", "ValidationMetrics",
    "ModelType", "Model", "ModelProvider", "Requirement",
]
```

### 2. `common.py` - Prompt Building
```python
# Replace build_card_detail with model method
def build_card_detail(card_number: int | None, card: Card) -> str:
    prefix = f"Card {card_number}: " if card_number else ""
    return f"{prefix}{card.to_prompt_detail()}"
```

### 3. `data_access.py` - Return Typed Models
```python
# All methods return domain models, not raw dicts
def get_cards_enriched(self, filters, limit) -> list[CardWithMetadata]:
    pipeline = [...]  # aggregation
    return [CardWithMetadata(**doc) for doc in self.cards.aggregate(pipeline)]
```

### 4. Generator Usage
```python
# In any generator
def build_prompt(self, template: TemplateConfig, combo: ComboWithCards) -> str:
    card_details = "\n".join(c.to_prompt_detail() for c in combo.cards)
    # ...
```

---

## Testing Strategy

### Unit Tests for Models
- **Deserialization**: `CardWithMetadata(**mongo_doc)` works for real MongoDB documents
- **Aliases**: `card.edhrec_rank` reads from `edhrecRank` field
- **Computed Properties**: `cmc`, `is_commander_legal`, `best_price`, `salt_level` return correct values
- **Serialization**: `to_prompt_detail()` produces expected format
- **Forward Refs**: `model_rebuild()` resolves all circular references
- **Extra Fields**: Unknown MongoDB fields ignored (no validation error)

### Integration Tests
- **Data Access Layer**: `data_access.get_cards_enriched()` returns `list[CardWithMetadata]` with all joins populated
- **Generator Pipeline**: Refactored generator produces identical Q&A output as before
- **Validation**: `ValidationMetrics` works with new model types

### Regression Tests
- Compare MongoDB output documents before/after migration (category counts, field presence)
- Verify `QuestionAnswerEnhanced` structure unchanged

---

## Potential Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MongoDB schema drift (new fields) | Medium | Low | `extra="ignore"` handles new fields; add to model when stable |
| Circular reference resolution fails | Low | High | Call `model_rebuild()` after all models defined; test import order |
| Performance overhead of Pydantic validation | Low | Medium | Use `model_validate` for batch; profile if needed |
| Breaking existing generators | Medium | High | Backward compat layer in `models.py`; pilot with 2 generators first |
| Missing fields in some documents | High | Low | All fields `Optional` with defaults; computed properties handle `None` |

---

## Handoff to Implementer

**Design Document**: This file (`.opencode/design/story-003-extended-data-models.md`)

**User Story**: `.opencode/discovery/story-003-extended-data-models.md`

**Estimated Complexity**: Medium (data modeling, no external dependencies)

**Key Files to Create/Modify**:
1. `training_data/generate_synthetic_data/domain_models.py` (NEW - main deliverable)
2. `training_data/generate_synthetic_data/models.py` (modify - backward compat)
3. `training_data/generate_synthetic_data/common.py` (modify - use `to_prompt_detail()`)
4. `training_data/generate_synthetic_data/data_access.py` (Story 2 - consumes these models)
5. `training_data/generate_synthetic_data/base_generator.py` (Story 1 - type hints)

**Start With**: Task 1 - Core Card Models (`CardFace`, `Card`, `CardWithMetadata`)

**Acceptance Criteria** (from user story):
- [ ] File: `domain_models.py`
- [ ] All models use Pydantic v2 (`BaseModel`, `Field`, `ConfigDict`)
- [ ] Models include MongoDB field aliases for seamless deserialization
- [ ] Computed properties for derived data (color identity, CMC, etc.)
- [ ] Serialization helpers for LLM prompt building (`to_prompt_detail()`)
- [ ] **Card Models**: `CardFace`, `Card`, `CardWithMetadata` with EDHREC fields, prices, rulings, keywords
- [ ] **PriceData**: USD/EUR/TIX/foil, `best_price`, `is_budget()`
- [ ] **Ruling**: uuid, date, text, source
- [ ] **Legalities**: format, status; `CardLegalities` with `is_legal_in()`
- [ ] **Combo Models**: `ComboCard`, `ComboProduces`, `Combo`, `ComboWithCards` with properties
- [ ] **Commander Models**: `Commander`, `CommanderWithTags` with `salt_level`, `is_popular()`
- [ ] **Archetype**: name, description, color_identities, key_cards, strategy, win_conditions, weaknesses, budget_options
- [ ] **Article/Guide**: title, content, tags, chapters, metadata
- [ ] **GameState**: turn, phase, player_state, decision_point, optimal_action
- [ ] **Rules**: `Rule` (recursive subrules), `GlossaryTerm`, `Keyword`
- [ ] All models have `model_config = ConfigDict(populate_by_name=True, extra="ignore")`
- [ ] Field aliases match MongoDB field names exactly (camelCase)
- [ ] `to_prompt_detail()` methods produce consistent, readable output for LLM context
- [ ] Models handle missing/None fields gracefully (no required fields except identifiers)
- [ ] Circular references resolved with `ForwardRef` or string annotations
- [ ] `__repr__` and `__str__` useful for debugging