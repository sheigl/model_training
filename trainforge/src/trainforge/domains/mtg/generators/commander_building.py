"""Generate Commander-specific deckbuilding Q&A pairs.

Ports the old CLI commander building generator into the TrainForge
BaseGenerator framework.  Fetches commanders via
``get_commanders_enriched()`` and staple cards via
``get_commander_staples()`` to produce grounded deckbuilding advice.
"""

from __future__ import annotations

import logging
import random

from trainforge.domain import TemplateConfig
from trainforge.generator import BaseGenerator
from trainforge.domains.mtg.models import CardWithMetadata, CommanderWithTags

logger = logging.getLogger(__name__)


# =============================================================================
# ARCHETYPES — 12 Commander archetypes/strategies ported from old CLI
# =============================================================================

ARCHETYPES: list[tuple[str, str]] = [
    (
        "sacrifice/aristocrats",
        "Decks that sacrifice creatures for value, using Blood Artist-style effects, "
        "sac outlets, and token generators. Key challenge: balancing fodder, payoffs, "
        "and sac outlets.",
    ),
    (
        "spellslinger/magecraft",
        "Decks that cast lots of instants and sorceries, using magecraft triggers, "
        "prowess, and spell-based win conditions. Key challenge: protecting your win "
        "condition while staying low to the ground.",
    ),
    (
        "token swarm",
        "Decks that generate many creature tokens and win through wide attacks or combo. "
        "Key challenge: having enough anthems and ways to win through chump blockers.",
    ),
    (
        "reanimator",
        "Decks that put big creatures in the graveyard and reanimate them cheaply. "
        "Key challenge: filling the graveyard, protecting the reanimation target, "
        "winning with the reanimated creature.",
    ),
    (
        "combo",
        "Decks that assemble a specific combination of cards to win instantly or lock "
        "opponents out. Key challenge: finding the combo pieces, protecting the combo, "
        "having backup win conditions.",
    ),
    (
        "control",
        "Decks that answer every threat and win through superior card advantage in the "
        "late game. Key challenge: staying relevant in multiplayer, having a win condition "
        "that can close through disruption.",
    ),
    (
        "voltron",
        "Decks that buff one creature (usually the commander) with equipment and auras "
        "to win through commander damage. Key challenge: protecting your commander, "
        "rebuilding after removal, winning through 21 combat damage.",
    ),
    (
        "stax/prison",
        "Decks that use symmetrical or asymmetrical effects to slow opponents while you "
        "advance your own game plan. Key challenge: calibrating the lock pieces so you "
        "can still win, not making the game unfun.",
    ),
    (
        "landfall/lands matter",
        "Decks that trigger off lands entering the battlefield, using extra land effects "
        "and landfall payoffs. Key challenge: getting enough lands into play per turn, "
        "balancing consistency with power.",
    ),
    (
        "graveyard value",
        "Decks that use the graveyard as a resource without necessarily being reanimator "
        "— flashback, delve, threshold, cycling. Key challenge: filling the graveyard "
        "efficiently, playing around graveyard hate.",
    ),
    (
        "turbo draw/card advantage",
        "Decks built around drawing as many cards as possible to find combo pieces or "
        "assemble overwhelming card advantage. Key challenge: using the cards drawn "
        "effectively, not decking yourself.",
    ),
    (
        "midrange goodstuff",
        "Decks that play powerful cards at every part of the curve without a focused "
        "synergy strategy. Key challenge: distinguishing this from a tuned synergy deck, "
        "knowing when to choose goodstuff over theme.",
    ),
]

# Map archetype → oracle-text keyword hints
ARCHETYPE_KEYWORDS: dict[str, list[str]] = {
    "sacrifice/aristocrats": ["sacrifice", "dies", "whenever a creature dies"],
    "spellslinger/magecraft": ["instant", "sorcery", "magecraft", "prowess", "whenever you cast"],
    "token swarm": ["create", "token", "creature token"],
    "reanimator": ["graveyard", "return", "from your graveyard"],
    "combo": ["whenever", "untap", "infinite"],
    "control": ["counter", "return", "exile", "draw a card"],
    "voltron": ["equipment", "aura", "equipped", "enchant"],
    "stax/prison": ["tap", "can't", "don't", "skip"],
    "landfall/lands matter": ["land", "landfall", "whenever a land"],
    "graveyard value": ["graveyard", "flashback", "delve", "dredge", "escape"],
    "turbo draw/card advantage": ["draw a card", "draw two", "whenever you draw"],
    "midrange goodstuff": [],
}

# Fallback key cards per archetype
ARCHETYPE_KEY_CARDS: dict[str, list[str]] = {
    "sacrifice/aristocrats": [
        "Blood Artist", "Zulaport Cutthroat", "Viscera Seer", "Phyrexian Altar",
        "Ashnod's Altar", "Grave Pact", "Dictate of Erebos",
    ],
    "spellslinger/magecraft": [
        "Guttersnipe", "Archmage Emeritus", "Storm-Kiln Artist", "Ral, Storm Conduit",
        "Thousand-Year Storm", "Manamorphose",
    ],
    "token swarm": [
        "Anointed Procession", "Doubling Season", "Parallel Lives", "Beastmaster Ascension",
        "Cathars' Crusade", "Secure the Wastes",
    ],
    "reanimator": [
        "Animate Dead", "Dance of the Dead", "Necromancy", "Reanimate",
        "Entomb", "Buried Alive", "Victimize",
    ],
    "combo": [
        "Thassa's Oracle", "Demonic Consultation", "Isochron Scepter", "Dramatic Reversal",
        "Basalt Monolith", "Rings of Brighthearth",
    ],
    "control": [
        "Cyclonic Rift", "Farewell", "Toxic Deluge", "Rhystic Study",
        "Mystic Remora", "Smothering Tithe",
    ],
    "voltron": [
        "Lightning Greaves", "Swiftfoot Boots", "Sword of the Animist",
        "Stoneforge Mystic", "Open the Armory", "Sigarda's Aid",
    ],
    "stax/prison": [
        "Winter Orb", "Static Orb", "Smokestack", "Tangle Wire",
        "Drannith Magistrate", "Aven Mindcensor",
    ],
    "landfall/lands matter": [
        "Azusa, Lost but Seeking", "Courser of Kruphix", "Ramunap Excavator",
        "Splendid Reclamation", "Rampaging Baloths", "Avenger of Zendikar",
    ],
    "graveyard value": [
        "Underworld Breach", "Life from the Loam", "Snapcaster Mage",
        "Mystic Sanctuary", "Tasigur, the Golden Fang",
    ],
    "turbo draw/card advantage": [
        "Rhystic Study", "Mystic Remora", "Sylvan Library", "Necropotence",
        "Phyrexian Arena", "The One Ring",
    ],
    "midrange goodstuff": [
        "Sol Ring", "Command Tower", "Arcane Signet", "Swords to Plowshares",
        "Beast Within", "Chaos Warp",
    ],
}


# =============================================================================
# GENERATOR
# =============================================================================


class GenerateCommanderBuilding(BaseGenerator[CommanderWithTags]):
    """Generate Commander-specific deckbuilding Q&A with enriched card data.

    Each data batch is a CommanderWithTags enriched with EDHREC data.
    The prompt includes staple suggestions based on the commander's
    color identity and archetype.
    """

    def get_data_batches(self) -> list[CommanderWithTags]:
        """Fetch enriched commanders and attach archetype context.

        For each commander, we tag it with a matching archetype name
        and staple cards so that ``build_prompt()`` can produce grounded
        deckbuilding advice.

        Returns:
            List of CommanderWithTags tagged with archetype info.
        """
        ds = self.domain.get_data_source()
        commanders = ds.get_commanders_enriched(limit=100)

        # Index key cards by name for quick lookup
        all_key_card_names: set[str] = set()
        for names in ARCHETYPE_KEY_CARDS.values():
            all_key_card_names.update(names)
        all_key_cards = ds.get_cards_enriched(
            filters={"name": {"$in": list(all_key_card_names)}},
            limit=len(all_key_card_names) * 3,
            lite=True,
        )
        key_card_map: dict[str, CardWithMetadata] = {}
        for kc in all_key_cards:
            if kc.name not in key_card_map:
                key_card_map[kc.name] = kc

        results: list[CommanderWithTags] = []
        for cmd in commanders:
            archetype_name = self._match_archetype(cmd)
            archetype_desc = ""
            for name, desc in ARCHETYPES:
                if name == archetype_name:
                    archetype_desc = desc
                    break

            staple_names = ARCHETYPE_KEY_CARDS.get(archetype_name, [])
            staples = [key_card_map[n] for n in staple_names if n in key_card_map]

            _attach_archetype_info(cmd, archetype_name, archetype_desc, staples)
            results.append(cmd)

        random.shuffle(results)
        logger.info("Built %d Commander building batches", len(results))
        return results

    def get_source_category(self) -> str:
        return "commander_building"

    def build_prompt(
        self, template: TemplateConfig, data_batch: CommanderWithTags
    ) -> str:
        """Build the LLM prompt for Commander deckbuilding advice.

        Args:
            template: TemplateConfig with task_instruction.
            data_batch: A CommanderWithTags with archetype info attached.

        Returns:
            Full prompt string.
        """
        cmd = data_batch
        archetype_name = _get_archetype_name(cmd) or "General"
        archetype_desc = _get_archetype_desc(cmd) or ""
        staples = _get_staples(cmd)

        notation = self.domain.notation_legend

        # Commander detail
        cmd_type = (
            cmd.card_details.type if cmd.card_details else "Legendary Creature"
        )
        cmd_text = (
            cmd.card_details.text or cmd.card_details.oracle_text or "N/A"
            if cmd.card_details else "N/A"
        )
        cmd_colors = ", ".join(cmd.color_identity) if cmd.color_identity else "Colorless"

        # Staple card details
        staple_lines: list[str] = []
        for i, sc in enumerate(staples, 1):
            staple_lines.append(
                f"{i}. {sc.name} ({sc.type or 'N/A'}) — {sc.text or sc.oracle_text or 'N/A'}"
            )
        staples_str = "\n".join(staple_lines) if staple_lines else "See suggested cards below."

        return (
            f"{notation}\n\n"
            f"<task>\n"
            f"{template.task_instruction}\n\n"
            f"Commander: {cmd.name}\n"
            f"Type: {cmd_type}\n"
            f"Oracle Text: {cmd_text}\n"
            f"Color Identity: {cmd_colors}\n"
            f"EDHREC Decks: {cmd.num_decks:,}\n"
            f"Salt Score: {cmd.salt:.2f}\n\n"
            f"Archetype/Strategy: {archetype_name}\n"
            f"Description: {archetype_desc}\n\n"
            f"Staple cards for this archetype:\n"
            f"{staples_str}\n\n"
            f"Generate questions about:\n"
            f"- How to build a deck around {cmd.name}\n"
            f"- What card categories (ramp, removal, draw) to prioritize\n"
            f"- Key synergies and combos to include\n"
            f"- Budget alternatives for expensive staples\n"
            f"- Play pattern and win conditions\n"
            f"\n"
            f"Output JSON:\n"
            f'[\n'
            f'  {{"question": "...", "answer": "..."}},\n'
            f'  {{"question": "...", "answer": "..."}}\n'
            f"]\n"
            f"\n"
            f"Answers should be 3-6 sentences grounded in the commander's abilities and format constraints.\n"
            f"Output ONLY valid JSON.\n"
            f"</task>"
        )

    def build_context(self, data_batch: CommanderWithTags) -> str | None:
        """Build metadata context for the generated Q&A."""
        cmd = data_batch
        archetype_name = _get_archetype_name(cmd) or "General"
        return (
            f"Category: {self.get_source_category()}\n"
            f"Commander: {cmd.name}\n"
            f"Archetype: {archetype_name}\n"
            f"Color Identity: {', '.join(cmd.color_identity) if cmd.color_identity else 'Colorless'}\n"
            f"EDHREC Decks: {cmd.num_decks:,}\n"
            f"Salt: {cmd.salt:.2f}"
        )

    # ------------------------------------------------------------------
    # Archetype matching
    # ------------------------------------------------------------------

    @staticmethod
    def _match_archetype(cmd: CommanderWithTags) -> str:
        """Find the best-matching archetype for a commander based on tags and oracle text.

        Falls back to ``midrange goodstuff`` when no strong match is found.
        """
        oracle = ""
        if cmd.card_details:
            oracle = cmd.card_details.text or cmd.card_details.oracle_text or ""
        oracle_lower = oracle.lower()
        tags = [t.lower() for t in (cmd.tags or [])]

        best_score = 0
        best_archetype = "midrange goodstuff"

        for archetype_name, keywords in ARCHETYPE_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw.lower() in oracle_lower:
                    score += 1
                # Also check tags
                for tag in tags:
                    if kw.lower() in tag:
                        score += 1
            if score > best_score:
                best_score = score
                best_archetype = archetype_name

        return best_archetype


# =============================================================================
# Private helpers — attach archetype info to commander objects
# =============================================================================

_ARCHETYPE_NAME_ATTR = "_archetype_name"
_ARCHETYPE_DESC_ATTR = "_archetype_desc"
_STAPLES_ATTR = "_staples"


def _attach_archetype_info(
    cmd: CommanderWithTags,
    archetype_name: str,
    archetype_desc: str,
    staples: list[CardWithMetadata],
) -> None:
    """Store archetype metadata on the commander as private attributes."""
    object.__setattr__(cmd, _ARCHETYPE_NAME_ATTR, archetype_name)
    object.__setattr__(cmd, _ARCHETYPE_DESC_ATTR, archetype_desc)
    object.__setattr__(cmd, _STAPLES_ATTR, staples)


def _get_archetype_name(cmd: CommanderWithTags) -> str | None:
    return getattr(cmd, _ARCHETYPE_NAME_ATTR, None)


def _get_archetype_desc(cmd: CommanderWithTags) -> str | None:
    return getattr(cmd, _ARCHETYPE_DESC_ATTR, None)


def _get_staples(cmd: CommanderWithTags) -> list[CardWithMetadata]:
    return getattr(cmd, _STAPLES_ATTR, [])
