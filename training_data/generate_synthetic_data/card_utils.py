"""Pure-card mapping helpers — no heavy LLM/external-service deps.

These functions convert raw MongoDB dicts into Pydantic ``Card`` models.
They live in their own module so they can be unit-tested without pulling
in the full dependency chain (ollama, anthropic, etc.) that ``common.py``
requires at import time.
"""

from __future__ import annotations

import json
from typing import Any

from .domain_models import Card as PydanticCard


def map_card(card: dict[str, Any]) -> PydanticCard | None:
    """Map a MongoDB document to a Pydantic Card model.

    Handles both camelCase (MongoDB) and snake_case keys.
    Returns ``None`` when required fields are missing.
    """
    return PydanticCard.from_dict(card)


def map_card_with_zones(
    card: dict[str, Any], zone_locations: list[str] | None = None
) -> PydanticCard | None:
    """Map a MongoDB document to a Pydantic Card with optional zone info.

    Used by combo generators that track which zone each card starts in.
    The ``zone_locations`` field is stored as a dynamic attribute for
    backward compatibility with legacy code that reads ``card.zone_locations``.
    """
    result = PydanticCard.from_dict(card)
    if result is None:
        return None
    # Attach zone_locations as a dynamic attribute for backward compat
    object.__setattr__(result, "zone_locations", zone_locations or [])
    return result
