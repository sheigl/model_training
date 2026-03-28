"""
Python dataclasses representing the MTG archetype document schema
stored in MongoDB by scrape_mtg_fandom_archetypes.py.
"""

from dataclasses import dataclass, field
from typing import Optional
from bson import ObjectId


@dataclass
class ArchetypeSection:
    title: str
    content: list[str]
    cards: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title":   self.title,
            "content": self.content,
            "cards":   self.cards,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArchetypeSection":
        return cls(
            title   = data["title"],
            content = data.get("content", []),
            cards   = data.get("cards", []),
        )


@dataclass
class ArchetypeDocument:
    name: str
    url: str
    archetypes: list[str]
    summary: list[str]
    sections: list[ArchetypeSection]
    cards: list[str]
    categories: list[str]
    also_see: list[str]
    id: Optional[ObjectId] = field(default=None)

    def to_dict(self) -> dict:
        doc = {
            "name":       self.name,
            "url":        self.url,
            "archetypes": self.archetypes,
            "summary":    self.summary,
            "sections":   [s.to_dict() for s in self.sections],
            "cards":      self.cards,
            "categories": self.categories,
            "also_see":   self.also_see,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return doc

    @classmethod
    def from_dict(cls, data: dict) -> "ArchetypeDocument":
        return cls(
            id         = data.get("_id"),
            name       = data["name"],
            url        = data["url"],
            archetypes = data.get("archetypes", []),
            summary    = data.get("summary", []),
            sections   = [ArchetypeSection.from_dict(s) for s in data.get("sections", [])],
            cards      = data.get("cards", []),
            categories = data.get("categories", []),
            also_see   = data.get("also_see", []),
        )

    # ── Convenience accessors ─────────────────────────────────────────────────

    def get_section(self, title: str) -> Optional[ArchetypeSection]:
        """Return the first section matching the given title (case-insensitive)."""
        title_lower = title.lower()
        return next((s for s in self.sections if s.title.lower() == title_lower), None)

    def all_cards(self) -> list[str]:
        """Deduplicated list of all card names across the whole document."""
        return self.cards

    def summary_text(self) -> str:
        """Full summary as a single string."""
        return " ".join(self.summary)

    def __repr__(self) -> str:
        return (
            f"ArchetypeDocument(name={self.name!r}, "
            f"archetypes={self.archetypes}, "
            f"sections={len(self.sections)}, "
            f"cards={len(self.cards)})"
        )


# ── MongoDB helpers ───────────────────────────────────────────────────────────

def load_all(collection) -> list[ArchetypeDocument]:
    """Load every document from a pymongo collection."""
    return [ArchetypeDocument.from_dict(doc) for doc in collection.find()]


def load_by_name(collection, name: str) -> Optional[ArchetypeDocument]:
    """Load a single archetype by exact name."""
    doc = collection.find_one({"name": name})
    return ArchetypeDocument.from_dict(doc) if doc else None


def load_by_archetype(collection, archetype: str) -> list[ArchetypeDocument]:
    """Load all documents tagged with a given archetype (e.g. 'Aggro')."""
    return [
        ArchetypeDocument.from_dict(doc)
        for doc in collection.find({"archetypes": archetype})
    ]


def load_by_card(collection, card_name: str) -> list[ArchetypeDocument]:
    """Load all documents that mention a specific card."""
    return [
        ArchetypeDocument.from_dict(doc)
        for doc in collection.find({"cards": card_name})
    ]


if __name__ == "__main__":
    # Quick smoke test using the sample document from the conversation
    sample = {
        "_id": ObjectId("69c732e8e26bfc3340cc8d08"),
        "name": "Aggro deck",
        "url": "https://mtg.fandom.com/wiki/Aggro_deck",
        "archetypes": ["Aggro"],
        "summary": [
            "Aggro deck is a Magic: The Gathering term for an aggressive deck "
            "that attempts to win the game through persistent, quick damage dealing."
        ],
        "sections": [
            {
                "title": "White Weenie",
                "content": ["White Weenie is the eternal aggro deck."],
                "cards": ["White Knight", "Suntail Hawk", "Umezawa's Jitte"],
            },
            {
                "title": "Sligh",
                "content": ["Sligh was the first example of a Modern Aggro Deck."],
                "cards": ["Mogg Fanatic", "Jackal Pup", "Cursed Scroll"],
            },
        ],
        "cards": ["White Knight", "Suntail Hawk", "Umezawa's Jitte",
                  "Mogg Fanatic", "Jackal Pup", "Cursed Scroll"],
        "categories": ["Deck archetypes"],
        "also_see": [],
    }

    doc = ArchetypeDocument.from_dict(sample)
    print(doc)
    print(f"Summary: {doc.summary_text()[:80]}...")
    print(f"Cards:   {doc.all_cards()}")

    weenie = doc.get_section("White Weenie")
    print(f"Section: {weenie.title} — {weenie.cards}")

    roundtrip = ArchetypeDocument.from_dict(doc.to_dict())
    assert roundtrip.name == doc.name
    assert len(roundtrip.sections) == len(doc.sections)
    print("Roundtrip OK")