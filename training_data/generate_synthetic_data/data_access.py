"""Unified Data Access Layer for MTG MongoDB Collections.

Provides a single facade class (MTGDataAccess) with typed methods for all
MongoDB operations, using aggregation pipelines for efficient joins.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from functools import lru_cache, wraps
from typing import Any, Callable, TypeVar, cast

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, OperationFailure, ServerSelectionTimeoutError

from .domain_models import (
    Archetype,
    Article,
    CardLegalities,
    CardWithMetadata,
    ComboWithCards,
    CommanderWithTags,
    GameState,
    GlossaryTerm,
    Guide,
    Keyword,
    PriceData,
    Ruling,
    Rule,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_transient_error(max_retries: int = 3, base_delay: float = 0.5):
    """Decorator for retrying transient MongoDB errors with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
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
                            f"Transient error in {func_name} (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All retries exhausted for {func_name}: {e}")
            raise last_exception
        return wrapper
    return decorator


class LRUCacheWithTTL:
    """Thread-safe LRU cache with TTL support."""

    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return "|".join(key_parts)

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    self._hits += 1
                    return value
                else:
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self.maxsize:
                # Remove oldest entry (simple LRU approximation)
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


class MTGDataAccess:
    """Unified data access layer for all MTG MongoDB collections.

    Provides typed, high-level methods for querying cards, combos, commanders,
    articles, guides, rules, and other MTG data with pre-built aggregation
    pipelines for efficient joins.

    Usage:
        with MTGDataAccess(uri, username, password) as db:
            cards = db.get_cards_enriched({"colorIdentity": ["W", "U"]}, limit=100)
            combos = db.get_combos_enriched(limit=50)
    """

    # Required collections for full functionality
    REQUIRED_COLLECTIONS = {
        "mtg_json": ["cards", "cardPrices", "cardLegalities", "cardRulings", "keywords"],
        "commander_spellbook": ["variants"],
        "edhrec": ["commanders", "articles", "guides", "game-changers"],
        "mtg_archetypes": ["archetypes"],
        "mtg_training": ["games"],
        "mtg_rules": ["rules", "glossary"],
        "scryfall": ["oracle_cards"],
    }

    # Indexes to verify/create on startup
    REQUIRED_INDEXES = {
        "mtg_json.cards": [
            [("uuid", 1)],
            [("name", 1)],
            [("colorIdentity", 1)],
            [("keywords", 1)],
            [("edhrecRank", 1)],
            [("cmc", 1)],
        ],
        "mtg_json.cardPrices": [[("uuid", 1)]],
        "mtg_json.cardLegalities": [[("uuid", 1)]],
        "mtg_json.cardRulings": [[("uuid", 1)]],
        "commander_spellbook.variants": [
            [("status", 1)],
            [("uses.card.name", 1)],
            [("produces.feature.name", 1)],
        ],
        "edhrec.commanders": [
            [("cardUuid", 1)],
            [("numDecks", -1)],
            [("colorIdentity", 1)],
        ],
        "edhrec.articles": [[("publishedDate", -1)]],
        "edhrec.guides": [[("tags", 1)]],
        "mtg_archetypes.archetypes": [[("name", 1)]],
        "mtg_training.games": [[("turn", 1)]],
        "mtg_rules.rules": [[("ruleNumber", 1)]],
        "mtg_rules.glossary": [[("term", 1)]],
        "scryfall.oracle_cards": [[("name", 1)], [("oracle_id", 1)]],
    }

    def __init__(
        self,
        uri: str = "mongodb://server.home:27017",
        username: str = "root",
        password: str = "whatever",
        database: str = "mtg_json",
        auth_source: str = "admin",
        max_pool_size: int = 50,
        min_pool_size: int = 5,
        server_selection_timeout_ms: int = 30000,
        connect_timeout_ms: int = 30000,
        socket_timeout_ms: int = 30000,
    ):
        """Initialize MTGDataAccess with MongoDB connection.

        Args:
            uri: MongoDB connection URI
            username: Database username
            password: Database password
            database: Default database name (mtg_json)
            auth_source: Authentication database
            max_pool_size: Maximum connection pool size
            min_pool_size: Minimum connection pool size
            server_selection_timeout_ms: Server selection timeout
            connect_timeout_ms: Connection timeout
            socket_timeout_ms: Socket timeout
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.default_db_name = database
        self.auth_source = auth_source
        self.max_pool_size = max_pool_size
        self.min_pool_size = min_pool_size
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self.connect_timeout_ms = connect_timeout_ms
        self.socket_timeout_ms = socket_timeout_ms

        self._client: MongoClient | None = None
        self._databases: dict[str, Database] = {}
        self._collections: dict[str, Collection] = {}
        self._indexes_verified = False
        self._cache = LRUCacheWithTTL(maxsize=1000, ttl=300)
        self._lock = threading.RLock()

    def __enter__(self) -> MTGDataAccess:
        """Context manager entry - establishes connection."""
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> None:
        """Context manager exit - closes connection."""
        self.close()

    def connect(self) -> None:
        """Establish MongoDB connection with connection pooling."""
        with self._lock:
            if self._client is not None:
                return

            self._client = MongoClient(
                self.uri,
                username=self.username,
                password=self.password,
                authSource=self.auth_source,
                maxPoolSize=self.max_pool_size,
                minPoolSize=self.min_pool_size,
                serverSelectionTimeoutMS=self.server_selection_timeout_ms,
                connectTimeoutMS=self.connect_timeout_ms,
                socketTimeoutMS=self.socket_timeout_ms,
            )
            # Force connection to verify credentials
            self._client.admin.command("ping")
            logger.info("MongoDB connection established (pool size: %d-%d)", self.min_pool_size, self.max_pool_size)

    def close(self) -> None:
        """Close MongoDB connection."""
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
                self._databases.clear()
                self._collections.clear()
                self._indexes_verified = False
                logger.info("MongoDB connection closed")

    def _get_database(self, db_name: str) -> Database:
        """Get database instance, creating connection if needed."""
        if self._client is None:
            self.connect()
        assert self._client is not None

        if db_name not in self._databases:
            self._databases[db_name] = self._client[db_name]
        return self._databases[db_name]

    def _get_collection(self, db_name: str, collection_name: str) -> Collection | None:
        """Get collection instance, returning None if collection doesn't exist."""
        try:
            db = self._get_database(db_name)
            if collection_name not in db.list_collection_names():
                logger.warning("Collection %s.%s does not exist", db_name, collection_name)
                return None
            key = f"{db_name}.{collection_name}"
            if key not in self._collections:
                self._collections[key] = db[collection_name]
            return self._collections[key]
        except Exception as e:
            logger.warning("Failed to access collection %s.%s: %s", db_name, collection_name, e)
            return None

    def _get_collection_required(self, db_name: str, collection_name: str) -> Collection:
        """Get collection, raising if not available."""
        coll = self._get_collection(db_name, collection_name)
        if coll is None:
            raise RuntimeError(f"Required collection {db_name}.{collection_name} not available")
        return coll

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
                    db_name, coll_name_only = coll_name.split(".", 1)
                    coll = self._get_collection(db_name, coll_name_only)
                    if coll is None:
                        logger.warning("Skipping index creation for missing collection: %s", coll_name)
                        continue

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

    def health_check(self) -> bool:
        """Check MongoDB connection health."""
        try:
            if self._client is None:
                return False
            self._client.admin.command("ping")
            return True
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return False

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        logger.info("Cache cleared")

    def cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return self._cache.stats()

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
        pipeline = self._build_card_enrichment_pipeline(filters, limit, skip, lite=lite)
        cards_coll = self._get_collection("mtg_json", "cards")
        if cards_coll is None:
            logger.warning("mtg_json.cards collection not available, returning empty list")
            return []

        try:
            cursor = cards_coll.aggregate(pipeline, allowDiskUse=True)
            return [self._convert_doc_to_model(doc, CardWithMetadata) for doc in cursor if self._convert_doc_to_model(doc, CardWithMetadata) is not None]
        except Exception as e:
            logger.error("Error in get_cards_enriched: %s", e)
            return []

    @retry_on_transient_error()
    def get_card_by_name(self, name: str) -> CardWithMetadata | None:
        """Get a single enriched card by exact name."""
        cards = self.get_cards_enriched(filters={"name": name}, limit=1)
        return cards[0] if cards else None

    @retry_on_transient_error()
    def get_cards_by_keyword_mechanic(self, keyword: str, limit: int = 100) -> list[CardWithMetadata]:
        """Get cards that have a specific keyword/mechanic."""
        return self.get_cards_enriched(filters={"keywords": keyword}, limit=limit)

    @retry_on_transient_error()
    def get_cards_by_archetype(self, archetype: str, limit: int = 100) -> list[CardWithMetadata]:
        """Get cards associated with an archetype (via keywords/tags)."""
        # This would need archetype-to-keyword mapping; simplified for now
        return self.get_cards_enriched(filters={"keywords": {"$regex": archetype, "$options": "i"}}, limit=limit)

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
            text_regex = filters["oracleText"].get("$regex") if isinstance(filters["oracleText"], dict) else filters["oracleText"]
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
        self, filters: dict | None, limit: int, skip: int, lite: bool = False
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

        match_stage = {"$match": processed_filters} if processed_filters else {"$match": {}}
        if skip > 0 and processed_filters:
            match_stage = {"$match": {"$and": [processed_filters, {"_id": {"$exists": True}}]}}
        elif skip > 0:
            match_stage = {"$match": {"_id": {"$exists": True}}}

        pipeline: list[dict] = [match_stage]

        if not lite:
            # Full mode: join prices, legalities, rulings (expensive)
            pipeline.extend([
                {"$lookup": {"from": "cardPrices", "localField": "uuid", "foreignField": "uuid", "as": "price_docs"}},
                {"$addFields": {"prices": {"$arrayElemAt": [
                    {"$sortArray": {"input": "$price_docs", "sortBy": {"date": -1}}}, 0
                ]}}},
                {"$lookup": {"from": "cardLegalities", "localField": "uuid", "foreignField": "uuid", "as": "legality_docs"}},
                {"$addFields": {"legalities_doc": {"$arrayElemAt": ["$legality_docs", 0]}}},
                {"$lookup": {"from": "cardRulings", "localField": "uuid", "foreignField": "uuid", "as": "ruling_docs"}},
                {"$addFields": {"rulings": {"$slice": [
                    {"$sortArray": {"input": "$ruling_docs", "sortBy": {"date": -1}}}, 5
                ]}}},
            ])

            # Project to clean shape with full enrichment
            pipeline.append({"$project": {
                "name": 1, "uuid": 1,
                "manaCost": 1, "type": 1, "text": 1, "manaValue": 1,
                "power": 1, "toughness": 1, "loyalty": 1, "defense": 1,
                "colors": 1, "colorIdentity": 1,
                "subtypes": 1, "supertypes": 1, "keywords": 1,
                "layout": 1, "side": 1, "frame": 1, "frameEffects": 1,
                "edhrecRank": 1, "edhrecSaltiness": 1, "edhrecTags": 1, "rarity": 1, "producedMana": 1,
                "prices": {
                    "$cond": {
                        "if": {"$ne": ["$prices", None]},
                        "then": {
                            "usd": {"$cond": {"if": {"$eq": ["$prices.currency", "USD"]},
                                               "then": {"$toDouble": "$prices.price"}, "else": None}},
                            "lastUpdated": "$prices.date"
                        },
                        "else": None
                    }
                },
                "legalities": {
                    "$cond": {
                        "if": {"$ne": ["$legalities_doc", None]},
                        "then": {
                            "commander": {"$toLower": {"$ifNull": ["$legalities_doc.commander", "Not Legal"]}},
                            "legacy": {"$toLower": {"$ifNull": ["$legalities_doc.legacy", "Not Legal"]}},
                            "modern": {"$toLower": {"$ifNull": ["$legalities_doc.modern", "Not Legal"]}},
                            "vintage": {"$toLower": {"$ifNull": ["$legalities_doc.vintage", "Not Legal"]}},
                            "standard": {"$toLower": {"$ifNull": ["$legalities_doc.standard", "Not Legal"]}},
                            "pioneer": {"$toLower": {"$ifNull": ["$legalities_doc.pioneer", "Not Legal"]}},
                            "pauper": {"$toLower": {"$ifNull": ["$legalities_doc.pauper", "Not Legal"]}},
                            "brawl": {"$toLower": {"$ifNull": ["$legalities_doc.brawl", "Not Legal"]}},
                        },
                        "else": {}
                    }
                },
                "rulings": {"$map": {"input": "$rulings", "as": "r", "in": {
                    "uuid": {"$ifNull": ["$$r.uuid", ""]}, "date": "$$r.date",
                    "text": "$$r.text", "source": {"$ifNull": ["$$r.source", "official"]}
                }}},
            }})
        else:
            # Lite mode: just basic card fields, no joins
            pipeline.append({"$project": {
                "_id": 0,
                "name": 1, "uuid": 1,
                "manaCost": 1, "type": 1, "text": 1, "manaValue": 1,
                "power": 1, "toughness": 1, "loyalty": 1, "defense": 1,
                "colors": 1, "colorIdentity": 1,
                "subtypes": 1, "supertypes": 1, "keywords": 1,
                "layout": 1, "side": 1, "rarity": 1, "producedMana": 1,
                "edhrecRank": 1, "edhrecSaltiness": 1, "edhrecTags": 1,
            }})

        if skip > 0:
            pipeline.append({"$skip": skip})
        pipeline.append({"$sample": {"size": limit}})
        pipeline.append({"$limit": limit})

        return pipeline

    # =========================================================================
    # COMBO & COMMANDER METHODS
    # =========================================================================

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
        combos_coll = self._get_collection("commander_spellbook", "variants")
        if combos_coll is None:
            logger.warning("commander_spellbook.variants collection not available")
            return []

        try:
            raw_combos = list(combos_coll.aggregate(pipeline, allowDiskUse=True))
        except Exception as e:
            logger.error("Error fetching combos: %s", e)
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

        # Look up card data from mtg_json.cards by name (batch query)
        card_lookup: dict[str, CardWithMetadata] = {}
        if all_card_names:
            cards_coll = self._get_collection("mtg_json", "cards")
            if cards_coll is not None:
                try:
                    # Get unique cards by name (one per name)
                    pipeline = [
                        {"$match": {"name": {"$in": list(all_card_names)}}},
                        {"$group": {"_id": "$name", "doc": {"$first": "$$ROOT"}}},
                    ]
                    for group in cards_coll.aggregate(pipeline):
                        name = group["_id"]
                        doc = group["doc"]
                        # Remove _id from group doc to avoid conflicts
                        doc.pop("_id", None)
                        model = self._convert_doc_to_model(doc, CardWithMetadata)
                        if model is not None:
                            card_lookup[name] = model
                except Exception as e:
                    logger.warning("Error looking up cards: %s", e)

        # Build ComboWithCards objects
        results: list[ComboWithCards] = []
        for combo_doc in raw_combos:
            combo = self._convert_doc_to_model(combo_doc, ComboWithCards)
            if combo is None:
                continue
            # Attach enriched card data
            combo.cards = []
            for use in combo.uses:
                card = card_lookup.get(use.name)
                if card:
                    combo.cards.append(card)
            results.append(combo)

        return results

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
        commanders_coll = self._get_collection("edhrec", "commanders")
        if commanders_coll is None:
            logger.warning("edhrec.commanders collection not available")
            return []

        try:
            cursor = commanders_coll.aggregate(pipeline, allowDiskUse=True)
            return [CommanderWithTags(**doc) for doc in cursor]
        except Exception as e:
            logger.error("Error in get_commanders_enriched: %s", e)
            return []

    def _build_combo_pipeline(self, filters: dict | None, limit: int) -> list[dict]:
        """Build aggregation pipeline for combos (no card lookup — that's done in Python).

        We can't use $lookup across databases (commander_spellbook → mtg_json),
        so we fetch combos first, then enrich with card data in get_combos_enriched.
        """
        match_filter = {"status": "OK"}
        if filters:
            match_filter.update(filters)

        return [
            {"$match": match_filter},
            {"$sample": {"size": limit}},
            # Transform uses from CSB shape to ComboCard shape
            # CSB: {card: {name, oracleId, ...}, quantity, zoneLocations, mustBeCommander, ...}
            # ComboCard: {name, quantity, isCommander, zone}
            {"$addFields": {
                "uses": {
                    "$map": {
                        "input": "$uses",
                        "as": "u",
                        "in": {
                            "name": "$$u.card.name",
                            "uuid": "$$u.card.oracleId",
                            "quantity": "$$u.quantity",
                            "isCommander": "$$u.mustBeCommander",
                            "zone": {"$switch": {
                                "branches": [
                                    {"case": {"$in": ["H", "$$u.zoneLocations"]}, "then": "hand"},
                                    {"case": {"$in": ["G", "$$u.zoneLocations"]}, "then": "graveyard"},
                                    {"case": {"$in": ["L", "$$u.zoneLocations"]}, "then": "library"},
                                    {"case": {"$in": ["C", "$$u.zoneLocations"]}, "then": "command_zone"},
                                ],
                                "default": "battlefield"
                            }}
                        }
                    }
                }
            }},
            {"$addFields": {
                "produces": {
                    "$map": {
                        "input": "$produces",
                        "as": "p",
                        "in": {
                            "description": "$$p.feature.name",
                            "infinite": {"$eq": ["$$p.feature.status", "S"]},
                            "mana": {"$regexMatch": {"input": "$$p.feature.name", "regex": "mana", "options": "i"}},
                            "damage": {"$regexMatch": {"input": "$$p.feature.name", "regex": "damage", "options": "i"}},
                            "tokens": {"$regexMatch": {"input": "$$p.feature.name", "regex": "token", "options": "i"}},
                            "draw": {"$regexMatch": {"input": "$$p.feature.name", "regex": "draw", "options": "i"}},
                            "mill": {"$regexMatch": {"input": "$$p.feature.name", "regex": "mill", "options": "i"}},
                            "life_gain": {"$regexMatch": {"input": "$$p.feature.name", "regex": "life.*gain|gain.*life", "options": "i"}},
                            "life_loss": {"$regexMatch": {"input": "$$p.feature.name", "regex": "life.*loss|loss.*life|damage", "options": "i"}}
                        }
                    }
                }
            }},
            {"$project": {
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
            }}
        ]

    def _build_commander_pipeline(self, filters: dict | None, limit: int) -> list[dict]:
        """Build aggregation pipeline for commanders.

        edhrec.commanders already has card data embedded (oracle_text, mana_cost,
        etc.), so no $lookup is needed. We just need to reshape the data to match
        CommanderWithTags.
        """
        match_filter = filters or {}

        return [
            {"$match": match_filter},
            {"$sample": {"size": limit}},
            {"$project": {
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
                }
            }},
        ]

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

        # Get uuids for card names
        cards_coll = self._get_collection("mtg_json", "cards")
        if cards_coll is None:
            return []

        uuids = [doc["uuid"] for doc in cards_coll.find({"name": {"$in": card_names}}, {"uuid": 1})]
        if not uuids:
            return []

        # Get rulings from mtg_json.cardRulings
        rulings_coll = self._get_collection("mtg_json", "cardRulings")
        rulings = []
        if rulings_coll is not None:
            for doc in rulings_coll.find({"uuid": {"$in": uuids}}):
                for ruling in doc.get("rulings", []):
                    rulings.append(Ruling(
                        uuid=ruling.get("uuid", ""),
                        date=ruling.get("date", ""),
                        text=ruling.get("text", ""),
                        source="official"
                    ))

        # Also check scryfall.rulings
        scryfall_coll = self._get_collection("scryfall", "oracle_cards")
        if scryfall_coll is not None:
            for doc in scryfall_coll.find({"oracle_id": {"$in": uuids}}, {"rulings": 1, "oracle_id": 1}):
                for ruling in doc.get("rulings", []):
                    rulings.append(Ruling(
                        uuid=ruling.get("oracle_id", ""),
                        date=ruling.get("published_at", ""),
                        text=ruling.get("comment", ""),
                        source="scryfall"
                    ))

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

        cards_coll = self._get_collection("mtg_json", "cards")
        if cards_coll is None:
            return {}

        uuids = [doc["uuid"] for doc in cards_coll.find({"name": {"$in": card_names}}, {"uuid": 1, "name": 1})]
        if not uuids:
            return {}

        prices_coll = self._get_collection("mtg_json", "cardPrices")
        if prices_coll is None:
            return {}

        result = {}
        for doc in prices_coll.find({"uuid": {"$in": uuids}}):
            # Get latest price entry
            price_data = PriceData(
                usd=doc.get("usd"),
                usd_foil=doc.get("usd_foil"),
                eur=doc.get("eur"),
                eur_foil=doc.get("eur_foil"),
                tix=doc.get("tix"),
                paper=doc.get("paper"),
                last_updated=doc.get("lastUpdated")
            )
            # Find card name for this uuid
            card_name = next((c["name"] for c in cards_coll.find({"uuid": doc["uuid"]}, {"name": 1})), doc["uuid"])
            result[card_name] = price_data

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

        cards_coll = self._get_collection("mtg_json", "cards")
        if cards_coll is None:
            return {}

        uuids = [doc["uuid"] for doc in cards_coll.find({"name": {"$in": card_names}}, {"uuid": 1, "name": 1})]
        if not uuids:
            return {}

        legalities_coll = self._get_collection("mtg_json", "cardLegalities")
        if legalities_coll is None:
            return {}

        result = {}
        for doc in legalities_coll.find({"uuid": {"$in": uuids}}):
            legalities = [
                Legality(format=fmt, status=status)
                for fmt, status in doc.get("legalities", {}).items()
            ]
            card_legalities = CardLegalities(card_uuid=doc["uuid"], legalities=legalities)
            card_name = next((c["name"] for c in cards_coll.find({"uuid": doc["uuid"]}, {"name": 1})), doc["uuid"])
            result[card_name] = card_legalities

        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_keyword_taxonomy(self) -> dict[str, list[str]]:
        """Get all unique keywords with their descriptions."""
        cache_key = "keyword_taxonomy"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        keywords_coll = self._get_collection("mtg_json", "keywords")
        if keywords_coll is None:
            return {}

        result = {}
        for doc in keywords_coll.find():
            keyword = doc.get("keyword", "")
            description = doc.get("description", "")
            if keyword:
                result[keyword] = [description] if description else []

        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_archetype_data(self) -> list[Archetype]:
        """Get all deck archetypes."""
        cache_key = "archetype_data"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        archetypes_coll = self._get_collection("mtg_archetypes", "archetypes")
        if archetypes_coll is None:
            return []

        result = [Archetype(**doc) for doc in archetypes_coll.find()]
        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_articles(self, limit: int = 100) -> list[Article]:
        """Get EDHREC articles."""
        cache_key = f"articles:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        articles_coll = self._get_collection("edhrec", "articles")
        if articles_coll is None:
            return []

        pipeline = [
            {"$sample": {"size": limit}},
            {"$sort": {"publishedDate": -1}},
            {"$project": {
                "title": 1,
                "content": 1,
                "excerpt": 1,
                "tags": {"$map": {"input": "$tags", "as": "t", "in": "$$t.name"}},
                "author": "$author.name",
                "publishedDate": 1,
                "url": 1,
            }},
        ]
        result = [Article(**doc) for doc in articles_coll.aggregate(pipeline)]
        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_guides(self, limit: int = 100) -> list[Guide]:
        """Get EDHREC guides."""
        cache_key = f"guides:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        guides_coll = self._get_collection("edhrec", "guides")
        if guides_coll is None:
            return []

        pipeline = [
            {"$sample": {"size": limit}},
            {"$project": {
                "title": 1,
                "chapters": 1,
                "tags": {"$map": {"input": "$tags", "as": "t", "in": "$$t.name"}},
            }},
        ]
        result = [Guide(**doc) for doc in guides_coll.aggregate(pipeline)]
        self._cache.set(cache_key, result)
        return result

    @retry_on_transient_error()
    def get_game_states(self, limit: int = 100) -> list[GameState]:
        """Get training game states."""
        games_coll = self._get_collection("mtg_training", "games")
        if games_coll is None:
            return []

        pipeline = [{"$sample": {"size": limit}}]
        return [GameState(**doc) for doc in games_coll.aggregate(pipeline)]

    @retry_on_transient_error()
    def get_rules(self, filters: dict | None = None, limit: int = 100) -> list[Rule]:
        """Get MTG comprehensive rules."""
        rules_coll = self._get_collection("mtg_rules", "rules")
        if rules_coll is None:
            return []

        pipeline: list[dict] = []
        if filters:
            pipeline.append({"$match": filters})
        pipeline.append({"$sample": {"size": limit}})
        return [Rule(**doc) for doc in rules_coll.aggregate(pipeline)]

    @retry_on_transient_error()
    def get_glossary(self, limit: int = 100) -> list[GlossaryTerm]:
        """Get MTG glossary terms."""
        cache_key = f"glossary:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        glossary_coll = self._get_collection("mtg_rules", "glossary")
        if glossary_coll is None:
            return []

        pipeline = [{"$sample": {"size": limit}}]
        result = [GlossaryTerm(**doc) for doc in glossary_coll.aggregate(pipeline)]
        self._cache.set(cache_key, result)
        return result

    # =========================================================================
    # ANALYTICS METHODS
    # =========================================================================

    @retry_on_transient_error()
    def get_top_cards_by_edhrec_rank(
        self, color_identity: list[str], limit: int = 50
    ) -> list[CardWithMetadata]:
        """Get top cards by EDHREC rank for a color identity."""
        filters = {"colorIdentity": {"$all": color_identity}, "edhrecRank": {"$ne": None}}
        return self.get_cards_enriched(filters=filters, limit=limit)

    @retry_on_transient_error()
    def get_budget_alternatives(
        self, expensive_card: str, max_price: float, limit: int = 10
    ) -> list[CardWithMetadata]:
        """Find budget alternatives for an expensive card."""
        # Get the expensive card's keywords and color identity
        card = self.get_card_by_name(expensive_card)
        if not card:
            return []

        keywords = card.keywords or []
        color_identity = card.color_identity or []

        pipeline = [
            {"$match": {
                "keywords": {"$in": keywords} if keywords else {"$exists": True},
                "colorIdentity": {"$in": color_identity} if color_identity else {"$exists": True},
                "name": {"$ne": expensive_card}
            }},
            {"$lookup": {
                "from": "cardPrices",
                "localField": "uuid",
                "foreignField": "uuid",
                "as": "price_docs"
            }},
            {"$addFields": {
                "min_price": {"$min": "$price_docs.usd"}
            }},
            {"$match": {"min_price": {"$lte": max_price, "$ne": None}}},
            {"$sort": {"min_price": 1, "edhrecRank": 1}},
            {"$limit": limit}
        ]

        cards_coll = self._get_collection("mtg_json", "cards")
        if cards_coll is None:
            return []

        try:
            cursor = cards_coll.aggregate(pipeline, allowDiskUse=True)
            return [CardWithMetadata(**doc) for doc in cursor]
        except Exception as e:
            logger.error("Error in get_budget_alternatives: %s", e)
            return []

    @retry_on_transient_error()
    def get_synergy_partners(self, card_name: str, limit: int = 20) -> list[CardWithMetadata]:
        """Find cards that appear in combos with the given card."""
        pipeline = [
            {"$match": {"status": "OK"}},
            {"$unwind": "$uses"},
            {"$match": {"uses.card.name": card_name}},
            {"$unwind": "$uses"},
            {"$match": {"uses.card.name": {"$ne": card_name}}},
            {"$group": {
                "_id": "$uses.card.name",
                "count": {"$sum": 1},
                "card_data": {"$first": "$uses.card"}
            }},
            {"$sort": {"count": -1}},
            {"$limit": limit},
            {"$lookup": {
                "from": "cards",
                "localField": "_id",
                "foreignField": "name",
                "as": "card_details"
            }},
            {"$addFields": {"card_details": {"$arrayElemAt": ["$card_details", 0]}}},
            {"$replaceRoot": {"newRoot": "$card_details"}}
        ]

        combos_coll = self._get_collection("commander_spellbook", "variants")
        if combos_coll is None:
            return []

        try:
            cursor = combos_coll.aggregate(pipeline, allowDiskUse=True)
            return [CardWithMetadata(**doc) for doc in cursor]
        except Exception as e:
            logger.error("Error in get_synergy_partners: %s", e)
            return []

    @retry_on_transient_error()
    def get_commander_staples(
        self, color_identity: list[str], min_decks: int, limit: int = 50
    ) -> list[CardWithMetadata]:
        """Get commander staples for a color identity."""
        # Get top commanders for color identity
        commanders_coll = self._get_collection("edhrec", "commanders")
        if commanders_coll is None:
            return []

        commander_uuids = [
            doc["cardUuid"] for doc in commanders_coll.find({
                "colorIdentity": {"$all": color_identity},
                "numDecks": {"$gte": min_decks}
            }, {"cardUuid": 1}).limit(20)
        ]

        if not commander_uuids:
            return []

        # Get cards commonly played with these commanders
        # This would need edhrec deck data; simplified for now
        filters = {"colorIdentity": {"$all": color_identity}, "edhrecRank": {"$ne": None}}
        return self.get_cards_enriched(filters=filters, limit=limit)

    @retry_on_transient_error()
    def get_format_legalities(self, format_name: str, limit: int = 100) -> list[CardWithMetadata]:
        """Get cards legal in a specific format."""
        filters = {f"legalities.{format_name.lower()}": "legal"}
        return self.get_cards_enriched(filters=filters, limit=limit)

    def calculate_color_identity(
        self, mana_cost: str | None, text: str | None, color_indicator: list[str] | None
    ) -> list[str]:
        """Calculate color identity from mana cost, rules text, and color indicator."""
        colors = set()

        # From color indicator
        if color_indicator:
            colors.update(color_indicator)

        # From mana cost
        if mana_cost:
            import re
            symbols = re.findall(r"\{([^}]+)\}", mana_cost)
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
            import re
            symbols = re.findall(r"\{([WUBRG])\}", text)
            colors.update(symbols)

        return sorted(colors)

    @retry_on_transient_error()
    def search_cards_text(
        self, regex: str, filters: dict | None = None, limit: int = 100
    ) -> list[CardWithMetadata]:
        """Search cards by regex on oracle text."""
        match_filter = {"oracleText": {"$regex": regex, "$options": "i"}}
        if filters:
            match_filter.update(filters)
        return self.get_cards_enriched(filters=match_filter, limit=limit)

    @retry_on_transient_error()
    def get_game_changers(self, limit: int = 100) -> list[dict]:
        coll = self._get_collection("edhrec", "game-changers")
        if coll is None:
            return []
        try:
            pipeline = [
                {"$match": {"game_changer": True, "oracle_text": {"$exists": True, "$ne": ""}}},
                {"$sample": {"size": limit}},
                {"$sort": {"num_decks": -1}},
                {"$project": {"name": 1, "oracle_text": 1, "type": 1, "mana_cost": 1, "num_decks": 1, "salt": 1, "tags": 1, "color_identity": 1}},
            ]
            return list(coll.aggregate(pipeline))
        except Exception as e:
            logger.error("Error in get_game_changers: %s", e)
            return []

    @retry_on_transient_error()  
    def get_salty_cards(self, min_salt: float = 1.2, limit: int = 100) -> list[dict]:
        coll = self._get_collection("edhrec", "game-changers")
        if coll is None:
            return []
        try:
            pipeline = [
                {"$match": {"salt": {"$gte": min_salt}, "oracle_text": {"$exists": True, "$ne": ""}}},
                {"$sample": {"size": limit}},
                {"$sort": {"salt": -1}},
                {"$project": {"name": 1, "oracle_text": 1, "type": 1, "mana_cost": 1, "num_decks": 1, "salt": 1, "tags": 1, "color_identity": 1}},
            ]
            return list(coll.aggregate(pipeline))
        except Exception as e:
            logger.error("Error in get_salty_cards: %s", e)
            return []

    @retry_on_transient_error()
    def get_top_cards_by_color(self, color: str, limit: int = 30) -> list[dict]:
        coll_name = f"top-{color}"
        coll = self._get_collection("edhrec", coll_name)
        if coll is None:
            logger.warning("Collection edhrec.%s not available", coll_name)
            return []
        try:
            pipeline = [
                {"$match": {"oracle_text": {"$exists": True}}},
                {"$sample": {"size": limit}},
                {"$sort": {"num_decks": -1}},
                {"$project": {"name": 1, "oracle_text": 1, "type": 1, "mana_cost": 1, "num_decks": 1, "tags": 1, "color_identity": 1}},
            ]
            return list(coll.aggregate(pipeline))
        except Exception as e:
            logger.error("Error in get_top_cards_by_color for %s: %s", color, e)
            return []

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _convert_doc_to_model(self, doc: dict, model_class: type[T]) -> T | None:
        """Convert MongoDB document to Pydantic model, parsing JSON string fields."""
        # Parse JSON string fields for CardWithMetadata
        if model_class.__name__ == "CardWithMetadata":
            for field in ["colors", "colorIdentity", "keywords", "subtypes", "supertypes", "frameEffects"]:
                if field in doc and isinstance(doc[field], str):
                    try:
                        import json
                        doc[field] = json.loads(doc[field])
                    except (json.JSONDecodeError, TypeError):
                        doc[field] = []
        try:
            return model_class(**doc)
        except Exception as e:
            logger.warning("Failed to convert document to %s: %s", model_class.__name__, e)
            return None


# Import Legality here to avoid circular import
from .domain_models import Legality  # noqa: E402