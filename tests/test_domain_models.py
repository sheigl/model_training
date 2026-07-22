"""Unit tests for Pydantic v2 domain models (Story 003).

Covers deserialization from MongoDB-style dicts, field aliases, computed
properties, serialization helpers, and forward-reference resolution.
"""

from __future__ import annotations

import sys
import os
import types
from datetime import datetime

# Ensure the generate_synthetic_data package is on the path for imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "training_data", "generate_synthetic_data"))

import pytest
from pydantic import ValidationError

from domain_models import (
    MongoModel,
    CardFace,
    Card,
    CardWithMetadata,
    PriceData,
    Ruling,
    Legality,
    CardLegalities,
    ComboCard,
    ComboProduces,
    Combo,
    ComboWithCards,
    Commander,
    CommanderWithTags,
    Archetype,
    Article,
    GuideChapter,
    Guide,
    GameState,
    Rule,
    GlossaryTerm,
    Keyword,
)


# =============================================================================
# CardFace Tests
# =============================================================================

class TestCardFace:
    def test_minimal(self):
        face = CardFace(name="Test", type="Creature", text="")
        assert face.name == "Test"
        assert face.type_line == "Creature"
        assert face.oracle_text == ""

    def test_mongo_aliases(self):
        doc = {
            "name": "Lightning Bolt",
            "manaCost": "{R}",
            "type": "Instant",
            "text": "Deals 3 damage.",
            "colorIdentity": ["R"],
        }
        face = CardFace(**doc)
        assert face.mana_cost == "{R}"
        assert face.type_line == "Instant"
        assert face.color_identity == ["R"]

    def test_extra_fields_ignored(self):
        doc = {
            "name": "Test",
            "type": "Creature",
            "text": "",
            "unknown_field": "should be ignored",
        }
        face = CardFace(**doc)
        assert face.name == "Test"

    def test_repr(self):
        face = CardFace(name="Test", type="Instant", text="")
        assert "Test" in repr(face)


# =============================================================================
# Card Tests
# =============================================================================

class TestCard:
    def test_minimal(self):
        card = Card(name="Basic Land")
        assert card.name == "Basic Land"
        assert card.cmc == 0.0
        assert not card.is_creature
        assert not card.is_legendary

    def test_mongo_aliases(self):
        doc = {
            "name": "Lightning Bolt",
            "manaCost": "{R}",
            "type": "Instant — Sorcery",
            "text": "Deals 3 damage to any target.",
            "oracleText": "Lightning Bolt deals 3 damage to any target.",
            "colorIdentity": ["R"],
            "edhrecRank": 10,
            "edhrecSalt": 1.2,
            "edhrecTags": ['"Direct Damage"', '"Removal"'],
            "legalities": {"commander": "Legal", "standard": "Not Legal"},
        }
        card = Card(**doc)
        assert card.mana_cost == "{R}"
        assert card.oracle_text == "Lightning Bolt deals 3 damage to any target."
        assert card.color_identity == ["R"]
        assert card.edhrec_rank == 10
        assert card.edhrec_salt == 1.2
        assert '"Direct Damage"' in card.edhrec_tags
        assert card.is_commander_legal is True

    def test_cmc_parsing(self):
        # Simple colored mana
        card = Card(name="Test", mana_cost="{W}{U}")
        assert card.cmc == 2.0

        # Numeric mana
        card = Card(name="Test", mana_cost="{3}{G}")
        assert card.cmc == 4.0

        # X (variable, counts as 0)
        card = Card(name="Test", mana_cost="{X}{W}")
        assert card.cmc == 1.0

        # No mana cost
        card = Card(name="Basic Land")
        assert card.cmc == 0.0

    def test_is_creature(self):
        card = Card(name="Goblin", type="Creature — Goblin")
        assert card.is_creature is True

        card2 = Card(name="Lightning Bolt", type="Instant")
        assert card2.is_creature is False

    def test_is_legendary(self):
        card = Card(name="Jace", type="Legendary Planeswalker — Jace")
        assert card.is_legendary is True

        card2 = Card(name="Test", type="Creature")
        assert card2.is_legendary is False

    def test_primary_face_from_faces(self):
        face = CardFace(name="Front", type="Creature", text="", manaCost="{1}")
        card = Card(name="DFC", faces=[face])
        pf = card.primary_face
        assert pf.name == "Front"
        assert pf.mana_cost == "{1}"

    def test_primary_face_from_main_fields(self):
        card = Card(
            name="Simple Spell",
            mana_cost="{R}",
            type="Instant",
            text="Deals 3 damage.",
            color_identity=["R"],
        )
        pf = card.primary_face
        assert pf.name == "Simple Spell"
        assert pf.mana_cost == "{R}"

    def test_to_prompt_detail_basic(self):
        card = Card(
            name="Lightning Bolt",
            mana_cost="{R}",
            type="Instant",
            text="Deals 3 damage to any target.",
            color_identity=["R"],
            keywords=["None"],
        )
        detail = card.to_prompt_detail()
        assert "Name: Lightning Bolt" in detail
        assert "Mana Cost: {R}" in detail
        assert "Type: Instant" in detail

    def test_to_prompt_detail_with_prices(self):
        prices = PriceData(usd=0.25, eur=0.20)
        card = Card(name="Test", mana_cost="{1}", type="Instant", text="", prices=prices)
        detail = card.to_prompt_detail(include_prices=True)
        assert "Price:" in detail

    def test_to_prompt_detail_no_prices(self):
        card = Card(name="Test", mana_cost="{1}", type="Instant", text="")
        detail = card.to_prompt_detail(include_prices=False)
        assert "Price" not in detail

    def test_to_prompt_detail_with_edhrec(self):
        card = Card(
            name="Test",
            mana_cost="{1}",
            type="Creature",
            text="",
            edhrec_rank=50,
            edhrec_salt=2.5,
            edhrec_tags=['"Staple"'],
        )
        detail = card.to_prompt_detail()
        assert "EDHREC Rank: 50" in detail
        assert "Salt Score: 2.50" in detail
        assert 'Tags: "Staple"' in detail

    def test_extra_fields_ignored(self):
        doc = {
            "name": "Test",
            "unknown_mongo_field": True,
            "another_unknown": [1, 2],
        }
        card = Card(**doc)
        assert card.name == "Test"

    def test_repr(self):
        card = Card(name="Test")
        assert "Test" in repr(card)


# =============================================================================
# CardWithMetadata Tests
# =============================================================================

class TestCardWithMetadata:
    def test_inherits_card_fields(self):
        doc = {
            "name": "Enchanted",
            "manaCost": "{2}{W}",
            "type": "Creature — Human Wizard",
            "text": "",
            "colorIdentity": ["W"],
            "edhrecRank": 100,
        }
        card = CardWithMetadata(**doc)
        assert isinstance(card, Card)
        assert card.name == "Enchanted"
        assert card.edhrec_rank == 100

    def test_with_prices_and_rulings(self):
        doc = {
            "name": "Test",
            "manaCost": "{1}",
            "type": "Instant",
            "text": "",
            "prices": {"usd": 1.50, "eur": 1.20},
            "rulings": [
                {
                    "uuid": "abc-123",
                    "date": "2024-01-01T00:00:00Z",
                    "text": "This is a ruling.",
                }
            ],
        }
        card = CardWithMetadata(**doc)
        assert card.prices is not None
        assert card.prices.usd == 1.50
        assert len(card.rulings) == 1
        assert card.rulings[0].text == "This is a ruling."


# =============================================================================
# PriceData Tests
# =============================================================================

class TestPriceData:
    def test_best_price(self):
        p = PriceData(usd=2.50, eur=3.00, paper=1.80)
        assert p.best_price == 1.80

    def test_best_price_all_none(self):
        p = PriceData()
        assert p.best_price is None

    def test_is_budget_default(self):
        p = PriceData(usd=3.00)
        assert p.is_budget() is True

    def test_is_budget_expensive(self):
        p = PriceData(usd=15.00)
        assert p.is_budget() is False

    def test_is_budget_custom_threshold(self):
        p = PriceData(usd=3.00)
        assert p.is_budget(threshold=2.0) is False

    def test_mongo_aliases(self):
        doc = {
            "usd": 1.50,
            "usd_foil": 5.00,
            "eur": 1.30,
            "lastUpdated": "2024-06-01T12:00:00Z",
        }
        p = PriceData(**doc)
        assert p.usd == 1.50
        assert p.usd_foil == 5.00

    def test_repr(self):
        p = PriceData(usd=1.0)
        assert "usd" in repr(p).lower()


# =============================================================================
# Ruling Tests
# =============================================================================

class TestRuling:
    def test_minimal(self):
        r = Ruling(uuid="abc", date=datetime(2024, 1, 1), text="A ruling.")
        assert r.source == "official"

    def test_source_options(self):
        for src in ("official", "scryfall", "community"):
            r = Ruling(uuid="x", date=datetime.now(), text="", source=src)
            assert r.source == src


# =============================================================================
# Legality Tests
# =============================================================================

class TestLegality:
    def test_legal(self):
        l = Legality(format="Commander", status="legal")
        assert l.status == "legal"

    def test_status_options(self):
        for s in ("legal", "not_legal", "restricted", "banned"):
            l = Legality(format="Test", status=s)  # type: ignore[arg-type]
            assert l.status == s


class TestCardLegalities:
    def test_is_legal_in(self):
        cl = CardLegalities(
            uuid="abc",
            legalities=[
                Legality(format="Commander", status="legal"),
                Legality(format="Standard", status="not_legal"),
            ],
        )
        assert cl.is_legal_in("commander") is True
        assert cl.is_legal_in("standard") is False

    def test_is_legal_in_case_insensitive(self):
        cl = CardLegalities(
            uuid="abc",
            legalities=[Legality(format="Commander", status="legal")],
        )
        assert cl.is_legal_in("COMMANDER") is True

    def test_unknown_format(self):
        cl = CardLegalities(uuid="abc", legalities=[])
        assert cl.is_legal_in("pioneer") is False


# =============================================================================
# Combo Tests
# =============================================================================

class TestComboCard:
    def test_defaults(self):
        cc = ComboCard(name="Test")
        assert cc.quantity == 1
        assert cc.is_commander is False
        assert cc.zone == "battlefield"

    def test_mongo_aliases(self):
        doc = {"name": "Goblin", "isCommander": True, "zone": "command_zone"}
        cc = ComboCard(**doc)
        assert cc.is_commander is True
        assert cc.zone == "command_zone"


class TestComboProduces:
    def test_defaults(self):
        cp = ComboProduces(description="Infinite mana")
        assert cp.infinite is False

    def test_mongo_aliases(self):
        doc = {"description": "Life", "lifeGain": True, "lifeLoss": True}
        cp = ComboProduces(**doc)
        assert cp.life_gain is True
        assert cp.life_loss is True


class TestCombo:
    def test_minimal(self):
        c = Combo(_id="combo-1")
        assert c.id == "combo-1"

    def test_card_names(self):
        c = Combo(
            _id="c1",
            uses=[ComboCard(name="A"), ComboCard(name="B")],
        )
        assert c.card_names == ["A", "B"]

    def test_is_infinite_true(self):
        c = Combo(
            _id="c1",
            produces=[ComboProduces(description="Inf mana", infinite=True)],
        )
        assert c.is_infinite is True

    def test_is_infinite_false(self):
        c = Combo(_id="c1", produces=[])
        assert c.is_infinite is False


class TestComboWithCards:
    def test_with_enriched_cards(self):
        card = CardWithMetadata(name="Test", mana_cost="{1}", type="Instant", text="")
        cw = ComboWithCards(
            _id="combo-1",
            uses=[ComboCard(name="Test")],
            cards=[card],
        )
        assert len(cw.cards) == 1
        assert cw.cards[0].name == "Test"


# =============================================================================
# Commander Tests
# =============================================================================

class TestCommander:
    def test_minimal(self):
        cmd = Commander(name="Gideon")
        assert cmd.num_decks == 0
        assert cmd.salt == 0.0

    def test_mongo_aliases(self):
        doc = {
            "name": "Jace",
            "colorIdentity": ["U"],
            "numDecks": 5000,
            "avgDeckRank": 120.5,
            "cardUuid": "abc-123",
        }
        cmd = Commander(**doc)
        assert cmd.color_identity == ["U"]
        assert cmd.num_decks == 5000
        assert cmd.avg_deck_rank == 120.5

    def test_is_popular(self):
        cmd = Commander(name="Test", numDecks=2000)
        assert cmd.is_popular() is True
        assert cmd.is_popular(threshold=5000) is False

    def test_salt_level_low(self):
        cmd = Commander(name="Test", salt=0.3)
        assert cmd.salt_level == "low"

    def test_salt_level_medium(self):
        cmd = Commander(name="Test", salt=1.0)
        assert cmd.salt_level == "medium"

    def test_salt_level_high(self):
        cmd = Commander(name="Test", salt=2.0)
        assert cmd.salt_level == "high"

    def test_salt_level_extreme(self):
        cmd = Commander(name="Test", salt=3.0)
        assert cmd.salt_level == "extreme"


class TestCommanderWithTags:
    def test_extended_fields(self):
        cmd = CommanderWithTags(
            name="Jace",
            inclusion_pct=15.5,
            salt_score=2.1,
        )
        assert cmd.inclusion_pct == 15.5
        assert cmd.salt_score == 2.1


# =============================================================================
# Archetype Tests
# =============================================================================

class TestArchetype:
    def test_minimal(self):
        a = Archetype(name="Voltron")
        assert a.description == ""
        assert a.key_cards == []

    def test_mongo_aliases(self):
        doc = {
            "name": "Stax",
            "colorIdentities": [["B"], ["G"]],
            "keyCards": ["Tormod's Crypt", "Rest in Peace"],
            "winConditions": ['"Beat down with creatures"'],
            "budgetOptions": ["Crypt of Agadeem"],
        }
        a = Archetype(**doc)
        assert a.color_identities == [["B"], ["G"]]
        assert len(a.key_cards) == 2


# =============================================================================
# Article & Guide Tests
# =============================================================================

class TestArticle:
    def test_minimal(self):
        art = Article(title="Test", content="Body")
        assert art.tags == []

    def test_mongo_aliases(self):
        doc = {
            "title": "Guide to Commander",
            "content": "...",
            "publishedDate": "2024-01-15T10:00:00Z",
        }
        art = Article(**doc)
        assert isinstance(art.published_date, datetime)


class TestGuideChapter:
    def test_minimal(self):
        ch = GuideChapter(title="Intro", content="Welcome")
        assert ch.title == "Intro"


class TestGuide:
    def test_with_chapters(self):
        g = Guide(
            title="Commander 101",
            chapters=[
                GuideChapter(title="Basics", content="..."),
                GuideChapter(title="Advanced", content="..."),
            ],
        )
        assert len(g.chapters) == 2


# =============================================================================
# GameState Tests
# =============================================================================

class TestGameState:
    def test_minimal(self):
        gs = GameState(
            turn=3,
            phase="main",
            player_state={"life": 20, "hand_size": 5},
            decision_point="Play a creature?",
            optimal_action="Cast Goblin.",
        )
        assert gs.turn == 3
        assert gs.phase == "main"


# =============================================================================
# Rule Tests
# =============================================================================

class TestRule:
    def test_minimal(self):
        r = Rule(ruleNumber="100.2", section="Game Basics", text="The game starts.")
        assert r.rule_number == "100.2"

    def test_recursive_subrules(self):
        sub = Rule(ruleNumber="100.2a", section="Game Basics", text="Subrule A")
        parent = Rule(
            ruleNumber="100.2",
            section="Game Basics",
            text="Main rule.",
            subrules=[sub],
        )
        assert len(parent.subrules) == 1
        assert parent.subrules[0].rule_number == "100.2a"


# =============================================================================
# GlossaryTerm Tests
# =============================================================================

class TestGlossaryTerm:
    def test_minimal(self):
        gt = GlossaryTerm(term="Stack", definition="Zone for spells.")
        assert gt.related_terms == []

    def test_mongo_aliases(self):
        doc = {
            "term": "Tap",
            "definition": "Rotate card 90 degrees.",
            "relatedTerms": ["Untap", "Activate"],
        }
        gt = GlossaryTerm(**doc)
        assert gt.related_terms == ["Untap", "Activate"]


# =============================================================================
# Keyword Tests
# =============================================================================

class TestKeyword:
    def test_minimal(self):
        kw = Keyword(keyword="Flying", description="Can only be blocked by flying.")
        assert kw.is_evergreen is False

    def test_mongo_aliases(self):
        doc = {
            "keyword": "Haste",
            "description": "Can attack the turn it enters.",
            "reminderText": "(This creature can attack...)",
            "ruleNumbers": ["702.10"],
            "isEvergreen": True,
            "isDeciduous": False,
        }
        kw = Keyword(**doc)
        assert kw.reminder_text is not None
        assert kw.rule_numbers == ["702.10"]
        assert kw.is_evergreen is True


# =============================================================================
# MongoModel Base Tests
# =============================================================================

class TestMongoModel:
    def test_extra_fields_ignored(self):
        class TestModel(MongoModel):
            name: str

        m = TestModel(name="Test", extra_field=123, another=None)
        assert m.name == "Test"

    def test_populate_by_name(self):
        from pydantic import Field as PydanticField

        class AliasModel(MongoModel):
            my_field: str = PydanticField(alias="mongoField")

        m = AliasModel(mongoField="value")
        assert m.my_field == "value"


# =============================================================================
# Forward Reference Resolution Tests
# =============================================================================

class TestForwardRefs:
    def test_card_with_price(self):
        """Card.prices should accept a PriceData instance."""
        card = Card(
            name="Test",
            prices=PriceData(usd=1.0),
        )
        assert isinstance(card.prices, PriceData)

    def test_card_with_rulings(self):
        """Card.rulings should accept Ruling instances."""
        card = Card(
            name="Test",
            rulings=[Ruling(uuid="x", date=datetime.now(), text="Ruling")],
        )
        assert len(card.rulings) == 1

    def test_rule_with_subrules(self):
        """Rule.subrules should accept Rule instances."""
        rule = Rule(
            ruleNumber="100.1",
            section="Test",
            text="Parent",
            subrules=[Rule(ruleNumber="100.1a", section="Test", text="Child")],
        )
        assert len(rule.subrules) == 1

    def test_combo_with_cards(self):
        """ComboWithCards.cards should accept CardWithMetadata instances."""
        combo = ComboWithCards(
            _id="c1",
            cards=[CardWithMetadata(name="Test")],
        )
        assert len(combo.cards) == 1


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    def test_card_to_prompt_detail_full(self):
        card = Card(
            name="Goblin Guide",
            mana_cost="{R}",
            type="Creature — Goblin Warrior",
            text="Haste\nGoblin Guide gets +1/+0 for each creature you control.",
            power="2",
            toughness="1",
            color_identity=["R"],
            keywords=["Haste"],
            edhrec_rank=42,
            edhrec_salt=1.8,
            edhrec_tags=['"Aggro"', '"Goblins"'],
            prices=PriceData(usd=3.50),
        )
        detail = card.to_prompt_detail(include_prices=True)
        lines = detail.split("\n")
        assert any("Name: Goblin Guide" in l for l in lines)
        assert any("Power/Toughness: 2/1" in l for l in lines)
        assert any("Color Identity: R" in l for l in lines)
        assert any("Keywords: Haste" in l for l in lines)
        assert any("EDHREC Rank: 42" in l for l in lines)
        assert any("Salt Score: 1.80" in l for l in lines)
        assert any('Tags: "Aggro", "Goblins"' in l for l in lines)
        assert any("Price:" in l for l in lines)

    def test_card_to_prompt_detail_planeswalker(self):
        card = Card(
            name="Jace, Wielder of Mysteries",
            mana_cost="{2}{U}{U}",
            type="Legendary Planeswalker — Jace",
            text="",
            loyalty="4",
            color_identity=["U"],
        )
        detail = card.to_prompt_detail()
        assert "Loyalty: 4" in detail

    def test_card_to_prompt_detail_rulings(self):
        card = Card(
            name="Test",
            rulings=[Ruling(uuid="x", date=datetime.now(), text="R1")],
        )
        detail = card.to_prompt_detail(include_rulings=True)
        assert "Rulings: 1 available" in detail

    def test_card_to_dict(self):
        card = Card(name="Test", mana_cost="{1}")
        d = card.model_dump()
        assert d["name"] == "Test"
        assert d["mana_cost"] == "{1}"


class TestCardFactory:
    """Tests for Card.from_dict(), to_dict(), and toDict()."""

    def test_from_dict_camelcase(self):
        data = {
            "name": "Lightning Bolt",
            "type": "Instant",
            "manaCost": "{R}",
            "text": "Deals 3 damage.",
            "subtypes": [],
            "supertypes": [],
            "colorIdentity": ["R"],
        }
        card = Card.from_dict(data)
        assert card is not None
        assert card.name == "Lightning Bolt"
        assert card.mana_cost == "{R}"
        assert card.color_identity == ["R"]

    def test_from_dict_snakecase(self):
        data = {
            "name": "Test Card",
            "type": "Sorcery",
            "mana_cost": "{2}",
            "text": "",
            "subtypes": [],
            "supertypes": [],
            "color_identity": [],
        }
        card = Card.from_dict(data)
        assert card is not None
        assert card.mana_cost == "{2}"

    def test_from_dict_json_encoded_lists(self):
        data = {
            "name": "Test",
            "type": "Creature — Human Wizard",
            "manaCost": "{1}",
            "text": "",
            "subtypes": '["Human", "Wizard"]',
            "supertypes": '["Legendary"]',
            "colorIdentity": '["U"]',
        }
        card = Card.from_dict(data)
        assert card is not None
        assert card.subtypes == ["Human", "Wizard"]
        assert card.supertypes == ["Legendary"]
        assert card.color_identity == ["U"]

    def test_from_dict_missing_required(self):
        assert Card.from_dict({}) is None
        assert Card.from_dict({"name": "X"}) is None  # missing type
        assert Card.from_dict(None) is None  # type: ignore[arg-type]

    def test_to_dict_excludes_none(self):
        card = Card(name="Test", mana_cost="{1}", type="Instant")
        d = card.to_dict()
        assert "name" in d
        assert "mana_cost" in d
        assert "uuid" not in d  # None fields excluded

    def test_toDict_alias(self):
        card = Card(name="Test", mana_cost="{1}")
        d = card.toDict()
        assert isinstance(d, dict)
        assert d["name"] == "Test"


class TestMapCardHelper:
    """Tests for card_utils.map_card and card_utils.map_card_with_zones."""

    def test_map_card_basic(self):
        from training_data.generate_synthetic_data.card_utils import map_card  # noqa: PLC0415

        data = {
            "name": "Sol Ring",
            "type": "Artifact",
            "manaCost": "{1}",
            "text": "Tap: Add {C}{C}.",
            "subtypes": [],
            "supertypes": [],
            "colorIdentity": [],
        }
        card = map_card(data)
        assert card is not None
        assert card.name == "Sol Ring"

    def test_map_card_returns_none_for_invalid(self):
        from training_data.generate_synthetic_data.card_utils import map_card  # noqa: PLC0415

        assert map_card({}) is None
        assert map_card({"name": "X"}) is None

    def test_map_card_with_zones(self):
        from training_data.generate_synthetic_data.card_utils import (  # noqa: PLC0415
            map_card_with_zones,
        )

        data = {
            "name": "Test",
            "type": "Instant",
            "manaCost": "{1}",
            "text": "",
            "subtypes": [],
            "supertypes": [],
            "colorIdentity": [],
        }
        card = map_card_with_zones(data, zone_locations=["hand"])
        assert card is not None
        assert getattr(card, "zone_locations", None) == ["hand"]

    def test_map_card_with_zones_empty(self):
        from training_data.generate_synthetic_data.card_utils import (  # noqa: PLC0415
            map_card_with_zones,
        )

        data = {
            "name": "Test",
            "type": "Instant",
            "manaCost": "{1}",
            "text": "",
            "subtypes": [],
            "supertypes": [],
            "colorIdentity": [],
        }
        card = map_card_with_zones(data)
        assert card is not None
        assert getattr(card, "zone_locations", []) == []
