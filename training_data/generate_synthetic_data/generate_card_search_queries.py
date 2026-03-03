import random
from typing import Callable
from models import Card, ModelType, Model
import pymongo
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, NEW_LINE, map_card, build_card_detail

class GenerateCardSearchQueries:
    def __init__(
        self,
        cards_collection: pymongo.collection.Collection,  # type: ignore 
        save_item: Callable[[dict], None], 
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count=3000) -> None:
        self.cards_collection = cards_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.query_model = QueryModel()

    def generate_card_search_queries(self) -> None:
        """Generate card search queries - returns MongoDB documents"""
        
        cards_collection = self.cards_collection
        save_item = self.save_item
        models = self.models
        validation_pct = self.validation_pct
        target_count = self.target_count
        
        print(f"\n=== GENERATING {target_count:,} CARD SEARCH QUERIES ===")
        
        search_patterns = [
            {'name': 'Green ramp', 'query': {'text': {'$regex': 'search.*land', '$options': 'i'}, 'colors': ['G']}},
            {'name': 'Zombie tokens', 'query': {'text': {'$regex': 'zombie.*token', '$options': 'i'}}},
            {'name': 'Treasure tokens', 'query': {'text': {'$regex': 'treasure', '$options': 'i'}}},
            {'name': 'White removal', 'query': {'text': {'$regex': 'exile|destroy', '$options': 'i'}, 'colors': ['W']}},
            {'name': 'Blue card draw', 'query': {'text': {'$regex': 'draw.*card', '$options': 'i'}, 'colors': ['U']}},
            {'name': 'ETB effects', 'query': {'text': {'$regex': 'enters the battlefield', '$options': 'i'}}},
            {'name': 'Black removal', 'query': {'text': {'$regex': 'destroy.*creature', '$options': 'i'}, 'colors': ['B']}},
            {'name': 'Red burn', 'query': {'text': {'$regex': 'deals.*damage', '$options': 'i'}, 'colors': ['R']}},
        ]
        
        num_docs = 0
        
        for pattern in search_patterns:
            if num_docs >= target_count:
                break
            
            print(f"  → {pattern['name']}")
            
            def map_matching_cards(card: dict) -> Card:
                return map_card(card) # pyright: ignore[reportReturnType]
            
            matching_cards = list(map(map_matching_cards, cards_collection.find(pattern['query'], {'name': 1, 'text': 1, 'manaCost': 1}).limit(15)))
            
            if not matching_cards:
                continue
            
            card_names = [c.name for c in matching_cards]
            
            prompt = self.__build_card_search_prompt(pattern, matching_cards[:10])

            try:
                response = self.query_model.query(self.models[ModelType.GENERATION], prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)
                
                for qa in qa_pairs:
                    
                    should_validate = True

                    if random.random() > validation_pct:
                        should_validate = False
                    
                    if 'question' in qa and 'answer' in qa:
                        mentioned = sum(1 for name in card_names if name in qa['answer'])

                        if mentioned >= 2:
                            is_valid, reason, score, suggested_fix = self.query_model.validate_qa(
                                self.models[ModelType.VALIDATION],
                                qa['question'], qa['answer'],
                                context=f"Search pattern: {pattern['name']}\nMatching cards: {card_info}",
                                category="card_search"
                            )
                            if is_valid:
                                mongo_documents.append({
                                    "question": qa['question'],
                                    "answer": qa['answer'],
                                    "category": "card_search",
                                    "source_data": card_names[:5],
                                    "search_pattern": pattern['name'],
                                    "validated": True,
                                    "validation_score": score,
                                    "needs_review": False
                                })
                                print(f"    ✓ ACCEPTED (score: {score}/10, {mentioned} cards): {qa['question'][:80]}")
                                if len(mongo_documents) >= target_count:
                                    break
                            else:
                                print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                        else:
                            print(f"    ✗ REJECTED (only {mentioned}/2 cards mentioned): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (missing question/answer keys): {qa}")
            except Exception as e:
                print(f"  ✗ Error generating for {pattern['name']}: {type(e).__name__}: {e}")
                continue
            
            num_docs = num_docs + 1

        print(f"  ✓ Generated {num_docs:,} card search queries")
    
    def __build_card_search_prompt(self, pattern: dict, cards: list[Card]) -> str:
        """Generate card search prompt with MTG notation guide."""
        
        prompt = f"""{MTG_NOTATION_LEGEND}

    Generate 5 Q&A pairs for: {pattern['name']}

    Example cards:
    {NEW_LINE.join(map(lambda c: build_card_detail(card_number=None, card=c), cards))}

    Output JSON with natural questions and helpful answers listing 3-5 best cards.
    Answers should explain what the cards do and why they're good for this purpose.
    Output ONLY valid JSON. The answer MUST be a string and not an array of strings."""
        return prompt