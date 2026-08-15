"""Generate synergy discovery Q&A pairs using BaseGenerator and MTGDataAccess.

Implements 4 synergy templates:
1. combo_piece - "What cards combo with [card] for infinite [result]?"
2. value_engine - "What cards generate value with [card] over multiple turns?"
3. tribal_synergy - "What [creature type] cards synergize with [card]?"
4. mechanic_synergy - "What cards work well with [card]'s [mechanic] ability?"

Data sources:
- Commander Spellbook combos (direct combo partners)
- EDHREC tags from commanders/game-changers (thematic partners)
- Card keywords (mechanic-based partners)
- Commander tags (commander-specific synergy)
"""

import random
from collections import defaultdict
from typing import Iterator

from .base_generator import BaseGenerator, TemplateConfig
from .data_access import MTGDataAccess
from .domain_models import CardWithMetadata, ComboWithCards, CommanderWithTags
from .models import Model, ModelType, ValidationMetrics
from .common import (
    MTG_NOTATION_LEGEND,
    OUTPUT_FORMAT,
    SYSTEM_MESSAGE,
    NEW_LINE,
    build_card_detail,
)
from .logger import print


# =============================================================================
# VALIDATION RULES PER TEMPLATE
# =============================================================================

COMBO_PIECE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not explain the infinite loop mechanism step by step.
2. Answer does not cite oracle text for EACH combo piece explaining its role.
3. Answer does not mention required zones (battlefield, hand, command zone, graveyard) for each piece.
4. Answer does not state the mana or other resource requirements to initiate the combo.
5. Answer does not state the concrete infinite outcome (e.g., "infinite damage", "infinite mana of any color", "infinite creature tokens").
6. Answer uses vague phrases like "very powerful" or "wins the game" instead of specific outcomes.
7. Answer contains markdown formatting (bold, italics, bullet points).
8. Answer references rule numbers directly — mechanics must be explained conversationally.
9. Answer is less than 80 characters.
10. JSON parsing fails.

VALIDATION CHECKLIST:
1. The infinite loop mechanism is explained step by step in correct order.
2. Oracle text is cited or closely paraphrased for each combo piece.
3. Zone requirements for each piece are explicitly stated.
4. Mana/resource requirements are stated.
5. Concrete infinite outcome is stated explicitly.
6. At least one question comes from a player asking "What combos with X for infinite Y?"
"""

VALUE_ENGINE_VALIDATION = """
HARD REJECT RULES:
1. Answer does not explain how value is generated over multiple turns (not a one-time effect).
2. Answer does not cite the specific triggers or abilities that generate recurring value.
2. Answer does not mention the mana investment required to set up and maintain the engine.
3. Answer does not explain what happens each turn/activation cycle.
4. Answer lists cards without explaining the synergistic interaction.
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. Value generation over time is clearly explained (e.g., "each turn you draw a card", "each activation creates a token").
2. Specific triggers/abilities are cited from oracle text.
3. Mana investment (setup cost + ongoing cost) is stated.
4. The engine's sustainability is addressed (does it run out of resources?).
5. At least one question asks about long-term value generation.
"""

TRIBAL_SYNERGY_VALIDATION = """
HARD REJECT RULES:
1. Answer does not identify the shared creature type that enables the synergy.
2. Answer does not mention at least one tribal lord or tribal support card (e.g., "Lord of the Unreal", "Coat of Arms", "Kindred Discovery").
3. Answer does not explain HOW the tribal synergy works (e.g., "lords give +1/+1", "kindred triggers draw cards").
4. Answer lists cards of the tribe without explaining their synergistic interaction.
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. Shared creature type is explicitly identified.
2. At least one tribal lord/support card is named and its effect explained.
3. The mechanism of synergy is explained (buffs, triggers, cost reduction, etc.).
6. At least one question asks about building around a specific tribe.
"""

MECHANIC_SYNERGY_VALIDATION = """
HARD REJECT RULES:
1. Answer does not identify the shared keyword/mechanic (e.g., landfall, magecraft, proliferate).
2. Answer does not explain HOW the mechanic interaction works (e.g., "landfall triggers twice with Yarok", "proliferate adds counters to saga").
3. Answer does not cite relevant rules or reminder text if the interaction is non-obvious.
4. Answer lists cards with the mechanic without explaining the synergy.
5. Answer contains markdown formatting (bold, italics, bullet points).
6. Answer references rule numbers directly.
7. Answer is less than 80 characters.
8. JSON parsing fails.

VALIDATION CHECKLIST:
1. Shared keyword/mechanic is explicitly identified.
2. The interaction mechanism is explained step by step.
3. Relevant rules/reminder text is cited for non-obvious interactions.
4. At least one specific card interaction is detailed (e.g., "Rampaging Baloths + Yarok = two 4/4 beasts per land").
5. At least one question asks about a specific mechanic interaction.
"""


# =============================================================================
# TEMPLATE INSTRUCTIONS
# =============================================================================

COMBO_PIECE_INSTRUCTION = """Generate exactly 3 Q&A pairs for COMBO PIECE synergy questions.
Focus on: What cards combine with the primary card to create an INFINITE combo.
Questions should be phrased as players searching for combo partners: "What combos with [card] for infinite [result]?" or "I have [card], what do I need to go infinite?"
Answers MUST: explain the infinite loop step by step, cite oracle text for each piece, state zone/mana requirements, and name the concrete infinite outcome."""

VALUE_ENGINE_INSTRUCTION = """Generate exactly 3 Q&A pairs for VALUE ENGINE synergy questions.
Focus on: What cards generate RECURRING VALUE over multiple turns with the primary card (not infinite combos).
Questions should be phrased as: "What generates long-term value with [card]?" or "What cards work well with [card] over a long game?"
Answers MUST: explain the value generation per turn/cycle, cite triggers/abilities, state mana investment, and explain sustainability."""

TRIBAL_SYNERGY_INSTRUCTION = """Generate exactly 3 Q&A pairs for TRIBAL SYNERGY questions.
Focus on: What cards of a SHARED CREATURE TYPE synergize with the primary card.
Questions should be phrased as: "What [creature type] cards synergize with [card]?" or "What [creature type] tribal support works with [card]?"
Answers MUST: identify the shared creature type, name at least one tribal lord/support card, explain the synergy mechanism (buffs, triggers, cost reduction), and cite relevant card text."""

MECHANIC_SYNERGY_INSTRUCTION = """Generate exactly 3 Q&A pairs for MECHANIC SYNERGY questions.
Focus on: What cards work well with the primary card's KEYWORD/MECHANIC ability.
Questions should be phrased as: "What cards work well with [card]'s [mechanic] ability?" or "What synergizes with [mechanic] on [card]?"
Answers MUST: identify the shared keyword/mechanic, explain the interaction mechanism, cite rules/reminder text if non-obvious, and give at least one concrete card interaction example."""


# =============================================================================
# SYNERGY DATA BATCH MODEL
# =============================================================================

class SynergyDataBatch:
    """Container for a primary card and its synergy partners from multiple sources."""
    
    def __init__(
        self,
        primary_card: CardWithMetadata,
        combo_partners: list[CardWithMetadata],
        tribal_partners: list[CardWithMetadata],
        mechanic_partners: list[CardWithMetadata],
        commander_partners: list[CardWithMetadata],
        edhrec_tags: list[str],
        combo_descriptions: list[str],
        shared_keywords: list[str],
        creature_types: list[str],
    ):
        self.primary_card = primary_card
        self.combo_partners = combo_partners
        self.tribal_partners = tribal_partners
        self.mechanic_partners = mechanic_partners
        self.commander_partners = commander_partners
        self.edhrec_tags = edhrec_tags
        self.combo_descriptions = combo_descriptions
        self.shared_keywords = shared_keywords
        self.creature_types = creature_types
    
    def has_synergy_data(self) -> bool:
        """Check if there's any synergy data to generate questions from."""
        return bool(
            self.combo_partners or self.tribal_partners or 
            self.mechanic_partners or self.commander_partners
        )
    
    def get_all_partners(self) -> list[CardWithMetadata]:
        """Get all unique synergy partners."""
        seen = set()
        all_partners = []
        for partners in [self.combo_partners, self.tribal_partners, self.mechanic_partners, self.commander_partners]:
            for card in partners:
                if card.name not in seen:
                    seen.add(card.name)
                    all_partners.append(card)
        return all_partners


# =============================================================================
# GENERATOR CLASS
# =============================================================================

class GenerateSynergyQuestions(BaseGenerator[SynergyDataBatch]):
    """Generate synergy discovery Q&A pairs from multiple MTG data sources."""
        
    def __init__(
        self,
        data_access: MTGDataAccess,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 3000,
        save_item: callable = None,
        metrics: ValidationMetrics | None = None,
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
            generator_name="GenerateSynergyQuestions",
            dry_run=dry_run,
            max_regeneration_attempts=max_regeneration_attempts,
            batch_size=batch_size,
            templates_per_item=templates_per_item,
            enable_extra_validation=enable_extra_validation,
            **kwargs,
        )
        self.data_access = data_access
        self._synergy_cache: dict[str, SynergyDataBatch] = {}
        self._primary_cards: list[CardWithMetadata] = []
    
    def get_data_batches(self) -> Iterator[SynergyDataBatch]:
        """Fetch and yield synergy data batches for generation."""
        # Build synergy data on first call
        if not self._primary_cards:
            self._build_synergy_data()
        
        for card in self._primary_cards:
            if self.generated_count >= self.target_count:
                break
            batch = self._synergy_cache.get(card.name)
            if batch and batch.has_synergy_data():
                yield batch
    
    def _build_synergy_data(self) -> None:
        """Build comprehensive synergy data from all sources."""
        print("  → Fetching combo data from Commander Spellbook...")
        combos = self.data_access.get_combos_enriched(limit=5000)
        
        print("  → Fetching commander data from EDHREC...")
        commanders = self.data_access.get_commanders_enriched(limit=500)
        
        print("  → Fetching enriched card data...")
        # Get cards that appear in combos or are popular commanders
        card_names = set()
        for combo in combos:
            for use in combo.uses:
                card_names.add(use.name)
        for cmd in commanders:
            card_names.add(cmd.name)
        
        # Fetch enriched cards in batches
        card_list = list(card_names)[:2000]  # Limit for performance
        cards = self.data_access.get_cards_enriched(
            filters={"name": {"$in": card_list}},
            limit=len(card_list),
            lite=True,
        )
        card_map = {c.name: c for c in cards}
        
        print("  → Building card → synergy partner mappings...")
        
        # Build combo partner mapping
        combo_partners = defaultdict(list)
        combo_descriptions = defaultdict(list)
        for combo in combos:
            card_names_in_combo = [use.name for use in combo.uses]
            for use in combo.uses:
                partners = [u.name for u in combo.uses if u.name != use.name]
                combo_partners[use.name].extend(partners)
                if combo.description:
                    combo_descriptions[use.name].append(combo.description)
        
        # Build tribal partner mapping (shared creature types)
        tribal_partners = defaultdict(list)
        creature_type_map = defaultdict(list)
        for card in cards:
            if card.subtypes:
                for subtype in card.subtypes:
                    if subtype in self._get_creature_types():
                        creature_type_map[subtype].append(card)
        
        for creature_type, type_cards in creature_type_map.items():
            if len(type_cards) >= 3:  # Only meaningful tribes
                for card in type_cards:
                    partners = [c.name for c in type_cards if c.name != card.name]
                    tribal_partners[card.name].extend(partners[:10])  # Limit per tribe
        
        # Build mechanic partner mapping (shared keywords)
        mechanic_partners = defaultdict(list)
        keyword_map = defaultdict(list)
        for card in cards:
            if card.keywords:
                for kw in card.keywords:
                    keyword_map[kw].append(card)
        
        for keyword, kw_cards in keyword_map.items():
            if len(kw_cards) >= 3:
                for card in kw_cards:
                    partners = [c.name for c in kw_cards if c.name != card.name]
                    mechanic_partners[card.name].extend(partners[:10])
        
        # Build commander partner mapping (EDHREC tags)
        commander_partners = defaultdict(list)
        commander_tag_map = defaultdict(list)
        for cmd in commanders:
            if cmd.tags:
                for tag in cmd.tags:
                    commander_tag_map[tag].append(cmd)
        
        for tag, tag_commanders in commander_tag_map.items():
            if len(tag_commanders) >= 2:
                for cmd in tag_commanders:
                    partners = [c.name for c in tag_commanders if c.name != cmd.name]
                    commander_partners[cmd.name].extend(partners[:5])

        # Build commander name map for lookups (commanders are from edhrec, not mtg_json.cards)
        commander_map: dict[str, CommanderWithTags] = {c.name: c for c in commanders}
        
        # Create primary cards list (cards with synergy data)
        primary_cards = []
        for card in cards:
            has_synergy = (
                card.name in combo_partners or 
                card.name in tribal_partners or 
                card.name in mechanic_partners or 
                card.name in commander_partners
            )
            if has_synergy:
                primary_cards.append(card)
        
        # Sort by EDHREC rank (popular cards first)
        primary_cards.sort(key=lambda c: c.edhrec_rank or 999999)
        
        # Build synergy batches
        for card in primary_cards:
            batch = SynergyDataBatch(
                primary_card=card,
                combo_partners=[card_map.get(n) for n in combo_partners.get(card.name, []) if card_map.get(n)],
                tribal_partners=[card_map.get(n) for n in tribal_partners.get(card.name, []) if card_map.get(n)],
                mechanic_partners=[card_map.get(n) for n in mechanic_partners.get(card.name, []) if card_map.get(n)],
                commander_partners=[commander_map.get(n) for n in commander_partners.get(card.name, []) if commander_map.get(n)],
                edhrec_tags=card.edhrec_tags or [],
                combo_descriptions=combo_descriptions.get(card.name, []),
                shared_keywords=card.keywords or [],
                creature_types=[st for st in (card.subtypes or []) if st in self._get_creature_types()],
            )
            self._synergy_cache[card.name] = batch
        
        self._primary_cards = primary_cards
        print(f"  ✓ Built synergy data for {len(primary_cards)} primary cards")
    
    def _get_creature_types(self) -> set[str]:
        """Get set of known creature types for tribal detection."""
        # Common MTG creature types that have tribal support
        return {
            "Human", "Elf", "Goblin", "Merfolk", "Zombie", "Vampire", "Dragon",
            "Spirit", "Soldier", "Wizard", "Warrior", "Cleric", "Rogue", "Shaman",
            "Druid", "Knight", "Angel", "Demon", "Beast", "Sliver", "Ally",
            "Kithkin", "Faerie", "Elemental", "Treefolk", "Scarecrow", "Changeling",
            "God", "Eldrazi", "Phyrexian", "Mutant", "Horror", "Nightmare",
            "Skeleton", "Rat", "Squirrel", "Cat", "Dog", "Wolf", "Bear", "Bird",
            "Fish", "Snake", "Lizard", "Dinosaur", "Hydra", "Sphinx", "Chimera",
            "Construct", "Golem", "Thopter", "Myr", "Artifact Creature", "Vehicle",
        }
    
    def build_prompt(self, template: TemplateConfig, data_batch: SynergyDataBatch) -> str:
        """Build the LLM prompt for a specific template and synergy data."""
        card = data_batch.primary_card
        
        # Select relevant partners based on template
        if template.template_id == "combo_piece":
            partners = data_batch.combo_partners[:8]
            partner_type = "combo partners (infinite combos)"
            extra_context = f"Combo descriptions: {'; '.join(data_batch.combo_descriptions[:3])}"
        elif template.template_id == "value_engine":
            # Value engines often come from combo pieces that aren't infinite, or tribal/mechanic
            partners = (data_batch.combo_partners[:4] + data_batch.tribal_partners[:4] + data_batch.mechanic_partners[:4])[:8]
            partner_type = "value engine partners"
            extra_context = f"EDHREC tags: {', '.join(data_batch.edhrec_tags[:5])}"
        elif template.template_id == "tribal_synergy":
            partners = data_batch.tribal_partners[:8]
            partner_type = f"tribal partners (shared types: {', '.join(data_batch.creature_types[:3])})"
            extra_context = f"Creature types: {', '.join(data_batch.creature_types)}"
        elif template.template_id == "mechanic_synergy":
            partners = data_batch.mechanic_partners[:8]
            partner_type = f"mechanic partners (shared keywords: {', '.join(data_batch.shared_keywords[:5])})"
            extra_context = f"Keywords: {', '.join(data_batch.shared_keywords)}"
        else:
            partners = data_batch.get_all_partners()[:8]
            partner_type = "synergy partners"
            extra_context = ""
        
        if not partners:
            # Fallback - shouldn't happen due to has_synergy_data check
            partners = data_batch.get_all_partners()[:8]
            partner_type = "synergy partners"
        
        # Build partner details
        partner_details = NEW_LINE.join(
            build_card_detail(card_number=i+1, card=p) for i, p in enumerate(partners)
        )
        
        # Primary card detail
        primary_detail = build_card_detail(card_number=0, card=card)
        
        prompt = f"""
{SYSTEM_MESSAGE}

{MTG_NOTATION_LEGEND}

<primary_card>
{primary_detail}
</primary_card>

<synergy_partners>
{partner_details}
</synergy_partners>

<context>
{extra_context}
</context>

<task>
{template.task_instruction}

REQUIREMENTS:
- Questions must be natural and varied — phrased as real players would ask
- Answers must cite specific cards from the <synergy_partners> block
- When explaining WHY a synergy works, quote or paraphrase oracle text from the cards above
- The answer field MUST be a single string (not an array)
- No markdown formatting (bold, italics, bullet points)
- No rule number references — explain mechanics conversationally
- Minimum 80 characters per answer

{OUTPUT_FORMAT}
</task>"""
        
        return prompt
    
    def get_source_category(self) -> str:
        return "synergy"
    
    def get_source_data(self, data_batch: SynergyDataBatch) -> list:
        """Extract source data references for the generated document."""
        sources = [data_batch.primary_card.to_dict()]
        for partners in [data_batch.combo_partners, data_batch.tribal_partners, 
                         data_batch.mechanic_partners, data_batch.commander_partners]:
            for p in partners[:5]:
                sources.append(p.to_dict())
        return sources
    
    def build_context(self, template: TemplateConfig, data_batch: SynergyDataBatch) -> str:
        """Build validation context for the generated Q&A."""
        card = data_batch.primary_card
        
        # Build partner context based on template
        if template.template_id == "combo_piece":
            partners = data_batch.combo_partners[:5]
            partner_type = "combo partners"
            validation_focus = COMBO_PIECE_VALIDATION
        elif template.template_id == "value_engine":
            partners = (data_batch.combo_partners[:3] + data_batch.tribal_partners[:3] + data_batch.mechanic_partners[:3])[:5]
            partner_type = "value engine partners"
            validation_focus = VALUE_ENGINE_VALIDATION
        elif template.template_id == "tribal_synergy":
            partners = data_batch.tribal_partners[:5]
            partner_type = "tribal partners"
            validation_focus = TRIBAL_SYNERGY_VALIDATION
        elif template.template_id == "mechanic_synergy":
            partners = data_batch.mechanic_partners[:5]
            partner_type = "mechanic partners"
            validation_focus = MECHANIC_SYNERGY_VALIDATION
        else:
            partners = data_batch.get_all_partners()[:5]
            partner_type = "synergy partners"
            validation_focus = ""
        
        partner_context = NEW_LINE.join(
            f"  - {p.name}:\n  {p.to_prompt_detail()}"
            for p in partners if p.primary_face.oracle_text
        )
        
        primary_context = f"""Primary Card: {card.name}
Mana Cost: {card.primary_face.mana_cost or 'N/A'}
Type: {card.primary_face.type_line}
Color Identity: {', '.join(card.color_identity) if card.color_identity else 'Colorless'}
Oracle Text: {card.primary_face.oracle_text}
Keywords: {', '.join(card.keywords) if card.keywords else 'None'}
Creature Types: {', '.join(data_batch.creature_types) if data_batch.creature_types else 'N/A'}
EDHREC Rank: {card.edhrec_rank or 'N/A'}
EDHREC Tags: {', '.join(card.edhrec_tags) if card.edhrec_tags else 'None'}

{partner_type.title()} for Validation:
{partner_context}

Combo Descriptions: {'; '.join(data_batch.combo_descriptions[:3]) if data_batch.combo_descriptions else 'None'}

Validation Focus for {template.template_id}:
{validation_focus}"""
        
        return f"""Category: {self.get_source_category()}
Template: {template.template_id}

{primary_context}"""


# =============================================================================
# LEGACY COMPATIBILITY WRAPPER
# =============================================================================

class GenerateSynergyQuestionsLegacy:
    """Legacy wrapper for backward compatibility with main.py"""
    
    def __init__(
        self,
        cards_collection,
        combos_collection,
        save_item: callable,
        models: dict[ModelType, Model],
        validation_pct: float,
        target_count: int = 3000,
        metrics: ValidationMetrics | None = None,
    ):
        self.cards_collection = cards_collection
        self.combos_collection = combos_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics
    
    def generate_synergy_questions(self) -> None:
        """Legacy entry point - delegates to new BaseGenerator implementation."""
        # Create data access
        data_access = MTGDataAccess()
        data_access.connect()
        
        try:
            generator = GenerateSynergyQuestions(
                data_access=data_access,
                models=self.models,
                validation_pct=self.validation_pct,
                target_count=self.target_count,
                save_item=self.save_item,
                metrics=self.metrics,
            )
            generator.generate()
        finally:
            data_access.close()