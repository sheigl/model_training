from enum import Enum
class ModelType(Enum):
    GENERATION = "generation"
    VALIDATION = "validation"

class Model:
    def __init__(self, name: str, type: ModelType):
        self.name = name
        self.type = type

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