# Story: Extended Data Models (Pydantic)

## User Story
As a **developer building the synthetic data generators**, I want **comprehensive Pydantic models for all MTG domain objects** with proper typing, validation, and serialization, so that **the Unified Data Access Layer (Story 2) returns rich, typed objects and generators have full IDE autocomplete and runtime validation**.

## Context
Currently, generators work with raw MongoDB dicts and manual `json.loads()` for nested fields (subtypes, supertypes, colorIdentity). There are no shared models for Combo, Commander, Ruling, PriceData, Legalities, Archetype, GameState, Article, Guide. The `Card` model in `models.py` is minimal and doesn't include EDHREC fields (rank, salt, tags), prices, legalities, or rulings.

## Acceptance Criteria
- [ ] File: `training_data/generate_synthetic_data/domain_models.py`
- [ ] All models use Pydantic v2 (`BaseModel`, `Field`, `ConfigDict`)
- [ ] Models include MongoDB field aliases for seamless deserialization
- [ ] Computed properties for derived data (color identity, CMC, etc.)
- [ ] Serialization helpers for LLM prompt building

### Required Models

#### 1. Card Models
```python
class CardFace(BaseModel):
    name: str
    mana_cost: str | None = Field(alias="manaCost")
    type_line: str = Field(alias="type")
    oracle_text: str = Field(alias="text")
    power: str | None
    toughness: str | None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list, alias="colorIdentity")
    keywords: list[str] = Field(default_factory=list)

class Card(BaseModel):
    # Core identifiers
    name: str
    uuid: str | None = None
    scryfall_id: str | None = Field(alias="scryfallId", default=None)
    
    # Card faces (for DFCs, split cards)
    faces: list[CardFace] = Field(default_factory=list)
    
    # Main face fields (backward compat)
    mana_cost: str | None = Field(alias="manaCost", default=None)
    type: str | None = None
    text: str | None = None
    power: str | None = None
    toughness: str | None = None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list, alias="colorIdentity")
    subtypes: list[str] = Field(default_factory=list)
    supertypes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    
    # EDHREC data (embedded in mtg_json.cards)
    edhrec_rank: int | None = Field(alias="edhrecRank", default=None)
    edhrec_salt: float | None = Field(alias="edhrecSalt", default=None)
    edhrec_tags: list[str] = Field(default_factory=list, alias="edhrecTags")
    
    # Legalities (embedded)
    legalities: dict[str, str] = Field(default_factory=dict)
    
    # Prices (joined)
    prices: "PriceData | None" = None
    
    # Rulings (joined)
    rulings: list["Ruling"] = Field(default_factory=list)
    
    # Computed properties
    @property
    def cmc(self) -> float: ...
    @property
    def is_commander_legal(self) -> bool: ...
    @property
    def is_creature(self) -> bool: ...
    @property
    def primary_face(self) -> CardFace: ...
    
    def to_prompt_detail(self) -> str: ...  # For LLM context
```

#### 2. PriceData Model
```python
class PriceData(BaseModel):
    usd: float | None = None
    usd_foil: float | None = Field(alias="usd_foil", default=None)
    eur: float | None = None
    eur_foil: float | None = Field(alias="eur_foil", default=None)
    tix: float | None = None
    paper: float | None = None  # Average paper price
    last_updated: datetime | None = Field(alias="lastUpdated", default=None)
    
    @property
    def best_price(self) -> float | None: ...  # Lowest non-None
    @property
    def is_budget(self, threshold: float = 5.0) -> bool: ...
```

#### 3. Ruling Model
```python
class Ruling(BaseModel):
    uuid: str
    date: datetime
    text: str
    source: str = "official"  # "official" | "scryfall" | "community"
```

#### 4. Legality Model
```python
class Legality(BaseModel):
    format: str
    status: str  # "legal" | "not_legal" | "restricted" | "banned"
    
class CardLegalities(BaseModel):
    card_uuid: str = Field(alias="uuid")
    legalities: list[Legality] = Field(default_factory=list)
    
    def is_legal_in(self, format_name: str) -> bool: ...
```

#### 5. Combo Models (Commander Spellbook)
```python
class ComboCard(BaseModel):
    name: str
    uuid: str | None = None
    quantity: int = 1
    is_commander: bool = Field(alias="isCommander", default=False)
    zone: str = "battlefield"  # battlefield, hand, graveyard, command_zone, library

class ComboProduces(BaseModel):
    description: str
    infinite: bool = False
    mana: bool = False
    damage: bool = False
    tokens: bool = False
    draw: bool = False
    mill: bool = False
    life_gain: bool = Field(alias="lifeGain", default=False)
    life_loss: bool = Field(alias="lifeLoss", default=False)

class Combo(BaseModel):
    id: str = Field(alias="_id")
    name: str | None = None
    uses: list[ComboCard] = Field(default_factory=list)
    produces: list[ComboProduces] = Field(default_factory=list)
    description: str = ""
    status: str = "OK"  # OK, Unverified, etc.
    tags: list[str] = Field(default_factory=list)
    commanders: list[str] = Field(default_factory=list)
    
    @property
    def card_names(self) -> list[str]: ...
    @property
    def is_infinite(self) -> bool: ...
    @property
    def primary_colors(self) -> list[str]: ...
```

#### 6. Commander Model (EDHREC)
```python
class Commander(BaseModel):
    name: str
    color_identity: list[str] = Field(alias="colorIdentity", default_factory=list)
    tags: list[str] = Field(default_factory=list)
    num_decks: int = Field(alias="numDecks", default=0)
    salt: float = 0.0
    avg_deck_rank: float | None = Field(alias="avgDeckRank", default=None)
    card_uuid: str | None = Field(alias="cardUuid", default=None)
    
    @property
    def is_popular(self, threshold: int = 1000) -> bool: ...
    @property
    def salt_level(self) -> str: ...  # "low", "medium", "high", "extreme"
```

#### 7. Archetype Model
```python
class Archetype(BaseModel):
    name: str
    description: str
    color_identities: list[list[str]] = Field(alias="colorIdentities", default_factory=list)
    key_cards: list[str] = Field(alias="keyCards", default_factory=list)
    strategy: str = ""
    win_conditions: list[str] = Field(alias="winConditions", default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    budget_options: list[str] = Field(alias="budgetOptions", default_factory=list)
```

#### 8. Article/Guide Models (EDHREC)
```python
class Article(BaseModel):
    title: str
    content: str
    excerpt: str | None = None
    tags: list[str] = Field(default_factory=list)
    author: str | None = None
    published_date: datetime | None = Field(alias="publishedDate", default=None)
    url: str | None = None

class GuideChapter(BaseModel):
    title: str
    content: str

class Guide(BaseModel):
    title: str
    chapters: list[GuideChapter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
```

#### 9. Rules Models
```python
class Rule(BaseModel):
    rule_number: str = Field(alias="ruleNumber")
    section: str
    text: str
    category: str | None = None
    subrules: list["Rule"] = Field(default_factory=list)

class GlossaryTerm(BaseModel):
    term: str
    definition: str
    related_terms: list[str] = Field(alias="relatedTerms", default_factory=list)
```

#### 10. Keyword Model
```python
class Keyword(BaseModel):
    keyword: str
    description: str
    reminder_text: str | None = Field(alias="reminderText", default=None)
    rule_numbers: list[str] = Field(alias="ruleNumbers", default_factory=list)
    is_evergreen: bool = Field(alias="isEvergreen", default=False)
    is_deciduous: bool = Field(alias="isDeciduous", default=False)
```

## Template Definitions
N/A - These are data models, not generation templates.

## Validation Criteria
- [ ] All models have `model_config = ConfigDict(populate_by_name=True, extra="ignore")`
- [ ] Field aliases match MongoDB field names exactly (camelCase)
- [ ] `to_prompt_detail()` methods produce consistent, readable output for LLM context
- [ ] Models handle missing/None fields gracefully (no required fields except identifiers)
- [ ] Circular references resolved with `ForwardRef` or string annotations
- [ ] `__repr__` and `__str__` useful for debugging

## Dependencies
- None (foundation story)

## Priority: High
## Story Points: 8

## Notes
- These models replace the minimal `Card` class in `models.py`
- The `models.py` file should be updated to import from `domain_models.py`
- Generators will use `card.to_prompt_detail()` instead of `build_card_detail()`
- Price data comes from `cardPrices` collection (1M+ docs) - join by UUID
- Rulings from `cardRulings` (258K docs) - join by UUID
- Legalities from `cardLegalities` (108K docs) - join by UUID
- EDHREC fields (rank, salt, tags) are already embedded in `mtg_json.cards`