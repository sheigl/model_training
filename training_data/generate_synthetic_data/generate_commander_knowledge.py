"""Generate Commander knowledge Q&A pairs using BaseGenerator.

Grounds generation in authoritative rule text (mtg_rules.rules section 903/800)
and real card data (mtg_json.cards enriched with EDHREC metadata) pulled from
MongoDB. Providing the LLM with real rule text and real cards prevents
hallucinating invented rules, card names, and card abilities.
"""

from dataclasses import dataclass, field
from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    SYSTEM_MESSAGE,
    NEW_LINE,
    build_card_detail,
)
from .data_access import MTGDataAccess
from .domain_models import CardWithMetadata, Rule
from .logger import print


# Validation criteria for commander knowledge templates
COMMANDER_KNOWLEDGE_GENERAL_VALIDATION = """
HARD REJECT RULES:
1. Answer does not provide accurate Commander rules information — incorrect rules are validation failures.
2. Answer contains markdown formatting (bold, italics, bullet points).
3. Answer references rule numbers directly — rules must be explained conversationally.
4. Answer is less than 80 characters.
5. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer accurately explains the Commander rules topic.
2. The answer uses a conversational tone without citing rule numbers.
3. At least one question comes from a practical perspective (e.g., "How does...?" or "What happens when...?").
"""

COMMANDER_KNOWLEDGE_EXAMPLE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not include at least one concrete scenario or card interaction example.
2. Answer references a card that is not listed in the provided context, or describes a listed card's abilities incorrectly.
3. Answer contains markdown formatting (bold, italics, bullet points).
4. Answer references rule numbers directly — rules must be explained conversationally.
5. Answer is less than 80 characters.
6. JSON parsing fails.

VALIDATION CHECKLIST:
1. The answer includes at least one concrete scenario that illustrates the rules interaction.
2. The answer references specific card names or game situations from the provided context.
3. The answer explains the rules interaction step by step.
"""


@dataclass
class CommanderKnowledgeBatch:
    """Grounded data batch for a Commander knowledge sub-topic.

    Provides authoritative rule text and real cards so the LLM never has to
    invent rules or card names/abilities.
    """

    topic: str
    topic_context: str
    relevant_rules: list[Rule] = field(default_factory=list)
    example_commanders: list[CardWithMetadata] = field(default_factory=list)
    key_cards: list[CardWithMetadata] = field(default_factory=list)


# Per-sub-topic grounding spec:
#   rule_numbers      → authoritative mtg_rules.rules to include (section 903/800)
#   commander_names   → real EDHREC commanders illustrating the topic
#   key_card_names    → real cards illustrating the rule
# All names must resolve in mtg_json.cards (verified against the live DB).
TOPIC_DATA_SPEC: dict[str, dict] = {
    "deck construction rules": {
        "rule_numbers": ["903.1", "903.3", "903.4", "903.5"],
        "commander_names": [
            "The Ur-Dragon",
            "Kenrith, the Returned King",
            "Sisay, Weatherlight Captain",
            "Ramos, Dragon Engine",
        ],
        "key_card_names": [
            "Sol Ring",
            "Command Tower",
            "Arcane Signet",
            "Transguild Courier",
            "Boros Reckoner",
        ],
    },
    "commander tax": {
        "rule_numbers": ["903.8"],
        "commander_names": [
            "Niv-Mizzet, Parun",
            "The Ur-Dragon",
            "Kess, Dissident Mage",
            "Edgar Markov",
        ],
        "key_card_names": [
            "Trinisphere",
            "Sphere of Resistance",
            "Thalia, Guardian of Thraben",
            "Grand Arbiter Augustin IV",
            "Command Beacon",
        ],
    },
    "commander damage": {
        "rule_numbers": ["903.10"],
        "commander_names": [
            "Skullbriar, the Walking Grave",
            "Xenagos, God of Revels",
            "Rafiq of the Many",
            "Sigarda, Host of Herons",
        ],
        "key_card_names": [
            "Colossus Hammer",
            "Fireshrieker",
            "Blackblade Reforged",
        ],
    },
    "command zone": {
        "rule_numbers": ["903.6", "903.9"],
        "commander_names": [
            "The Ur-Dragon",
            "Inalla, Archmage Ritualist",
            "Oloro, Ageless Ascetic",
            "Sen Triplets",
        ],
        "key_card_names": [
            "Command Beacon",
            "Drannith Magistrate",
        ],
    },
    "color identity restrictions": {
        "rule_numbers": ["903.4"],
        "commander_names": [
            "Feather, the Redeemed",
            "Alesha, Who Smiles at Death",
            "Jodah, Archmage Eternal",
            "Morophon, the Boundless",
        ],
        "key_card_names": [
            "Boros Reckoner",
            "Transguild Courier",
            "Gitaxian Probe",
            "Dismember",
        ],
    },
    "multiplayer rules": {
        "rule_numbers": ["903.2", "903.7"],
        "commander_names": [
            "Kynaios and Tiro of Meletis",
            "Queen Marchesa",
            "Phelddagrif",
            "Kenrith, the Returned King",
        ],
        "key_card_names": [
            "Howling Mine",
            "Rhystic Study",
            "Arcane Signet",
        ],
    },
    "partner and background commanders": {
        "rule_numbers": ["903.3"],
        "commander_names": [
            "Rograkh, Son of Rohgahh",
            "Kediss, Emberclaw Familiar",
            "Ishai, Ojutai Dragonspeaker",
            "Thrasios, Triton Hero",
            "Wilson, Refined Grizzly",
        ],
        "key_card_names": [
            "Agent of the Iron Throne",
            "Guild Artisan",
            "Noble Heritage",
            "Raised by Giants",
        ],
    },
    "companion and wish effects": {
        "rule_numbers": ["903.11"],
        "commander_names": [
            "Keruga, the Macrosage",
            "Lurrus of the Dream-Den",
            "Yorion, Sky Nomad",
            "Zirda, the Dawnwaker",
        ],
        "key_card_names": [
            "Fae of Wishes // Granted",
            "Burning Wish",
            "Cunning Wish",
        ],
    },
}


class GenerateCommanderKnowledge(BaseGenerator[CommanderKnowledgeBatch]):
    """Generate Commander rules Q&A covering deck construction, tax, damage, and format rules."""

    # Commander sub-topics broken from the original monolithic topic
    # Covers all concepts from the original: singleton, command zone, tax, damage, color identity, multiplayer, partner, companion
    COMMANDER_SUBTOPICS = [
        (
            "deck construction rules",
            "100-card singleton, exactly 100 cards including commander, no sideboard, commander determines color identity, basics only from outside game.",
        ),
        (
            "commander tax",
            "Each time commander is cast from command zone, costs {2} more. Tax is cumulative. Applies to all spell-based commanders.",
        ),
        (
            "commander damage",
            "21 combat damage from a single commander to a player loses that game. Commander must be commanded by the player who dealt it. Resets if commander changes zones.",
        ),
        (
            "command zone",
            "Commander starts in command zone. Goes to command zone from any zone (owner's choice for graveyard/exile). Not cast from library, hand, or battlefield.",
        ),
        (
            "color identity restrictions",
            "Cards in deck must only use mana symbols in commander's color identity. Hybrid, Phyrexian, color indicators all count. Basic lands only from outside.",
        ),
        (
            "multiplayer rules",
            "Typically 4 players. Last player standing wins. Political deals, archenemy dynamics, kingmaking considerations. Turn order matters for threat assessment.",
        ),
        (
            "partner and background commanders",
            "Partner allows 2 commanders if both have 'Partner'. Background enchantment commanders pair with a creature that has 'Choose a Background'. Both count for color identity.",
        ),
        (
            "companion and wish effects",
            "Companion restrictions apply from outside the game. Wish effects can only get cards from outside in casual. Commander's Handbook / Rule 903.9 governs this.",
        ),
    ]

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict,
        validation_pct: float,
        target_count: int = 3000,
        save_item: callable = None,
        metrics=None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
        **kwargs,
    ):
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateCommanderKnowledge",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
            **kwargs,
        )
        self.data_access = data_access
        self._rules: dict[str, Rule] = {}
        self._cards: dict[str, CardWithMetadata] = {}
        self._loaded = False

    def _ensure_data_loaded(self) -> None:
        """Lazily load all grounding data (rules + cards) on first call."""
        if self._loaded:
            return
        self._loaded = True

        all_rule_numbers = sorted(
            {num for spec in TOPIC_DATA_SPEC.values() for num in spec["rule_numbers"]}
        )
        rules = self.data_access.get_rules(
            {"rule_number": {"$in": all_rule_numbers}},
            limit=len(all_rule_numbers),
        )
        self._rules = {r.rule_number: r for r in rules}

        all_names = sorted(
            {
                name
                for spec in TOPIC_DATA_SPEC.values()
                for name in spec["commander_names"] + spec["key_card_names"]
            }
        )
        # Fetch per name (limit=1) because get_cards_enriched applies $sample —
        # a bulk $in query would randomly drop names.
        for name in all_names:
            cards = self.data_access.get_cards_enriched(
                filters={"name": name}, limit=1, lite=True
            )
            if cards:
                self._cards[name] = cards[0]

        print(
            f"  → Commander knowledge grounded in {len(self._rules)} rules "
            f"and {len(self._cards)} cards from MongoDB"
        )

    def get_data_batches(self) -> Iterator[CommanderKnowledgeBatch]:
        """Yield one grounded batch per sub-topic."""
        self._ensure_data_loaded()

        while True:
            for topic_name, topic_context in self.COMMANDER_SUBTOPICS:
                spec = TOPIC_DATA_SPEC.get(topic_name, {})
                rules = sorted(
                    (self._rules[n] for n in spec.get("rule_numbers", []) if n in self._rules),
                    key=lambda r: r.rule_number,
                )
                commanders = [
                    self._cards[n]
                    for n in spec.get("commander_names", [])
                    if n in self._cards
                ]
                key_cards = [
                    self._cards[n]
                    for n in spec.get("key_card_names", [])
                    if n in self._cards
                ]

                yield CommanderKnowledgeBatch(
                    topic=topic_name,
                    topic_context=topic_context,
                    relevant_rules=rules,
                    example_commanders=commanders,
                    key_cards=key_cards,
                )

    def build_prompt(self, template: TemplateConfig, data_batch: CommanderKnowledgeBatch) -> str:
        """Build a grounded LLM prompt with authoritative rules and real cards."""
        batch = data_batch

        rules_xml = NEW_LINE.join(
            f"Rule {r.rule_number}: {r.text}" for r in batch.relevant_rules
        ) or "No authoritative rule text available."

        commander_blocks = [
            build_card_detail(i + 1, cmd)
            for i, cmd in enumerate(batch.example_commanders)
        ]
        commanders_xml = (
            NEW_LINE.join(commander_blocks) if commander_blocks else "No commander examples available."
        )

        card_blocks = [
            build_card_detail(i + 1, card)
            for i, card in enumerate(batch.key_cards)
        ]
        key_cards_xml = (
            NEW_LINE.join(card_blocks) if card_blocks else "No key card examples available."
        )

        task_instruction = template.task_instruction.format(
            topic=batch.topic,
            context=batch.topic_context,
            output_format=OUTPUT_FORMAT.strip(),
        )

        prompt = f"""{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<rules>
AUTHORITATIVE RULES — treat these as ground truth. Base every rules statement on this text.
{rules_xml}
</rules>

<commanders>
Real commanders relevant to this topic. Reference ONLY these cards by name.
{commanders_xml}
</commanders>

<key_cards>
Real cards relevant to this topic. Reference ONLY these cards by name.
{key_cards_xml}
</key_cards>

<task>
{task_instruction}
</task>"""

        return prompt

    def get_source_category(self) -> str:
        return "commander_rules"

    def get_source_data(self, data_batch: CommanderKnowledgeBatch) -> list:
        """Extract source data references for the generated Q&A."""
        sources = []
        for rule in data_batch.relevant_rules:
            sources.append({"rule_number": rule.rule_number, "section": rule.section})
        for cmd in data_batch.example_commanders:
            sources.append({"name": cmd.name, "role": "commander", "edhrec_rank": cmd.edhrec_rank})
        for card in data_batch.key_cards:
            sources.append({"name": card.name, "role": "key_card", "edhrec_rank": card.edhrec_rank})
        return sources

    def build_context(self, template: TemplateConfig, data_batch: CommanderKnowledgeBatch) -> str:
        """Build validation context with the same grounding data the LLM saw."""
        batch = data_batch

        rules_text = NEW_LINE.join(
            f"  Rule {r.rule_number}: {r.text}" for r in batch.relevant_rules
        ) or "  None"

        commander_context = NEW_LINE.join(
            f"  {c.name}: {c.primary_face.oracle_text[:200] if c.primary_face else 'N/A'}"
            for c in batch.example_commanders
        ) or "  None"

        card_context = NEW_LINE.join(
            f"  {c.name}: {c.primary_face.oracle_text[:200] if c.primary_face else 'N/A'}"
            for c in batch.key_cards
            if c.primary_face and c.primary_face.oracle_text
        ) or "  None"

        return f"""Category: {self.get_source_category()}
Template: {template.template_id}
Topic: {batch.topic}
Context: {batch.topic_context}

Authoritative Rules (ground truth for answers):
{rules_text}

Example Commanders (reference only these for accuracy):
{commander_context}

Key Cards (reference only these for accuracy):
{card_context}"""
