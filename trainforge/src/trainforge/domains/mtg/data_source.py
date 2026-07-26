"""MTG-specific data access layer — extends MongoDataSource with typed collection methods."""

from __future__ import annotations

import logging
import re as _re
import threading
import time
from functools import wraps
from typing import Any, TypeVar

from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError

from trainforge.data_source import MongoDataSource
from trainforge.domains.mtg.models import (
    Archetype,
    CardLegalities,
    CardWithMetadata,
    ComboWithCards,
    CommanderWithTags,
    Guide,
    Legality,
    PriceData,
    Ruling,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# CACHE & RETRY UTILITIES
# =============================================================================


class LRUCacheWithTTL:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    self._hits += 1
                    return value
                del self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self.maxsize:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (value, time.time())

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}


def retry_on_transient_error(max_retries: int = 3, base_delay: float = 0.5):
    """Retry on ConnectionFailure, ServerSelectionTimeoutError, OperationFailure."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            func_name = getattr(func, "__name__", "unknown")
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (ConnectionFailure, ServerSelectionTimeoutError, OperationFailure) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Transient error in {func_name} (attempt {attempt + 1}/{max_retries}): "
                            f"{e}. Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All retries exhausted for {func_name}: {e}")
            raise last_exception
        return wrapper
    return decorator


# =============================================================================
# MTG DATA ACCESS
# =============================================================================


class MTGDataAccess(MongoDataSource):
    """Magic: The Gathering data access layer.

    Extends MongoDataSource with convenience methods for accessing MTG-specific
    collections (cards, articles, rules, glossary, EDHREC rankings) and enriched
    aggregation pipelines for typed model access.

    Usage:
        db = MTGDataAccess(uri="mongodb://localhost:27017")
        cards = db.get_cards_enriched(filters={"colorIdentity": ["W", "U"]}, limit=100)
        combos = db.get_combos_enriched(limit=50)
    """

    # Required collections for full functionality
    REQUIRED_COLLECTIONS: dict[str, list[str]] = {
        "mtg_json": ["cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"],
        "commander_spellbook": ["variants"],
        "edhrec": ["commanders", "articles", "guides", "game-changers"],
        "mtg_archetypes": ["archetypes"],
        "mtg_rules": ["rules", "glossary"],
        "scryfall": ["oracle_cards"],
    }

    # Indexes to verify/create on startup
    REQUIRED_INDEXES: dict[str, list[list[tuple[str, int]]]] = {
        "mtg_json.cards": [
            [("uuid", 1)],
            [("name", 1)],
            [("colorIdentity", 1)],
            [("keywords", 1)],
            [("edhrecRank", 1)],
        ],
        "mtg_json.cardPrices": [[("uuid", 1)]],
        "mtg_json.cardLegalities": [[("uuid", 1)]],
        "mtg_json.cardRulings": [[("uuid", 1)]],
        "commander_spellbook.variants": [
            [("status", 1)],
            [("uses.card.name", 1)],
        ],
        "edhrec.commanders": [
            [("cardUuid", 1)],
            [("numDecks", -1)],
            [("colorIdentity", 1)],
        ],
        "mtg_rules.rules": [[("ruleNumber", 1)]],
        "mtg_rules.glossary": [[("term", 1)]],
    }

    def __init__(self, uri: str = "mongodb://localhost:27017", **kwargs):
        cache_maxsize = kwargs.pop("cache_maxsize", 1000)
        cache_ttl = kwargs.pop("cache_ttl", 300)
        super().__init__(uri=uri, **kwargs)
        self.db_name = "synthetic_queries"
        self._cache = LRUCacheWithTTL(maxsize=cache_maxsize, ttl=cache_ttl)
        self._indexes_verified = False

    # =========================================================================
    # EXISTING SIMPLE METHODS (preserved for backward compatibility)
    # =========================================================================

    # ------------------------------------------------------------------
    # CARD DATA
    # ------------------------------------------------------------------

    def get_cards(self, limit: int = 1000, filters: dict | None = None) -> list[dict]:
        """Fetch card records from the cards collection."""
        return self.get_records(f"{self.db_name}.mtg_cards", filters=filters, limit=limit)

    def get_card_by_name(self, name: str) -> CardWithMetadata | None:
        """Find a specific card by exact name match (enriched with metadata)."""
        return self.get_cards_enriched(filters={"name": name}, limit=1, lite=False)

    def get_cards_by_type(self, type_: str, limit: int = 500) -> list[dict]:
        """Get cards filtered by card type (e.g., 'Creature', 'Artifact')."""
        return self.get_records(
            f"{self.db_name}.mtg_cards", filters={"type": type_}, limit=limit
        )

    def get_cards_by_color(self, color: str, limit: int = 500) -> list[dict]:
        """Get cards filtered by color identity."""
        return self.get_records(
            f"{self.db_name}.mtg_cards", filters={"color_identity": color}, limit=limit
        )

    # ------------------------------------------------------------------
    # ARTICLE DATA
    # ------------------------------------------------------------------

    def get_articles(self, limit: int = 1000, filters: dict | None = None) -> list[dict]:
        """Fetch article/guide records."""
        return self.get_records(f"{self.db_name}.mtg_articles", filters=filters, limit=limit)

    # ------------------------------------------------------------------
    # RULES DATA
    # ------------------------------------------------------------------

    def get_rules(self, limit: int = 1000, filters: dict | None = None) -> list[dict]:
        """Fetch comprehensive rules records."""
        return self.get_records(f"{self.db_name}.mtg_rules", filters=filters, limit=limit)

    # ------------------------------------------------------------------
    # GLOSSARY DATA
    # ------------------------------------------------------------------

    def get_glossary(self, limit: int = 1000, filters: dict | None = None) -> list[dict]:
        """Fetch glossary entries."""
        return self.get_records(f"{self.db_name}.mtg_glossary", filters=filters, limit=limit)

    # ------------------------------------------------------------------
    # EDHREC DATA (Commander/EDH rankings and metadata)
    # ------------------------------------------------------------------

    def get_edhrec_data(self, limit: int = 1000, filters: dict | None = None) -> list[dict]:
        """Fetch EDHREC ranking data."""
        return self.get_records(f"{self.db_name}.edhrec_data", filters=filters, limit=limit)

    def get_game_changers(self, limit: int = 500) -> list[dict]:
        """Get game-changer cards from EDHREC rankings."""
        return self.get_records(
            f"{self.db_name}.edhrec_data",
            filters={"game_changer": True},
            limit=limit,
        )

    def get_salty_cards(self, min_salt: float = 1.2, limit: int = 500) -> list[dict]:
        """Get salty/controversial cards from EDHREC rankings."""
        return self.get_records(
            f"{self.db_name}.edhrec_data",
            filters={"salt": {"$gte": min_salt}},
            limit=limit,
        )

    def get_top_cards_by_color(self, color: str, limit: int = 100) -> list[dict]:
        """Get top ranked cards for a specific color identity."""
        return self.get_records(
            f"{self.db_name}.edhrec_data",
            filters={"color_identity": color},
            limit=limit,
        )

    # ------------------------------------------------------------------
    # GUIDE DATA
    # ------------------------------------------------------------------

    @retry_on_transient_error()
    def get_guides(self, limit: int = 100) -> list[Guide]:
        """Get EDHREC guides with chapters and tags.

        Args:
            limit: Maximum number of guides to return.

        Returns:
            List of Guide model objects.
        """
        cache_key = f"guides:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        guides_coll = self._get_collection("edhrec", "guides")
        if guides_coll is None:
            return []

        pipeline = [
            {"$sample": {"size": limit}},
            {
                "$project": {
                    "title": 1,
                    "chapters": 1,
                    "tags": {
                        "$map": {
                            "input": {"$ifNull": ["$tags", []]},
                            "as": "t",
                            "in": "$$t.name",
                        }
                    },
                }
            },
        ]
        result: list[Guide] = []
        for doc in guides_coll.aggregate(pipeline):
            guide = self._convert_doc_to_model(doc, Guide)
            if guide is not None:
                result.append(guide)

        self._cache.set(cache_key, result)
        return result

    # =========================================================================
    # CARD ENRICHMENT METHODS
    # =========================================================================

    @retry_on_transient_error()
    def get_cards_enriched(
        self,
        filters: dict | None = None,
        limit: int = 100,
        skip: int = 0,
        lite: bool = False,
    ) -> list[CardWithMetadata]:
        """Get cards enriched with prices, legalities, rulings, and keywords.

        Args:
            filters: MongoDB query filter for cards collection
            limit: Maximum number of cards to return
            skip: Number of cards to skip (for pagination)
            lite: If True, skip expensive joins (prices, rulings) for faster queries

        Returns:
            List of CardWithMetadata with enrichment data populated
        """
        pipeline = self._build_card_enrichment_pipeline(filters or {}, limit, skip, lite=lite)
        try:
            docs = self.aggregate("mtg_json.cards", pipeline)
            return [
                model for d in docs
                if (model := self._convert_doc_to_model(d, CardWithMetadata)) is not None
            ]
        except Exception as e:
            logger.error("Error in get_cards_enriched: %s", e)
            return []

    @retry_on_transient_error()
    def get_cards_by_keyword_mechanic(self, keyword: str, limit: int = 100) -> list[CardWithMetadata]:
        """Get cards that have a specific keyword/mechanic."""
        return self.get_cards_enriched(filters={"keywords": keyword}, limit=limit)

    def _translate_card_filters(self, filters: dict) -> dict:
        """Translate custom filter keys to MongoDB queries for mtg_json.cards.

        mtg_json.cards stores many fields as JSON strings (colors, colorIdentity,
        keywords, etc.), so standard MongoDB array operators don't work directly.
        This method translates our generator filter syntax to valid queries.

        Supported filter keys:
            - name: exact name or {$in: [...]} filter (simple string field)
            - text_regex: regex on 'text' field
            - oracleText: backward-compat alias for text regex
            - colors / colorIdentity: filter by color identity (JSON string field)
            - keywords / keywords_regex: filter by keywords (JSON string field)
            - commander_legal: skipped (legalities in separate collection)
        """
        and_parts: list[dict] = []

        # --- Name filter (simple string field, pass through directly) ---
        name_filter = filters.get("name")
        if name_filter:
            and_parts.append({"name": name_filter})

        # --- Text filter ---
        text_regex = None
        if "oracleText" in filters:
            text_regex = (
                filters["oracleText"].get("$regex")
                if isinstance(filters["oracleText"], dict)
                else filters["oracleText"]
            )
        elif "text_regex" in filters:
            text_regex = filters["text_regex"]
        elif "text" in filters:
            text_val = filters["text"]
            text_regex = text_val.get("$regex") if isinstance(text_val, dict) else text_val
        if text_regex:
            opts = "i"
            if isinstance(filters.get("oracleText"), dict):
                opts = filters["oracleText"].get("$options", "i")
            and_parts.append({"text": {"$regex": text_regex, "$options": opts}})

        # --- Color identity filter ---
        # colorIdentity in mtg_json is a JSON string like '["W","U"]'
        ci = filters.get("colorIdentity") or filters.get("colors")
        if ci:
            if isinstance(ci, dict) and "$all" in ci:
                colors = ci["$all"]
            elif isinstance(ci, list):
                colors = ci
            else:
                colors = []
            for color in colors:
                and_parts.append({"colorIdentity": {"$regex": f'"{color}"'}})

        # --- Keywords filter ---
        kw = filters.get("keywords_regex") or filters.get("keywords")
        if kw:
            if isinstance(kw, str):
                and_parts.append({"keywords": {"$regex": kw, "$options": "i"}})
            elif isinstance(kw, dict) and "$regex" in kw:
                and_parts.append({"keywords": kw})

        # --- Commander legality: skip (in separate collection) ---
        # Generators should check is_commander_legal on the CardWithMetadata model

        # --- Rarity filter ---
        rarity = filters.get("rarity")
        if rarity:
            if isinstance(rarity, list):
                and_parts.append({"rarity": {"$in": [r.lower() for r in rarity]}})
            else:
                and_parts.append({"rarity": rarity.lower()})

        # --- Price filters: skip (prices in separate collection, filter in Python) ---
        # min_price_usd / max_price_usd are stripped here; generators should filter in code

        if not and_parts:
            return {}
        if len(and_parts) == 1:
            return and_parts[0]
        return {"$and": and_parts}

    def _build_card_enrichment_pipeline(
        self,
        filters: dict | None,
        limit: int,
        skip: int = 0,
        lite: bool = False,
    ) -> list[dict]:
        """Build aggregation pipeline for enriched card queries.

        Data schema (mtg_json database):
            - cards: camelCase fields; colors/colorIdentity/keywords/subtypes/supertypes
              are stored as JSON strings (e.g., '["W"]')
            - cardPrices: {uuid, price, date, currency, cardFinish, priceProvider}
              — many rows per card (different finishes/providers/dates)
            - cardLegalities: flat {uuid, commander: "Legal", modern: "Not Legal", ...}
            - cardRulings: {uuid, date, text}
        """
        # Pre-process filters: translate our custom filter keys to MongoDB queries
        processed_filters = self._translate_card_filters(filters or {})

        match_stage: dict = {"$match": processed_filters} if processed_filters else {"$match": {}}
        if skip > 0 and processed_filters:
            match_stage = {"$match": {"$and": [processed_filters, {"_id": {"$exists": True}}]}}
        elif skip > 0:
            match_stage = {"$match": {"_id": {"$exists": True}}}

        pipeline: list[dict] = [match_stage]

        if not lite:
            # Full mode: join prices, legalities, rulings (expensive)
            pipeline.extend([
                {
                    "$lookup": {
                        "from": "cardPrices",
                        "localField": "uuid",
                        "foreignField": "uuid",
                        "as": "price_docs",
                    }
                },
                {
                    "$addFields": {
                        "prices": {
                            "$arrayElemAt": [
                                {"$sortArray": {"input": "$price_docs", "sortBy": {"date": -1}}},
                                0,
                            ]
                        }
                    }
                },
                {
                    "$lookup": {
                        "from": "cardLegalities",
                        "localField": "uuid",
                        "foreignField": "uuid",
                        "as": "legality_docs",
                    }
                },
                {
                    "$addFields": {
                        "legalities_doc": {"$arrayElemAt": ["$legality_docs", 0]}
                    }
                },
                {
                    "$lookup": {
                        "from": "cardRulings",
                        "localField": "uuid",
                        "foreignField": "uuid",
                        "as": "ruling_docs",
                    }
                },
                {
                    "$addFields": {
                        "rulings": {
                            "$slice": [
                                {"$sortArray": {"input": "$ruling_docs", "sortBy": {"date": -1}}},
                                5,
                            ]
                        }
                    }
                },
            ])

            # Project to clean shape with full enrichment
            pipeline.append({
                "$project": {
                    "name": 1,
                    "uuid": 1,
                    "manaCost": 1,
                    "type": 1,
                    "text": 1,
                    "manaValue": 1,
                    "power": 1,
                    "toughness": 1,
                    "loyalty": 1,
                    "defense": 1,
                    "colors": 1,
                    "colorIdentity": 1,
                    "subtypes": 1,
                    "supertypes": 1,
                    "keywords": 1,
                    "layout": 1,
                    "side": 1,
                    "frame": 1,
                    "frameEffects": 1,
                    "edhrecRank": 1,
                    "edhrecSaltiness": 1,
                    "edhrecTags": 1,
                    "rarity": 1,
                    "producedMana": 1,
                    "prices": {
                        "$cond": {
                            "if": {"$ne": ["$prices", None]},
                            "then": {
                                "usd": {
                                    "$cond": {
                                        "if": {"$eq": ["$prices.currency", "USD"]},
                                        "then": {"$toDouble": "$prices.price"},
                                        "else": None,
                                    }
                                },
                                "lastUpdated": "$prices.date",
                            },
                            "else": None,
                        }
                    },
                    "legalities": {
                        "$cond": {
                            "if": {"$ne": ["$legalities_doc", None]},
                            "then": {
                                "commander": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.commander", "Not Legal"]}
                                },
                                "legacy": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.legacy", "Not Legal"]}
                                },
                                "modern": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.modern", "Not Legal"]}
                                },
                                "vintage": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.vintage", "Not Legal"]}
                                },
                                "standard": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.standard", "Not Legal"]}
                                },
                                "pioneer": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.pioneer", "Not Legal"]}
                                },
                                "pauper": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.pauper", "Not Legal"]}
                                },
                                "brawl": {
                                    "$toLower": {"$ifNull": ["$legalities_doc.brawl", "Not Legal"]}
                                },
                            },
                            "else": {},
                        }
                    },
                    "rulings": {
                        "$map": {
                            "input": "$rulings",
                            "as": "r",
                            "in": {
                                "uuid": {"$ifNull": ["$$r.uuid", ""]},
                                "date": "$$r.date",
                                "text": "$$r.text",
                                "source": {"$ifNull": ["$$r.source", "official"]},
                            },
                        }
                    },
                }
            })
        else:
            # Lite mode: just basic card fields, no joins
            pipeline.append({
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "uuid": 1,
                    "manaCost": 1,
                    "type": 1,
                    "text": 1,
                    "manaValue": 1,
                    "power": 1,
                    "toughness": 1,
                    "loyalty": 1,
                    "defense": 1,
                    "colors": 1,
                    "colorIdentity": 1,
                    "subtypes": 1,
                    "supertypes": 1,
                    "keywords": 1,
                    "layout": 1,
                    "side": 1,
                    "rarity": 1,
                    "producedMana": 1,
                    "edhrecRank": 1,
                    "edhrecSaltiness": 1,
                    "edhrecTags": 1,
                }
            })

        if skip > 0:
            pipeline.append({"$skip": skip})
        pipeline.append({"$sample": {"size": limit}})
        pipeline.append({"$limit": limit})

        return pipeline

    # =========================================================================
    # COMBO ENRICHMENT METHODS
    # =========================================================================

    def _build_combo_pipeline(self, filters: dict | None, limit: int) -> list[dict]:
        """Build aggregation pipeline for combos (no card lookup — that's done in Python).

        We can't use $lookup across databases (commander_spellbook → mtg_json),
        so we fetch combos first, then enrich with card data in get_combos_enriched.
        """
        match_filter: dict = {"status": "OK"}
        if filters:
            match_filter.update(filters)

        return [
            {"$match": match_filter},
            {"$sample": {"size": limit}},
            # Transform uses from CSB shape to ComboCard shape
            {
                "$addFields": {
                    "uses": {
                        "$map": {
                            "input": "$uses",
                            "as": "u",
                            "in": {
                                "name": "$$u.card.name",
                                "uuid": "$$u.card.oracleId",
                                "quantity": "$$u.quantity",
                                "isCommander": "$$u.mustBeCommander",
                                "zone": {
                                    "$switch": {
                                        "branches": [
                                            {"case": {"$in": ["H", "$$u.zoneLocations"]}, "then": "hand"},
                                            {"case": {"$in": ["G", "$$u.zoneLocations"]}, "then": "graveyard"},
                                            {"case": {"$in": ["L", "$$u.zoneLocations"]}, "then": "library"},
                                            {"case": {"$in": ["C", "$$u.zoneLocations"]}, "then": "command_zone"},
                                        ],
                                        "default": "battlefield",
                                    }
                                },
                            },
                        }
                    }
                }
            },
            {
                "$addFields": {
                    "produces": {
                        "$map": {
                            "input": "$produces",
                            "as": "p",
                            "in": {
                                "description": "$$p.feature.name",
                                "infinite": {"$eq": ["$$p.feature.status", "S"]},
                                "mana": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "mana",
                                        "options": "i",
                                    }
                                },
                                "damage": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "damage",
                                        "options": "i",
                                    }
                                },
                                "tokens": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "token",
                                        "options": "i",
                                    }
                                },
                                "draw": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "draw",
                                        "options": "i",
                                    }
                                },
                                "mill": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "mill",
                                        "options": "i",
                                    }
                                },
                                "life_gain": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "life.*gain|gain.*life",
                                        "options": "i",
                                    }
                                },
                                "life_loss": {
                                    "$regexMatch": {
                                        "input": "$$p.feature.name",
                                        "regex": "life.*loss|loss.*life|damage",
                                        "options": "i",
                                    }
                                },
                            },
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "id": {"$toString": "$_id"},
                    "name": 1,
                    "description": 1,
                    "notes": 1,
                    "features": 1,
                    "produces": 1,
                    "requires": 1,
                    "mana_needed": "$manaNeeded",
                    "mana_value_needed": "$manaValueNeeded",
                    "easy_prerequisites": "$easyPrerequisites",
                    "notable_prerequisites": "$notablePrerequisites",
                    "popularity": 1,
                    "bracket_tag": "$bracketTag",
                    "uses": 1,
                }
            },
        ]

    @retry_on_transient_error()
    def get_combos_enriched(
        self,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[ComboWithCards]:
        """Get combos with fully enriched card details for each piece.

        Fetches combos from commander_spellbook.variants, then looks up card
        details from mtg_json.cards by name (can't use $lookup across databases).

        Args:
            filters: Additional filters for commander_spellbook.variants
            limit: Maximum number of combos to return

        Returns:
            List of ComboWithCards with enriched CardWithMetadata for each piece
        """
        pipeline = self._build_combo_pipeline(filters, limit)
        try:
            raw_combos = self.aggregate("commander_spellbook.variants", pipeline)
        except Exception as e:
            logger.error("Error in get_combos_enriched: %s", e)
            return []

        if not raw_combos:
            return []

        # Collect unique card names from all combos
        all_card_names: set[str] = set()
        for combo_doc in raw_combos:
            for use in combo_doc.get("uses", []):
                name = use.get("name", "")
                if name:
                    all_card_names.add(name)

        # Batch look up card data from mtg_json.cards
        card_lookup = self._batch_lookup_cards_by_name(list(all_card_names))

        # Build ComboWithCards objects
        results: list[ComboWithCards] = []
        for combo_doc in raw_combos:
            combo = self._convert_doc_to_model(combo_doc, ComboWithCards)
            if combo is None:
                continue
            combo.cards = [
                card_lookup.get(use.name)
                for use in (combo.uses or [])
                if use.name in card_lookup
            ]
            results.append(combo)

        return results

    # =========================================================================
    # COMMANDER ENRICHMENT METHODS
    # =========================================================================

    def _build_commander_pipeline(self, filters: dict | None, limit: int) -> list[dict]:
        """Build aggregation pipeline for commanders.

        edhrec.commanders already has card data embedded (oracle_text, mana_cost,
        etc.), so no $lookup is needed. We just need to reshape the data to match
        CommanderWithTags.
        """
        match_filter: dict = filters or {}

        return [
            {"$match": match_filter},
            {"$sample": {"size": limit}},
            {
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "colorIdentity": "$color_identity",
                    "tags": {"$ifNull": ["$tags", []]},
                    "numDecks": {"$ifNull": ["$num_decks", 0]},
                    "salt": {"$ifNull": ["$salt", 0]},
                    "avgDeckRank": None,
                    "cardUuid": {"$ifNull": ["$oracle_id", ""]},
                    # Embedded card details for CommanderWithTags.card_details
                    "card_details": {
                        "name": "$name",
                        "manaCost": "$mana_cost",
                        "type": "$type",
                        "text": "$oracle_text",
                        "power": "$power",
                        "toughness": "$toughness",
                        "colorIdentity": "$color_identity",
                        "edhrecRank": "$rank",
                    },
                }
            },
        ]

    @retry_on_transient_error()
    def get_commanders_enriched(
        self,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[CommanderWithTags]:
        """Get commanders with EDHREC tags and enriched card details.

        Args:
            filters: Additional filters for edhrec.commanders
            limit: Maximum number of commanders to return

        Returns:
            List of CommanderWithTags with card_details populated
        """
        pipeline = self._build_commander_pipeline(filters, limit)
        try:
            docs = self.aggregate("edhrec.commanders", pipeline)
            return [CommanderWithTags(**doc) for doc in docs]
        except Exception as e:
            logger.error("Error in get_commanders_enriched: %s", e)
            return []

    # =========================================================================
    # LOOKUP METHODS
    # =========================================================================

    @retry_on_transient_error()
    def get_rulings_for_cards(self, card_names: list[str]) -> list[Ruling]:
        """Get rulings for multiple cards by name."""
        if not card_names:
            return []

        cache_key = f"rulings:{','.join(sorted(card_names))}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Get UUIDs for card names
        try:
            cards_coll = self._get_collection("mtg_json", "cards")
            uuids = [
                doc["uuid"]
                for doc in cards_coll.find({"name": {"$in": card_names}}, {"uuid": 1})
                if doc.get("uuid")
            ]
        except Exception as e:
            logger.warning("Error looking up card UUIDs: %s", e)
            return []

        if not uuids:
            return []

        rulings: list[Ruling] = []

        # Get rulings from mtg_json.cardRulings
        try:
            rulings_coll = self._get_collection("mtg_json", "cardRulings")
            for doc in rulings_coll.find({"uuid": {"$in": uuids}}):
                for ruling in doc.get("rulings", []):
                    rulings.append(Ruling(
                        uuid=ruling.get("uuid", ""),
                        date=ruling.get("date") or None,
                        text=ruling.get("text", ""),
                        source="official",
                    ))
        except Exception as e:
            logger.warning("Error fetching rulings: %s", e)

        # Also check scryfall.oracle_cards
        try:
            scryfall_coll = self._get_collection("scryfall", "oracle_cards")
            for doc in scryfall_coll.find(
                {"oracle_id": {"$in": uuids}}, {"rulings": 1, "oracle_id": 1}
            ):
                for ruling in doc.get("rulings", []):
                    rulings.append(Ruling(
                        uuid=ruling.get("oracle_id", ""),
                        date=ruling.get("published_at") or None,
                        text=ruling.get("comment", ""),
                        source="scryfall",
                    ))
        except Exception as e:
            logger.warning("Error fetching Scryfall rulings: %s", e)

        self._cache.set(cache_key, rulings)
        return rulings

    @retry_on_transient_error()
    def get_prices_for_cards(self, card_names: list[str]) -> dict[str, PriceData]:
        """Get latest prices for multiple cards by name."""
        if not card_names:
            return {}

        cache_key = f"prices:{','.join(sorted(card_names))}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Get UUIDs for card names
        try:
            cards_coll = self._get_collection("mtg_json", "cards")
            uuid_to_name: dict[str, str] = {
                doc["uuid"]: doc["name"]
                for doc in cards_coll.find({"name": {"$in": card_names}}, {"uuid": 1, "name": 1})
                if doc.get("uuid")
            }
        except Exception as e:
            logger.warning("Error looking up card UUIDs: %s", e)
            return {}

        if not uuid_to_name:
            return {}

        # Get prices by UUID
        result: dict[str, PriceData] = {}
        try:
            prices_coll = self._get_collection("mtg_json", "cardPrices")
            for doc in prices_coll.find({"uuid": {"$in": list(uuid_to_name.keys())}}):
                price_data = PriceData(
                    usd=doc.get("usd"),
                    usd_foil=doc.get("usd_foil"),
                    eur=doc.get("eur"),
                    eur_foil=doc.get("eur_foil"),
                    tix=doc.get("tix"),
                    paper=doc.get("paper"),
                    last_updated=doc.get("lastUpdated"),
                )
                card_name = uuid_to_name.get(doc["uuid"], doc["uuid"])
                result[card_name] = price_data
        except Exception as e:
            logger.warning("Error fetching prices: %s", e)

        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_legalities_for_cards(self, card_names: list[str]) -> dict[str, CardLegalities]:
        """Get legalities for multiple cards by name."""
        if not card_names:
            return {}

        cache_key = f"legalities:{','.join(sorted(card_names))}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Get UUIDs for card names
        try:
            cards_coll = self._get_collection("mtg_json", "cards")
            uuid_to_name: dict[str, str] = {
                doc["uuid"]: doc["name"]
                for doc in cards_coll.find({"name": {"$in": card_names}}, {"uuid": 1, "name": 1})
                if doc.get("uuid")
            }
        except Exception as e:
            logger.warning("Error looking up card UUIDs: %s", e)
            return {}

        if not uuid_to_name:
            return {}

        # Get legalities by UUID
        result: dict[str, CardLegalities] = {}
        try:
            legalities_coll = self._get_collection("mtg_json", "cardLegalities")
            for doc in legalities_coll.find({"uuid": {"$in": list(uuid_to_name.keys())}}):
                legalities = [
                    Legality(format=fmt, status=status)
                    for fmt, status in doc.get("legalities", {}).items()
                ]
                card_legalities = CardLegalities(card_uuid=doc["uuid"], legalities=legalities)
                card_name = uuid_to_name.get(doc["uuid"], doc["uuid"])
                result[card_name] = card_legalities
        except Exception as e:
            logger.warning("Error fetching legalities: %s", e)

        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_keyword_taxonomy(self) -> dict[str, list[str]]:
        """Get all unique keywords with their descriptions."""
        cache_key = "keyword_taxonomy"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        result: dict[str, list[str]] = {}
        try:
            keywords_coll = self._get_collection("mtg_json", "keywords")
            for doc in keywords_coll.find():
                keyword = doc.get("keyword", "")
                description = doc.get("description", "")
                if keyword:
                    result[keyword] = [description] if description else []
        except Exception as e:
            logger.warning("Error fetching keyword taxonomy: %s", e)

        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_archetype_data(self) -> list[Archetype]:
        """Get all deck archetypes."""
        cache_key = "archetype_data"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        result: list[Archetype] = []
        try:
            archetypes_coll = self._get_collection("mtg_archetypes", "archetypes")
            result = [Archetype(**doc) for doc in archetypes_coll.find()]
        except Exception as e:
            logger.warning("Error fetching archetype data: %s", e)

        self._cache.set(cache_key, result)
        return result

    # =========================================================================
    # ANALYTICS METHODS
    # =========================================================================

    @retry_on_transient_error()
    def get_top_cards_by_edhrec_rank(
        self,
        color_identity: list[str],
        limit: int = 50,
    ) -> list[CardWithMetadata]:
        """Get top cards by EDHREC rank for a color identity."""
        filters = {
            "colorIdentity": {"$all": color_identity},
            "edhrecRank": {"$ne": None},
        }
        return self.get_cards_enriched(filters=filters, limit=limit)

    @retry_on_transient_error()
    def get_budget_alternatives(
        self,
        expensive_card: str,
        max_price: float,
        limit: int = 10,
    ) -> list[CardWithMetadata]:
        """Find budget alternatives for an expensive card."""
        # Get the expensive card's keywords and color identity
        card = self.get_card_by_name(expensive_card)
        if not card:
            return []

        keywords = card.keywords or []
        color_identity = card.color_identity or []

        pipeline: list[dict] = [
            {
                "$match": {
                    "keywords": {"$in": keywords} if keywords else {"$exists": True},
                    "colorIdentity": {"$in": color_identity} if color_identity else {"$exists": True},
                    "name": {"$ne": expensive_card},
                }
            },
            {
                "$lookup": {
                    "from": "cardPrices",
                    "localField": "uuid",
                    "foreignField": "uuid",
                    "as": "price_docs",
                }
            },
            {"$addFields": {"min_price": {"$min": "$price_docs.usd"}}},
            {"$match": {"min_price": {"$lte": max_price, "$ne": None}}},
            {"$sort": {"min_price": 1, "edhrecRank": 1}},
            {"$limit": limit},
        ]

        try:
            docs = self.aggregate("mtg_json.cards", pipeline)
            return [
                model for d in docs
                if (model := self._convert_doc_to_model(d, CardWithMetadata)) is not None
            ]
        except Exception as e:
            logger.error("Error in get_budget_alternatives: %s", e)
            return []

    @retry_on_transient_error()
    def get_synergy_partners(
        self,
        card_name: str,
        limit: int = 20,
    ) -> list[CardWithMetadata]:
        """Find cards that appear in combos with the given card."""
        pipeline: list[dict] = [
            {"$match": {"status": "OK"}},
            {"$unwind": "$uses"},
            {"$match": {"uses.card.name": card_name}},
            {"$unwind": "$uses"},
            {"$match": {"uses.card.name": {"$ne": card_name}}},
            {
                "$group": {
                    "_id": "$uses.card.name",
                    "count": {"$sum": 1},
                    "card_data": {"$first": "$uses.card"},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "cards",
                    "localField": "_id",
                    "foreignField": "name",
                    "as": "card_details",
                }
            },
            {"$addFields": {"card_details": {"$arrayElemAt": ["$card_details", 0]}}},
            {"$replaceRoot": {"newRoot": "$card_details"}},
        ]

        try:
            docs = self.aggregate("commander_spellbook.variants", pipeline)
            return [
                model for d in docs
                if (model := self._convert_doc_to_model(d, CardWithMetadata)) is not None
            ]
        except Exception as e:
            logger.error("Error in get_synergy_partners: %s", e)
            return []

    @retry_on_transient_error()
    def get_commander_staples(
        self,
        color_identity: list[str],
        min_decks: int,
        limit: int = 50,
    ) -> list[CardWithMetadata]:
        """Get commander staples for a color identity."""
        # Get top commanders for color identity
        try:
            commanders_coll = self._get_collection("edhrec", "commanders")
            commander_uuids = [
                doc["cardUuid"]
                for doc in commanders_coll.find(
                    {
                        "colorIdentity": {"$all": color_identity},
                        "numDecks": {"$gte": min_decks},
                    },
                    {"cardUuid": 1},
                ).limit(20)
                if doc.get("cardUuid")
            ]
        except Exception as e:
            logger.warning("Error fetching commanders for staples: %s", e)
            return []

        if not commander_uuids:
            # Fallback: get cards by color identity with EDHREC rank
            filters = {
                "colorIdentity": {"$all": color_identity},
                "edhrecRank": {"$ne": None},
            }
            return self.get_cards_enriched(filters=filters, limit=limit)

        # Get cards commonly played with these commanders
        # This would need EDHREC deck data; simplified for now
        filters = {
            "colorIdentity": {"$all": color_identity},
            "edhrecRank": {"$ne": None},
        }
        return self.get_cards_enriched(filters=filters, limit=limit)

    @retry_on_transient_error()
    def get_format_legalities(
        self,
        format_name: str,
        limit: int = 100,
    ) -> list[CardWithMetadata]:
        """Get cards legal in a specific format."""
        filters = {f"legalities.{format_name.lower()}": "legal"}
        return self.get_cards_enriched(filters=filters, limit=limit)

    def calculate_color_identity(
        self,
        mana_cost: str | None,
        text: str | None,
        color_indicator: list[str] | None,
    ) -> list[str]:
        """Calculate color identity from mana cost, rules text, and color indicator."""
        colors: set[str] = set()

        # From color indicator
        if color_indicator:
            colors.update(color_indicator)

        # From mana cost
        if mana_cost:
            symbols = _re.findall(r"\{([^}]+)\}", mana_cost)
            color_map = {"W": "W", "U": "U", "B": "B", "R": "R", "G": "G"}
            for sym in symbols:
                if sym in color_map:
                    colors.add(color_map[sym])
                elif "/" in sym:  # Hybrid mana
                    for c in sym.split("/"):
                        if c in color_map:
                            colors.add(color_map[c])
                elif sym == "P":  # Phyrexian
                    # Phyrexian mana can be any color - would need context
                    pass

        # From mana symbols in rules text (e.g., "{T}: Add {G}")
        if text:
            symbols = _re.findall(r"\{([WUBRG])\}", text)
            colors.update(symbols)

        return sorted(colors)

    @retry_on_transient_error()
    def search_cards_text(
        self,
        regex: str,
        filters: dict | None = None,
        limit: int = 100,
    ) -> list[CardWithMetadata]:
        """Search cards by regex on oracle text."""
        match_filter: dict = {"oracleText": {"$regex": regex, "$options": "i"}}
        if filters:
            match_filter.update(filters)
        return self.get_cards_enriched(filters=match_filter, limit=limit)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _batch_lookup_cards_by_name(self, names: list[str]) -> dict[str, CardWithMetadata]:
        """Batch lookup cards by name from mtg_json.cards.

        Args:
            names: List of card names to look up

        Returns:
            Dict mapping card name to CardWithMetadata
        """
        if not names:
            return {}

        pipeline: list[dict] = [
            {"$match": {"name": {"$in": names}}},
            {"$group": {"_id": "$name", "doc": {"$first": "$$ROOT"}}},
        ]

        result: dict[str, CardWithMetadata] = {}
        try:
            for group in self.aggregate("mtg_json.cards", pipeline):
                doc = group["doc"]
                doc.pop("_id", None)
                model = self._convert_doc_to_model(doc, CardWithMetadata)
                if model is not None:
                    result[group["_id"]] = model
        except Exception as e:
            logger.warning("Error batch looking up cards: %s", e)

        return result

    def verify_indexes(self) -> None:
        """Verify and create required indexes for optimal query performance."""
        if self._indexes_verified:
            return

        with self._lock:
            if self._indexes_verified:
                return

            logger.info("Verifying MongoDB indexes...")
            for coll_name, indexes in self.REQUIRED_INDEXES.items():
                try:
                    parts = coll_name.split(".", 1)
                    db_name, coll_name_only = parts
                    coll = self._get_collection(db_name, coll_name_only)
                    existing_indexes = {idx["name"]: idx for idx in coll.list_indexes()}
                    for index_spec in indexes:
                        index_name = "_".join(f"{k}_{v}" for k, v in index_spec)
                        if index_name not in existing_indexes:
                            coll.create_index(index_spec, background=True, name=index_name)
                            logger.info("Created index %s on %s", index_name, coll_name)
                except Exception as e:
                    logger.warning("Could not verify/create indexes for %s: %s", coll_name, e)

            self._indexes_verified = True
            logger.info("Index verification complete")

    def _convert_doc_to_model(
        self,
        doc: dict,
        model_class: type[T],
    ) -> T | None:
        """Convert MongoDB doc to Pydantic model, pre-parsing JSON string arrays."""
        try:
            # mtg_json stores array fields as JSON strings like '["W","U"]'
            if model_class.__name__ in ("CardWithMetadata", "Card", "CommanderWithTags", "Commander"):
                import json
                for field in ["colors", "colorIdentity", "keywords", "subtypes", "supertypes", "frameEffects"]:
                    if field in doc and isinstance(doc[field], str):
                        try:
                            doc[field] = json.loads(doc[field])
                        except (json.JSONDecodeError, TypeError):
                            doc[field] = []
            return model_class(**doc)
        except Exception as e:
            logger.warning(
                "Failed to convert doc to %s: %s",
                model_class.__name__ if hasattr(model_class, "__name__") else str(model_class),
                e,
            )
            return None
