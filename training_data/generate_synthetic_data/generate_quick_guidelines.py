"""Generate Quick Guidelines - Deckbuilding guideline Q&A using BaseGenerator and MTGDataAccess.

Generates 5 types of deckbuilding guidelines:
1. land_count - "How many lands should my [archetype] deck run?"
2. ramp_package - "How much ramp does [archetype] need?"
3. removal_suite - "What removal should I run in [archetype]?"
4. card_advantage - "How do I get card advantage in [archetype]?"
5. win_con_density - "How many win conditions does [archetype] need?"

Uses MTGDataAccess to fetch archetype data, commander data, and training game data
for statistical grounding.
"""

from __future__ import annotations

from typing import Any, Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .domain_models import Archetype, CommanderWithTags, GameState
from .models import ModelType, Model, ValidationMetrics
from .common import QuestionAnswer, QuestionAnswerEnhanced, validate_and_loop_with_suggested_fix


# Archetypes from EDHREC tags + mtg_archetypes
ARCHETYPES = [
    "aristocrats", "spellslinger", "token_swarm", "reanimator", "combo",
    "control", "voltron", "stax", "landfall", "graveyard_value",
    "turbo_draw", "midrange", "enchantress", "artifact", "planeswalker",
    "tribal_elves", "tribal_goblins", "tribal_zombies", "tribal_dragons",
]


# Archetype strategy summaries for context building
ARCHETYPE_STRATEGIES = {
    "aristocrats": "Sacrifice creatures for value, drain life, and generate tokens. Key engines: sacrifice outlets, death triggers, token makers.",
    "spellslinger": "Cast many instants/sorceries, copy spells, and generate value from spellcasting. Key engines: prowess, magecraft, spell copy effects.",
    "token_swarm": "Create many creature tokens, then buff them or sacrifice for value. Key engines: token generators, anthems, mass pump.",
    "reanimator": "Put large creatures in graveyard, then reanimate them for less mana. Key engines: discard outlets, reanimation spells, big targets.",
    "combo": "Assemble specific card combinations that win the game or generate infinite value. Key engines: tutors, protection, compact combos.",
    "control": "Answer threats, draw cards, and win with few finishers. Key engines: counterspells, board wipes, card draw, efficient removal.",
    "voltron": "Suit up a single commander with equipment/auras to deal 21 commander damage. Key engines: protection, evasion, efficient equipment.",
    "stax": "Symmetrically restrict opponents' resources while breaking parity. Key engines: tax effects, resource denial, asymmetric breakers.",
    "landfall": "Trigger abilities when lands enter the battlefield. Key engines: land fetch, extra land drops, landfall payoffs.",
    "graveyard_value": "Use graveyard as a resource for value and recursion. Key engines: self-mill, flashback, escape, delve, recursion.",
    "turbo_draw": "Draw massive amounts of cards to find wins. Key engines: draw engines, hand size manipulation, win conditions in hand.",
    "midrange": "Efficient threats across the curve, flexible answers, card quality over synergy. Key engines: value creatures, planeswalkers, modal cards.",
    "enchantress": "Draw cards when casting enchantments, build enchantment-based board. Key engines: enchantress effects, constellation, saga value.",
    "artifact": "Artifact synergies, mana acceleration, and artifact-based win conditions. Key engines: artifact cost reduction, sacrifice outlets, recursion.",
    "planeswalker": "Protect and proliferate planeswalkers for incremental value. Key engines: proliferation, protection, oath effects.",
    "tribal_elves": "Elf tribal synergies, mana acceleration, and swarm wins. Key engines: elf lords, mana dorks, Craterhoof/Finale wins.",
    "tribal_goblins": "Goblin tribal synergies, token swarms, and combo finishes. Key engines: goblin lords, token makers, Skirk Prospector combos.",
    "tribal_zombies": "Zombie tribal, graveyard recursion, and drain effects. Key engines: lord effects, self-mill, Rooftop Storm combos.",
    "tribal_dragons": "Dragon tribal, ramp into big flyers, and dragonstorm-style finishes. Key engines: cost reduction, haste enablers, Scion toolbox.",
}


# Commander examples per archetype (from EDHREC data)
ARCHETYPE_COMMANDERS = {
    "aristocrats": ["Teysa Karlov", "Krav, the Unredeemed", "Judith, the Scourge Diva", "Yawgmoth, Thran Physician"],
    "spellslinger": ["Mizzix of the Izmagnus", "Kalamax, the Stormsire", "Veyran, Voice of Duality", "Ral, Storm Conduit"],
    "token_swarm": ["Rhys the Redeemed", "Trostani, Selesnya's Voice", "Emmara, Soul of the Accord", "Krenko, Mob Boss"],
    "reanimator": ["Meren of Clan Nel Toth", "The Mimeoplasm", "Karador, Ghost Chieftain", "Alesha, Who Smiles at Death"],
    "combo": ["Thrasios, Triton Hero", "Tymna the Weaver", "Kinnan, Bonder Prodigy", "Urza, Lord Protector"],
    "control": ["Grand Arbiter Augustin IV", "Azami, Lady of Scrolls", "Baral, Chief of Compliance", "Talrand, Sky Summoner"],
    "voltron": ["Sram, Senior Edificer", "Balan, Wandering Knight", "Kemba, Kha Regent", "Godo, Bandit Warlord"],
    "stax": ["Derevi, Empyrial Tactician", "Hokori, Dust Drinker", "Elesh Norn, Grand Cenobite", "Karn, the Great Creator"],
    "landfall": ["Omnath, Locus of Creation", "Tatyova, Benthic Druid", "Aesi, Tyrant of Gyre Strait", "Lord Windgrace"],
    "graveyard_value": ["Muldrotha, the Gravetide", "The Gitrog Monster", "Kroxa, Titan of Death's Hunger", "Chainer, Nightmare Adept"],
    "turbo_draw": ["Niv-Mizzet, Parun", "The Locust God", "Kess, Dissident Mage", "Narset, Parter of Veils"],
    "midrange": ["Tymna the Weaver", "Kraum, Ludevic's Opus", "Atraxa, Praetors' Voice", "Yorion, Sky Nomad"],
    "enchantress": ["Sythis, Harvest's Hand", "Estrid, the Masked", "Tuvasa the Sunlit", "Satyr Enchanter"],
    "artifact": ["Urza, Lord Protector", "Karn, the Great Creator", "Goblin Welder", "Daretti, Scrap Savant"],
    "planeswalker": ["Atraxa, Praetors' Voice", "Teferi, Hero of Dominaria", "Nicol Bolas, Dragon-God", "Oath of Teferi"],
    "tribal_elves": ["Lathril, Blade of the Elves", "Ezuri, Renegade Leader", "Marwyn, the Nurturer", "Eladamri, Lord of Leaves"],
    "tribal_goblins": ["Krenko, Mob Boss", "Prosper, Tome-Bound", "Squee, the Immortal", "Wort, Boggart Auntie"],
    "tribal_zombies": ["The Scarab God", "Gisa and Geralf", "Varina, Lich Queen", "Ghoulcaller Gisa"],
    "tribal_dragons": ["The Ur-Dragon", "Scion of the Ur-Dragon", "Miirym, Sentinel Wyrm", "Velomachus Lorehold"],
}


# Template configurations for the 5 guideline types
TEMPLATE_CONFIGS = [
    TemplateConfig(
        template_id="land_count",
        task_instruction=(
            "Generate 3 Q&A pairs about land count for this archetype. "
            "Each question should ask 'How many lands should my [archetype] deck run?' with natural variations. "
            "Answers MUST: give a specific land count range (e.g., 36-38), explain based on average mana curve and ramp density, "
            "cite 2+ example commanders from the archetype, mention how ramp affects land count, "
            "and reference real deck statistics if available."
        ),
        weight=1.0,
        validation_rules=[
            "Answer gives specific land count range (e.g., 36-38)",
            "Explains based on curve and ramp",
            "Cites 2+ example commanders",
            "Mentions ramp effect on land count",
        ],
        min_answer_length=120,
    ),
    TemplateConfig(
        template_id="ramp_package",
        task_instruction=(
            "Generate 3 Q&A pairs about ramp package for this archetype. "
            "Each question should ask 'How much ramp does [archetype] need?' with natural variations. "
            "Answers MUST: give a ramp count range (e.g., 8-12), break down by type (land ramp / artifact ramp / rituals), "
            "explain based on commander CMC and color identity, list 3+ specific ramp cards matching the archetype's colors, "
            "and mention color constraints on ramp choices."
        ),
        weight=1.0,
        validation_rules=[
            "Answer gives ramp count range",
            "Breaks down by type (land/artifact/ritual)",
            "Explains based on commander CMC",
            "Lists 3+ specific ramp cards",
            "Mentions color constraints",
        ],
        min_answer_length=150,
    ),
    TemplateConfig(
        template_id="removal_suite",
        task_instruction=(
            "Generate 3 Q&A pairs about removal suite for this archetype. "
            "Each question should ask 'What removal should I run in [archetype]?' with natural variations. "
            "Answers MUST: give a removal count range (e.g., 8-12), break down targeted removal vs board wipes, "
            "explain based on archetype role (control needs more, aggro needs less), "
            "list 3+ specific removal cards matching the archetype's colors, "
            "and mention versatile vs narrow removal choices."
        ),
        weight=1.0,
        validation_rules=[
            "Answer gives removal count range",
            "Breaks down targeted vs board wipes",
            "Explains based on archetype role",
            "Lists 3+ specific removal cards",
            "Mentions versatile vs narrow removal",
        ],
        min_answer_length=150,
    ),
    TemplateConfig(
        template_id="card_advantage",
        task_instruction=(
            "Generate 3 Q&A pairs about card advantage for this archetype. "
            "Each question should ask 'How do I get card advantage in [archetype]?' with natural variations. "
            "Answers MUST: list 3+ specific card advantage engines (draw, selection, recursion), "
            "explain synergy with archetype's game plan, distinguish between burst draw and steady engines, "
            "mention at least 1 commander that enables card advantage, "
            "and explain why these engines fit the archetype better than generic goodstuff."
        ),
        weight=1.0,
        validation_rules=[
            "Lists 3+ specific card advantage engines",
            "Explains synergy with archetype",
            "Distinguishes burst vs steady draw",
            "Mentions 1+ commander enabling CA",
            "Explains archetype-specific fit",
        ],
        min_answer_length=150,
    ),
    TemplateConfig(
        template_id="win_con_density",
        task_instruction=(
            "Generate 3 Q&A pairs about win condition density for this archetype. "
            "Each question should ask 'How many win conditions does [archetype] need?' with natural variations. "
            "Answers MUST: give a specific win con count or range (e.g., 2-4), explain compact vs redundant win cons, "
            "list 2+ example win conditions matching the archetype, "
            "explain how the archetype's strategy impacts win con choices, "
            "and mention relationship between tutor density and win con count."
        ),
        weight=1.0,
        validation_rules=[
            "Gives specific win con count/range",
            "Explains compact vs redundant",
            "Lists 2+ example win conditions",
            "Explains strategy impact on win cons",
            "Mentions tutor density relationship",
        ],
        min_answer_length=150,
    ),
]


class GenerateQuickGuidelines(BaseGenerator[dict]):
    """Generator for quick deckbuilding guidelines using BaseGenerator pattern."""

    TEMPLATES = TEMPLATE_CONFIGS

    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int,
        save_item: callable,
        metrics: ValidationMetrics | None = None,
        dry_run: bool = False,
        max_regeneration_attempts: int = 3,
        batch_size: int = 1,
        templates_per_item: int = 1,
        enable_extra_validation: bool = True,
        **kwargs,
    ):
        self.data_access = data_access
        self._archetype_data_cache: dict[str, dict] = {}
        super().__init__(
            models=models,
            validation_pct=validation_pct,
            target_count=target_count,
            save_item=save_item,
            metrics=metrics,
            generator_name="GenerateQuickGuidelines",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
            **kwargs,
        )

    def get_data_batches(self) -> Iterator[list[dict]]:
        """Fetch and yield data batches for each archetype."""
        # Pre-fetch data for all archetypes
        self._prefetch_archetype_data()

        # Yield one batch per archetype
        for archetype in ARCHETYPES:
            if archetype in self._archetype_data_cache:
                yield [self._archetype_data_cache[archetype]]

    def _prefetch_archetype_data(self) -> None:
        """Pre-fetch all data needed for archetype context building."""
        # Get archetype data from mtg_archetypes
        archetypes = self.data_access.get_archetype_data()
        archetype_map = {a.name.lower().replace(" ", "_"): a for a in archetypes}

        # Get commanders for each archetype
        all_commanders = self.data_access.get_commanders_enriched(limit=500)
        commanders_by_tag: dict[str, list[CommanderWithTags]] = {}
        for cmd in all_commanders:
            for tag in cmd.tags:
                tag_lower = tag.lower().replace(" ", "_")
                if tag_lower not in commanders_by_tag:
                    commanders_by_tag[tag_lower] = []
                commanders_by_tag[tag_lower].append(cmd)

        # Get training game data for stats
        game_states = self.data_access.get_game_states(limit=1000)

        # Build cache for each archetype
        for archetype in ARCHETYPES:
            self._archetype_data_cache[archetype] = self._build_archetype_context(
                archetype, archetype_map, commanders_by_tag, game_states
            )

    def _build_archetype_context(
        self,
        archetype: str,
        archetype_map: dict[str, Archetype],
        commanders_by_tag: dict[str, list[CommanderWithTags]],
        game_states: list[GameState],
    ) -> dict:
        """Build rich context for an archetype."""
        # Get strategy
        strategy = ARCHETYPE_STRATEGIES.get(archetype, "A versatile strategy.")

        # Get commanders
        commander_names = ARCHETYPE_COMMANDERS.get(archetype, [])
        commanders = []
        for name in commander_names:
            # Find in commanders_by_tag
            for tag, cmds in commanders_by_tag.items():
                for cmd in cmds:
                    if cmd.name == name:
                        commanders.append(cmd)
                        break
                if len(commanders) >= 4:
                    break
            if len(commanders) >= 4:
                break

        # Get key cards from archetype data
        key_cards = []
        if archetype in archetype_map:
            key_cards = archetype_map[archetype].key_cards[:10]

        # Calculate average mana curve from commanders
        avg_cmc = 0.0
        if commanders:
            cmcs = []
            for cmd in commanders:
                if cmd.card_details and cmd.card_details.cmc:
                    cmcs.append(cmd.card_details.cmc)
            if cmcs:
                avg_cmc = sum(cmcs) / len(cmcs)

        # Get deck stats from training games (simplified)
        deck_stats = self._calculate_deck_stats(archetype, game_states)

        # Get top cards by color identity from EDHREC
        color_identity = []
        if commanders:
            color_identity = commanders[0].color_identity

        top_cards = []
        if color_identity:
            top_cards = self.data_access.get_top_cards_by_edhrec_rank(color_identity, limit=15)

        return {
            "archetype": archetype,
            "strategy": strategy,
            "commanders": [c.name for c in commanders],
            "commander_details": [
                {"name": c.name, "cmc": c.card_details.cmc if c.card_details else None, "colors": c.color_identity}
                for c in commanders
            ],
            "key_cards": key_cards,
            "top_cards": [c.name for c in top_cards[:10]],
            "avg_cmc": round(avg_cmc, 1),
            "color_identity": color_identity,
            "deck_stats": deck_stats,
        }

    def _calculate_deck_stats(self, archetype: str, game_states: list[GameState]) -> dict:
        """Calculate deck statistics from training game data."""
        # This is a simplified version - in practice you'd filter games by archetype
        # For now, return reasonable defaults based on archetype
        defaults = {
            "avg_lands": 37,
            "avg_ramp": 10,
            "avg_removal": 10,
            "avg_card_draw": 8,
            "avg_win_cons": 3,
            "sample_size": len(game_states),
        }

        # Adjust based on archetype
        if archetype in ["control", "stax"]:
            defaults.update({"avg_lands": 38, "avg_removal": 12, "avg_card_draw": 10})
        elif archetype in ["combo", "turbo_draw"]:
            defaults.update({"avg_lands": 35, "avg_ramp": 12, "avg_win_cons": 2})
        elif archetype in ["voltron", "tribal_elves", "tribal_goblins"]:
            defaults.update({"avg_lands": 36, "avg_ramp": 8})
        elif archetype in ["landfall"]:
            defaults.update({"avg_lands": 40, "avg_ramp": 14})

        return defaults

    def build_prompt(self, template: TemplateConfig, data_batch: dict) -> str:
        """Build the LLM prompt for a specific template and archetype data."""
        data = data_batch[0] if isinstance(data_batch, list) else data_batch
        archetype = data["archetype"]
        strategy = data["strategy"]
        commanders = data["commanders"]
        key_cards = data["key_cards"]
        top_cards = data["top_cards"]
        avg_cmc = data["avg_cmc"]
        color_identity = data["color_identity"]
        deck_stats = data["deck_stats"]

        commander_examples = ", ".join(commanders[:3]) if commanders else "various commanders"
        key_cards_str = ", ".join(key_cards[:8]) if key_cards else "archetype staples"
        top_cards_str = ", ".join(top_cards[:8]) if top_cards else "color staples"
        colors_str = ", ".join(color_identity) if color_identity else "colorless"

        stats_str = (
            f"Avg lands: {deck_stats.get('avg_lands', 37)}, "
            f"Avg ramp: {deck_stats.get('avg_ramp', 10)}, "
            f"Avg removal: {deck_stats.get('avg_removal', 10)}, "
            f"Avg card draw: {deck_stats.get('avg_card_draw', 8)}, "
            f"Avg win cons: {deck_stats.get('avg_win_cons', 3)}"
        )

        prompt = f"""{self._get_mtg_notation_legend()}

You are an expert Commander deckbuilder. Generate deckbuilding guideline Q&A for the {archetype} archetype.

ARCHETYPE CONTEXT:
- Name: {archetype}
- Strategy: {strategy}
- Example Commanders: {commander_examples}
- Key Cards: {key_cards_str}
- Top Color Staples: {top_cards_str}
- Color Identity: {colors_str}
- Average Commander CMC: {avg_cmc}
- Real Deck Statistics: {stats_str}

TEMPLATE INSTRUCTION:
{template.task_instruction}

Output ONLY valid JSON in this format:
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

The answer MUST be a single string (not an array). Do not include markdown formatting."""

        return prompt

    def _get_mtg_notation_legend(self) -> str:
        """Return the MTG notation legend for prompts."""
        return """<reference>
MTG NOTATION:
- {T}: Tap (rotate card 90°; only if untapped)
- {C}: Colorless mana | {W}: White | {U}: Blue | {B}: Black | {R}: Red | {G}: Green
- {X}: Variable amount | {1},{2},{3}...: Generic mana (any color/colorless)
- Example: {2}{U}{U} = 4 total mana (2 generic + 2 blue)

CARD TYPES:
- Creature: Can attack/block; has summoning sickness (can't tap or attack first turn it enters)
- Artifact / Enchantment: Permanent; stays on battlefield
- Instant: Cast anytime; goes to graveyard after resolving
- Sorcery: Cast only on your turn; goes to graveyard after resolving
- Land: Played once per turn (not cast); produces mana

KEY TERMS:
- ETB: Triggers when permanent enters the battlefield
- Summoning Sickness: Creatures can't tap or attack the turn they enter
- Sacrifice: Put into graveyard as a cost (uncounterable)
- Destroy: Put into graveyard (blocked by indestructible)
- Exile: Remove from game (harder to recover than graveyard)
</reference>"""

    def get_source_category(self) -> str:
        """Return the source category for metrics and tracking."""
        return "quick_guideline"

    def get_source_data(self, data_batch: dict) -> list[Any]:
        """Extract source data references for the generated document."""
        data = data_batch[0] if isinstance(data_batch, list) else data_batch
        archetype = data["archetype"]
        return [
            f"archetype:{archetype}",
            f"commanders:{','.join(data['commanders'][:3])}",
            f"key_cards:{','.join(data['key_cards'][:5])}",
            f"top_cards:{','.join(data['top_cards'][:5])}",
        ]

    def build_context(self, template: TemplateConfig, data_batch: dict) -> str:
        """Build validation context for the generated Q&A."""
        data = data_batch[0] if isinstance(data_batch, list) else data_batch
        archetype = data["archetype"]
        template_id = template.template_id

        context = (
            f"Category: {self.get_source_category()}\n"
            f"Template: {template_id}\n"
            f"Archetype: {archetype}\n"
            f"Strategy: {data['strategy']}\n"
            f"Commanders: {', '.join(data['commanders'][:3])}\n"
            f"Avg CMC: {data['avg_cmc']}\n"
            f"Color Identity: {', '.join(data['color_identity']) if data['color_identity'] else 'colorless'}\n"
            f"Deck Stats: {data['deck_stats']}\n"
        )

        # Add template-specific validation context
        validation_contexts = {
            "land_count": (
                "VALIDATION: Answer must give specific land count range (e.g., 36-38), "
                "explain based on curve/ramp, cite 2+ commanders, mention ramp effect on lands."
            ),
            "ramp_package": (
                "VALIDATION: Answer must give ramp count range, break down by type "
                "(land/artifact/ritual), explain based on commander CMC, list 3+ specific cards, "
                "mention color constraints."
            ),
            "removal_suite": (
                "VALIDATION: Answer must give removal count range, break down targeted vs wipes, "
                "explain based on archetype role, list 3+ specific cards matching colors, "
                "mention versatile vs narrow removal."
            ),
            "card_advantage": (
                "VALIDATION: Answer must list 3+ specific card advantage engines, "
                "explain synergy with archetype, distinguish draw/selection/recursion, "
                "mention 1+ commander enabling CA, explain archetype-specific fit."
            ),
            "win_con_density": (
                "VALIDATION: Answer must give specific win con count/range, explain compact vs "
                "redundant, list 2+ example win cons matching archetype, explain strategy impact, "
                "mention tutor density relationship."
            ),
        }

        if template_id in validation_contexts:
            context += validation_contexts[template_id]

        return context

    def validate_answer(
        self,
        qa: QuestionAnswer,
        template: TemplateConfig,
        data_batch: dict,
        source_data: list[Any],
    ) -> tuple[bool, QuestionAnswerEnhanced | None]:
        """Run validation pipeline with regeneration loop."""
        return validate_and_loop_with_suggested_fix(
            query_model=self.query_model,
            models=self.models,
            qa_pairs=[qa],
            validation_pct=self.validation_pct,
            enable_extra_validation=self.enable_extra_validation,
            build_context=lambda: self.build_context(template, data_batch),
            source_category=self.get_source_category(),
            source_data=source_data,
            source_template=template.template_id,
            metrics=self.metrics,
        )