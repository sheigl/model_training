import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import MTG_NOTATION_LEGEND, OUTPUT_FORMAT, REQUIREMENTS_BASE, SYSTEM_MESSAGE, NEW_LINE, build_card_detail, validate_and_loop_with_suggested_fix
from scryfall_mongodb import ScryfallMongo
import random
from typing import Any, Callable
from models import Card, Model, ModelType, ProjectedCombo, QuestionAnswer, QuestionAnswerEnhanced, Requirement
from logger import print
from archetype_models import ArchetypeDocument


class GenerateArchetypes:
    def __init__(
        self,
        card_collection: pymongo.collection.Collection,  # type: ignore
        archetype_collection: pymongo.collection.Collection,  # type: ignore
        scryfall_client: ScryfallMongo, ) -> None:
        self.card_collection = card_collection
        self.archetype_collection = archetype_collection
        self.scryfall_client = scryfall_client
    
    #def __get_scryfall_cards() -> None:
    def __get_archetype_articles(self) -> list[ArchetypeDocument]:
        docs = [ArchetypeDocument.from_dict(d) for d in self.archetype_collection.find()]
        return docs

    def generate_archetypes(self, target_count=5000) -> None:
        """
        Generate deck archetype and strategy Q&A.

        Examples:
        - "How does a stax deck win?"
        - "What are the weaknesses of voltron?"
        - "How do I recognize a storm deck?"
        """
        print(f"\n=== GENERATING {target_count:,} ARCHETYPE QUESTIONS ===")
        
        
        
        for archetype, context in archetypes:
            if len(mongo_documents) >= target_count:
                break

            print(f"  → {archetype}")
            prompt = build_archetype_prompt(archetype, context)

            try:
                response = query_ollama(MODEL_NAME, prompt)
                response = response.replace("```json", "").replace("```", "").strip()
                qa_pairs = json.loads(response)

                for qa in qa_pairs:
                    if 'question' in qa and 'answer' in qa and len(qa['answer']) > 80:
                        is_valid, reason, score = query_ollama.validate_qa(
                            qa['question'], qa['answer'],
                            context=f"Archetype: {archetype}\nContext: {context}",
                            category="archetype"
                        )
                        if is_valid:
                            mongo_documents.append({
                                "question": qa['question'],
                                "answer": qa['answer'],
                                "category": "archetype",
                                "source_data": ["strategy"],
                                "archetype": archetype,
                                "validated": True,
                                "validation_score": score,
                                "needs_review": False
                            })
                            print(f"    ✓ ACCEPTED (score: {score}/10): {qa['question'][:80]}")
                            if len(mongo_documents) >= target_count:
                                break
                        else:
                            print(f"    ✗ REJECTED (score: {score}/10, {reason}): {qa['question'][:80]}")
                    else:
                        print(f"    ✗ REJECTED (too short or missing keys): {str(qa)[:80]}")
            except Exception as e:
                print(f"  ✗ Error for archetype '{archetype}': {type(e).__name__}: {e}")
                continue

        print(f"  ✓ Generated {len(mongo_documents):,} archetype questions")
        return mongo_documents

