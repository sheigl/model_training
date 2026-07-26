"""MTG-specific data access layer — extends MongoDataSource with typed collection methods."""

from __future__ import annotations

import logging
from typing import Any

from trainforge.data_source import MongoDataSource

logger = logging.getLogger(__name__)


class MTGDataAccess(MongoDataSource):
    """Magic: The Gathering data access layer.

    Extends MongoDataSource with convenience methods for accessing MTG-specific
    collections (cards, articles, rules, glossary, EDHREC rankings).
    """

    def __init__(self, uri: str = "mongodb://localhost:27017", **kwargs):
        super().__init__(uri=uri, **kwargs)
        self.db_name = "synthetic_queries"

    # ------------------------------------------------------------------
    # CARD DATA
    # ------------------------------------------------------------------

    def get_cards(self, limit: int = 1000, filters: dict | None = None) -> list[dict]:
        """Fetch card records from the cards collection."""
        return self.get_records(f"{self.db_name}.mtg_cards", filters=filters, limit=limit)

    def get_card_by_name(self, name: str) -> dict | None:
        """Find a specific card by exact name match."""
        results = self.get_records(
            f"{self.db_name}.mtg_cards", filters={"name": name}, limit=1
        )
        return results[0] if results else None

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
