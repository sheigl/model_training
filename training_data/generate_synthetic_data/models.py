from enum import Enum
from datetime import datetime
import json



class QuestionAnswer:
    def __init__(self, question: str, answer: str):
        self.question = question
        self.answer = answer
        
class QuestionAnswerEnhanced(QuestionAnswer):
    def __init__(self, question: str, answer: str):
        super().__init__(question, answer)
        
        self.category: str | None = None
        self.source_data: list[str] | None = None
        self.validated: bool = False
        self.validation_score: float | None = None
        self.needs_review: bool = True
        self.suggested_fix: str | None = None
        self.content_hash: str | None = None
        self.generated_at: datetime | None = None
        self.version: int = 0
        

class ModelType(Enum):
    GENERATION = "generation"
    VALIDATION = "validation"

class ModelProvider(Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

class Model:
    def __init__(self, name: str, type: ModelType):
        self.name = self._parse_model_name(name)
        self.type = type
        self.provider = self._parse_provider(name)
        self.provider_url = self._parse_provider_host(name)
    
    def _parse_provider(self, model_name: str) -> ModelProvider:
        if "anthropic" in model_name:
            return ModelProvider.ANTHROPIC
        elif "openai" in model_name:
            return ModelProvider.OPENAI
        else:
            return ModelProvider.OLLAMA
    
    def _parse_model_name(self, model_name: str):
        if "anthropic" in model_name:
            return model_name[model_name.rfind(':')+1:]
        elif "openai" in model_name:
            return model_name[model_name.rfind(':')+1:]
        else:
            if "," in model_name:
                return model_name.split(',')[1]
            else:
                return model_name
        
    def _parse_provider_host(self, model_name: str) -> str | None:
        if "," in model_name:
            parts = model_name.split(',')
            return parts[0]
        else:
            return "http://127.0.0.1:11434"
        
class Requirement:
    def __init__(self, name: str, scryfall_query: str, zone_locations: list[str]):
        self.name = name
        self.scryfall_query = scryfall_query
        self.zone_locations = zone_locations

class Card:
    def __init__(self, 
                 name: str, 
                 type: str, 
                 mana_cost: str, 
                 text: str, 
                 subtypes: list[str], 
                 supertypes: list[str], 
                 color_identity: list[str], 
                 zone_locations: list[str]):
        self.name = name
        self.type = type
        self.mana_cost = mana_cost
        self.text = text
        self.subtypes = subtypes
        self.supertypes = supertypes
        self.color_identity = color_identity
        self.zone_locations = zone_locations

class ProjectedCombo:
    def __init__(self, 
                 name: str, 
                 description: str, 
                 cards_in_combo: list[Card], 
                 features: list[str], 
                 requirements: list[Requirement], 
                 notes: str):
        self.name = name
        self.description = description
        self.cards_in_combo = cards_in_combo
        self.features = features
        self.requirements = requirements
        self.notes = notes