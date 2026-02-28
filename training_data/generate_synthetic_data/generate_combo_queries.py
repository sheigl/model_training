import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, build_card_detail
from scryfall_mongodb import ScryfallMongo
import random
from typing import Any, Callable
from models import Card, Model, ModelType, ProjectedCombo, Requirement

console = Console()

def build_combo_prompt(cards: list[Card], combo: str, random_combo_feature: str) -> str:
    """Generate combo question prompt with MTG notation guide."""
    
    prompt = f"""{MTG_NOTATION_LEGEND}

Generate 3 natural Q&A pairs about combos with the cards below. Make sure at least one of the questions is from the perspective of a player that doesn't know the extact combo or the cards, but may have an idea of a combo or looking for a combo. For example: "What combo can I make with {", ".join(map(lambda card: card.name, cards))}?" or "How can I make a {random_combo_feature} combo?".

Cards:
{NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards))}

Combo:
{combo}

Output JSON:
[
{{"question": "...", "answer": "..."}},
{{"question": "...", "answer": "..."}},
{{"question": "...", "answer": "..."}}
]

Make questions varied and natural. Base answers on combo data above.
Explain how the combos work and what they achieve.
Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
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

def map_combo_cards(using_cards: list[dict], cards_collection: pymongo.collection.Collection) -> list[Card]: # type: ignore
    cards: list[Card] = []
    
    for card in using_cards:
        mapped_card = map_using_card(Card(
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

def extract_combo_data(
    combos_collection: pymongo.collection.Collection,  # pyright: ignore[reportPrivateImportUsage]
    card_collection: pymongo.collection.Collection,  # pyright: ignore[reportPrivateImportUsage]
    scryfall_client: ScryfallMongo,
    target_count: int,
    rich_status: Status) -> list[ProjectedCombo]:
    """Extract combo data from commander spellbook documents and prepare for prompt generation."""
    all_combos = list(combos_collection.find({'status': 'OK'}).limit(target_count + 100))
    combos: list[ProjectedCombo] = []
    
    for i, combo in enumerate(all_combos):
        rich_status.update(f"[bold green]Extracting combo data... {i+1}/{len(all_combos)}")
        cards: list[dict] = combo.get('uses', [])
        combo_name = "|".join(map(lambda card: card.get('card', {}).get('name', 'Unknown'), cards))
        
        if len(list(filter(lambda combo: combo.name == combo_name, combos))) > 0:
            continue
        
        projected_combo: ProjectedCombo = ProjectedCombo(
            name=combo_name,
            description=combo.get('description', None),
            cards_in_combo=map_combo_cards(cards, card_collection),
            features=map_features(combo),
            requirements=map_requirements(combo),
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
                    random_card_mapped = map_using_card(Card(
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

def map_requirements(combo: dict) -> list[Requirement]:
    reqs: list[Requirement] = []
    
    if "requires" in combo:
        for req in combo.get('requires', []):
            reqs.append(Requirement(
                name=req.get('template', {}).get('name', None),
                scryfall_query=req.get('template', {}).get('scryfallQuery'),
                zone_locations=req.get('zoneLocations', [])
            ))
    
    return reqs
        
def map_features(combo: dict) -> list[str]:
    features = []
    if "produces" in combo:
        for feature in combo.get('produces', []):
            features.append(feature.get('feature', {}).get('name', None))
            
    return features
        
def map_using_card(card: Card, card_collection: pymongo.collection.Collection) -> Card | None: # type: ignore
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

def generate_combo_queries(
    combos_collection: pymongo.collection.Collection,  # type: ignore
    card_collection: pymongo.collection.Collection,  # type: ignore
    scryfall_client: ScryfallMongo, 
    save_item: Callable[[dict], None], 
    models: dict[ModelType, Model],
    validation_pct: int,
    target_count=5000) -> None:
    """Generate combo queries - returns MongoDB documents"""
    print(f"\n=== GENERATING {target_count:,} COMBO QUERIES ===")
    
    combos = []
    
    with console.status("[bold green]Extracting combo data...") as status:    
        combos = extract_combo_data(combos_collection, card_collection, scryfall_client, target_count, status)
    
    print(f"  → Processing {len(combos):,} cards...")
    
    i: int = 0
    for combo in combos:
        if i >= target_count:
            break
        
        if (i + 1) % 100 == 0:
            print(f"    Generated {i:,}/{target_count:,}...")
        
        combo_name = combo.name        
        # Build prompt
        prompts: list[tuple[str, list[Card], str]] = []
        
        description: str = combo.description
        notes: str = combo.notes
        
        numbered_descriptions = (f"Step {i + 1}. {desc}" for i, desc in enumerate(description.split('\n')))
        description = NEW_LINE.join(numbered_descriptions)
        
        if notes:
            description = description + NEW_LINE + NEW_LINE + f"*{notes}" 
            
        cards_in_combo: list[Card] = combo.cards_in_combo
        
        prompts.append((build_combo_prompt(cards_in_combo, description, random.choice(combo.features or [])), cards_in_combo, description))
        
        query_model = QueryModel()
        
        for prompt, cards_in_combo, description in prompts:         
            try:
                
                response =  query_model.query(models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for enumerated_i, qa in enumerate(qa_pairs):
                    if random.random() > validation_pct:
                        continue
                    
                    if 'question' in qa and 'answer' in qa:            
                        
                        iteration = 0
                        
                        while True:
                            # Validate
                            # Create MongoDB document

                            qa_context =f"""
- For combo_query category: also verify that the sequence of triggers described matches the order in the provided combo steps. A correct description of individual triggers in the wrong order is still a factual error.

Cards:\n{NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards_in_combo))}\nCombo:\n{description}
                                """
                            
                            is_valid, reason, score, suggested_fix = query_model.validate_qa(
                                validation_model=models[ModelType.VALIDATION],
                                question=qa['question'], 
                                answer=qa['answer'],
                                context=qa_context,
                                category="combo_query",
                                enable_extra_validation=False
                            )
                            
                            if not is_valid and suggested_fix:
                                print(f"    ✗ REJECTED but suggested fix provided: {suggested_fix}. Applying fix and re-validating...")
                                qa['answer'] = suggested_fix
                                iteration += 1
                                if iteration >= 3:
                                    print(f"    ✗ REJECTED after 3 iterations, moving on.")
                                    break
                                continue
                            
                            if is_valid:
                                doc = {
                                    "question": qa['question'],
                                    "answer": qa['answer'],
                                    "category": "combo_query",
                                    "source_data": [combo_name],
                                    "validated": True,
                                    "validation_score": score,
                                    "needs_review": False,
                                    "suggested_fix": suggested_fix if not is_valid else None
                                }
                                
                                save_item(doc)
                                
                                print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                                
                            else:
                                print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            
            except Exception as e:
                print(f"  ✗ Error generating for {combo_name}: {type(e).__name__}: {e}")
                continue
        
        i = i + 1
