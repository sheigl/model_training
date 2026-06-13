import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, OUTPUT_FORMAT, REQUIREMENTS_BASE, SYSTEM_MESSAGE, NEW_LINE, build_card_detail, validate_and_loop_with_suggested_fix
from constants import COMBO_QUESTION_TEMPLATES
from scryfall_mongodb import ScryfallMongo
import random
from typing import Any, Callable
from models import Card, Model, ModelType, ProjectedCombo, QuestionAnswer, QuestionAnswerEnhanced, Requirement, ValidationMetrics
from logger import print

console = Console()

class GenerateComboQueries:
    def __init__(
        self,
        combos_collection: pymongo.collection.Collection,  # type: ignore
        card_collection: pymongo.collection.Collection,  # type: ignore
        scryfall_client: ScryfallMongo,
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=5000,
        metrics: ValidationMetrics | None = None) -> None:

        self.combos_collection = combos_collection
        self.card_collection = card_collection
        self.scryfall_client = scryfall_client
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics
        

    def generate_combo_queries(self) -> None:
        """Generate combo queries - returns MongoDB documents"""
        
        combos_collection = self.combos_collection
        card_collection = self.card_collection
        scryfall_client = self.scryfall_client
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count
        
        print(f"\n=== GENERATING {target_count:,} COMBO QUERIES ===")
        
        combos = []
        
        with console.status("[bold green]Extracting combo data...") as status:    
            combos = self.__extract_combo_data(combos_collection, card_collection, scryfall_client, target_count, status)
        
        print(f"  → Processing {len(combos):,} cards...")
        
        i: int = 0
        for combo in combos:
            if i >= target_count:
                break
            
            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{target_count:,}...")
            
            combo_name = combo.name        
            # Build prompt
            prompts: list[tuple[str, list[Card], str, dict[str, str]]] = []
            
            description: str = combo.description
            notes: str = combo.notes
            
            numbered_descriptions = (f"Step {i + 1}. {desc}" for i, desc in enumerate(description.split('\n')))
            description = NEW_LINE.join(numbered_descriptions)
            
            if notes:
                description = description + NEW_LINE + NEW_LINE + f"⚠️ WARNING: {notes}" 
                
            cards_in_combo: list[Card] = combo.cards_in_combo
            
            selected_templates = random.sample(COMBO_QUESTION_TEMPLATES, k=2)

            for template in selected_templates:
                prompts.append((
                    self.__build_combo_prompt(
                        cards_in_combo,
                        description,
                        random.choice(combo.features or []),
                        template  # pass template through
                    ),
                    cards_in_combo,
                    description,
                    template
                ))            

            query_model = QueryModel()
            
            for prompt, cards_in_combo, description, template in prompts:         
                try:
                    
                    response =  query_model.query(models[ModelType.GENERATION], prompt)
                    qa_pairs = list(map(lambda qa: QuestionAnswer(qa["question"], qa["answer"]), json.loads(response)))
                    
                    qa_context = f"""
For combo_query category ({template["type"]}): verify the following:
1. The sequence of triggers described matches the order in the provided combo steps. A correct description of individual triggers in the wrong order is still a factual error.
2. The answer explicitly names ALL required combo pieces and explains each one's role.
3. The answer states the concrete outcome matching the COMBO RESULT field — vague phrases like "very powerful" or "wins the game" are validation failures.
4. Oracle text is cited or closely paraphrased when explaining why a trigger fires.

Don't get confused by the abilities on the cards below that have nothing to do with the combo. 
The combo listed below should be considered more than anything else, and is 100% factually accurate and proven. 

Cards:\n{NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards_in_combo))}\nCombo:\n{description}
"""
                    
                    source_data: list[Any] = list(map(lambda c: c.toDict(), cards_in_combo))
                    source_data.append(combo.toDict())

                    is_valid, doc = validate_and_loop_with_suggested_fix(
                        query_model=query_model,
                        models=models,
                        qa_pairs=qa_pairs,
                        validation_pct=validation_pct,
                        enable_extra_validation=False,
                        build_context=lambda: qa_context,
                        source_category="combo_query",
                        source_data=source_data,
                        source_template=template["type"],
                        metrics=self.metrics
                    )
                    
                    if is_valid and doc:
                        save_item(doc)
                
                except Exception as e:
                    print(f"  ✗ Error generating for {combo_name}: {type(e).__name__}: {e}")
                    continue
            
            i = i + 1


    def __build_combo_prompt(
        self,
        cards: list[Card],
        combo: str,
        random_combo_feature: str,
        template: dict  # add this parameter
    ) -> str:
        """Generate combo question prompt with MTG notation guide."""
        requirementList = (f"{i + 1}. {desc}" for i, desc in enumerate(REQUIREMENTS_BASE))
        requirements = NEW_LINE.join(requirementList)
        
        combo_result = f"\nCOMBO RESULT: {random_combo_feature}" if random_combo_feature else ""

        prompt = f"""
    {SYSTEM_MESSAGE}

    {MTG_NOTATION_LEGEND}

    <cards>
    {NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards))}
    </cards>

    <combo>
    AUTHORITATIVE COMBO — treat this as ground truth, overriding any inferences from card text alone:

    {combo}{combo_result}
    </combo>

    <task>
    {template["task_instruction"]}

    REQUIREMENTS:
    {requirements}

    {OUTPUT_FORMAT}
    </task>"""

        return prompt

    # TODO build combo text just like commander spellbook

    # Initial Card State
    #  Sol Ring in hand.
    #  Teferi and Displacer Kitten on the battlefield.
    # Mana Needed
    # ({1} magic symbol)  Magic Symbol (1) available.
    # Steps
    # Cast Sol Ring by paying ({1} magic symbol)  Magic Symbol (1).
    # Displacer Kitten triggers, blinking Teferi.
    # Activate Sol Ring by tapping it, adding ({C} magic symbol)  Magic Symbol (C)({C} magic symbol)  Magic Symbol (C).
    # Activate Teferi's second loyalty ability by removing three loyalty counters from it, returning Sol Ring from the battlefield to your hand and drawing a card.
    # Repeat.
    # Results
    # Infinite card draw.
    # Infinite draw triggers.
    # Near-infinite colorless mana.
    # Near-infinite storm count.

    def __map_combo_cards(self, using_cards: list[dict], cards_collection: pymongo.collection.Collection) -> list[Card]: # type: ignore
        cards: list[Card] = []
        
        for card in using_cards:
            mapped_card = self.__map_using_card(Card(
                name=card.get('card', {}).get('name', 'Unknown'),
                type='',
                mana_cost='',
                text='',
                subtypes=[],
                supertypes=[],
                color_identity=[],
                zone_locations=card.get('zoneLocations', [])
            ), cards_collection
            )
            
            if mapped_card:
                cards.append(mapped_card)
        
        return cards

    # Rarity tiers for stratified sampling (lower score = rarer = higher priority)
    RARE_FEATURES = [
        "Lock", "Infinite combat phases", "Infinite self-mill",
        "Infinite landfall triggers", "Infinite Treasure tokens"
    ]
    MEDIUM_FEATURES = [
        "Infinite +1/+1 counters (single)", "Infinite colored mana",
        "Infinite creature tokens", "Infinite draw triggers",
        "Infinite lifegain triggers", "Infinite colorless mana"
    ]

    def __extract_combo_data(
        self,
        combos_collection: pymongo.collection.Collection,  # pyright: ignore[reportPrivateImportUsage]
        card_collection: pymongo.collection.Collection,  # pyright: ignore[reportPrivateImportUsage]
        scryfall_client: ScryfallMongo,
        target_count: int,
        rich_status: Status) -> list[ProjectedCombo]:
        """Extract combo data from commander spellbook documents using stratified sampling by feature rarity.

        Combos producing rare features (lock, combat phases, self-mill, etc.) get ~4x representation.
        Medium-rarity features get ~2x. Common patterns (ETB/LTB/death/sacrifice) stay at 1x.
        Final pool is shuffled so you don't get blocks of same-type combos.
        """
        pipeline = [
            {"$match": {"status": "OK"}},
            {"$unwind": "$produces"},
            {"$addFields": {
                "produces.rarityScore": {
                    "$switch": {
                        "branches": [
                            {"case": {"$in": ["$produces.feature.name", self.RARE_FEATURES]}, "then": 1},
                            {"case": {"$in": ["$produces.feature.name", self.MEDIUM_FEATURES]}, "then": 2},
                            {"case": True, "then": 3}
                        ]
                    }
                }
            }},
            {"$group": {
                "_id": "$_id",
                "name": {"$first": "$name"},
                "description": {"$first": "$description"},
                "uses": {"$first": "$uses"},
                "produces": {"$push": "$produces"},
                "notes": {"$first": "$notes"},
                "requires": {"$first": "$requires"},
                "bestRarityScore": {"$min": "$produces.rarityScore"}
            }},
            {"$sort": {"bestRarityScore": 1, "_id": 1}},
            # Pull a larger pool biased toward rare features
            {"$limit": target_count + int(target_count * 0.75)}
        ]

        all_combos = list(combos_collection.aggregate(pipeline))
        combos: list[ProjectedCombo] = []
        
        seen_names: set[str] = set()

        for i, combo in enumerate(all_combos):

            rich_status.update(f"[bold green]Extracting combo data... {i+1}/{len(all_combos)}")
            cards: list[dict] = combo.get('uses', [])
            combo_name = "|".join(map(lambda card: card.get('card', {}).get('name', 'Unknown'), cards))

            if combo_name in seen_names:
                continue
            seen_names.add(combo_name)
            
            projected_combo: ProjectedCombo = ProjectedCombo(
                name=combo_name,
                description=combo.get('description', None),
                cards_in_combo=self.__map_combo_cards(cards, card_collection),
                features=self.__map_features(combo),
                requirements=self.__map_requirements(combo),
                notes=combo.get('notes', None)
            )
            
            if len(projected_combo.requirements) > 0:
                for req in projected_combo.requirements:
                    query = req.scryfall_query
                    if not query:
                        continue
                    results = scryfall_client.search_scryfall(query=query)
                    if hasattr(results, 'cards') and  len(results.cards) > 0:
                        random_card = random.choice(results.cards)
                        random_card_mapped = self.__map_using_card(Card(
                            name=random_card.get('name', 'Unknown'),
                            type='',
                            mana_cost='',
                            text='',
                            subtypes=[],
                            supertypes=[],
                            color_identity=[],
                            zone_locations=[]
                        ), card_collection)
                        if random_card_mapped:
                            projected_combo.cards_in_combo.append(random_card_mapped)
                    
            combos.append(projected_combo)
        
        random.shuffle(combos)
        return combos

    def __map_requirements(self, combo: dict) -> list[Requirement]:
        reqs: list[Requirement] = []
        
        if "requires" in combo:
            for req in combo.get('requires', []):
                reqs.append(Requirement(
                    name=req.get('template', {}).get('name', None),
                    scryfall_query=req.get('template', {}).get('scryfallQuery'),
                    zone_locations=req.get('zoneLocations', [])
                ))
        
        return reqs
            
    def __map_features(self, combo: dict) -> list[str]:
        features = []
        if "produces" in combo:
            for feature in combo.get('produces', []):
                features.append(feature.get('feature', {}).get('name', None))
                
        return features
            
    def __map_using_card(self, card: Card, card_collection: pymongo.collection.Collection) -> Card | None: # type: ignore
        mtg_card: dict = card_collection.find_one({"name": card.name}) or {}
        
        if not mtg_card or 'name' not in mtg_card or 'type' not in mtg_card or 'manaCost' not in mtg_card or 'text' not in mtg_card:
            return None
        
        projected_card: Card = Card(
            name=mtg_card.get('name', 'Unknown'),
            type=mtg_card.get('type', 'Unknown'),
            mana_cost=mtg_card.get('manaCost', 'Unknown'),
            text=mtg_card.get('text', ''),
            subtypes=json.loads(mtg_card.get('subtypes', '[]')) if mtg_card.get('subtypes') else [],
            supertypes=json.loads(mtg_card.get('supertypes', '[]')) if mtg_card.get('supertypes') else [],
            color_identity=json.loads(mtg_card.get('colorIdentity', '[]')) if mtg_card.get('colorIdentity') else [],
            zone_locations=card.zone_locations or []
        )
        
        return projected_card
