"""
Import MTG Comprehensive Rules into MongoDB
Parses the TXT file and creates a structured database
"""

from pymongo import MongoClient
import re
from datetime import datetime
import sys

def parse_comprehensive_rules(filepath):
    """
    Parse the comprehensive rules TXT file into structured format
    Returns: (rules_dict, glossary_dict, metadata)
    """
    print("=== Parsing Comprehensive Rules File ===")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract metadata from header
    metadata = {}
    header_match = re.search(r'These rules are effective as of (.+?)\.', content)
    if header_match:
        metadata['effective_date'] = header_match.group(1)
    
    # Find where glossary starts
    glossary_start = content.find('Glossary')
    if glossary_start != -1:
        rules_content = content[:glossary_start]
        glossary_content = content[glossary_start:]
    else:
        rules_content = content
        glossary_content = ""
    
    # Parse main rules
    # Pattern: "100.1. Rule text here" or "100.1a Some subrule"
    rule_pattern = r'^(\d{3}\.\d+[a-z]*)\.\s+(.+?)(?=^\d{3}\.\d+[a-z]*\.|$)'
    matches = re.findall(rule_pattern, rules_content, re.MULTILINE | re.DOTALL)
    
    rules = {}
    for rule_num, rule_text in matches:
        rule_text = rule_text.strip()
        
        # Parse rule number into components
        parts = rule_num.split('.')
        section = parts[0]  # e.g., "702"
        subsection = parts[1] if len(parts) > 1 else ""  # e.g., "15a"
        
        # Extract base subsection number and letter
        base_subsection = re.match(r'(\d+)', subsection).group(1) if subsection else ""
        subrule_letter = re.search(r'([a-z]+)$', subsection)
        subrule_letter = subrule_letter.group(1) if subrule_letter else ""
        
        rules[rule_num] = {
            'rule_number': rule_num,
            'section': section,
            'subsection': base_subsection,
            'subrule': subrule_letter,
            'text': rule_text,
            'length': len(rule_text)
        }
    
    print(f"Parsed {len(rules)} individual rules")
    
    # Parse glossary if present
    glossary = {}
    if glossary_content:
        # Pattern: "Term\nDefinition text" or "Term: Definition text"
        glossary_pattern = r'^([A-Z][A-Za-z\s\',\-/]+?)(?:\n|:)\s*(.+?)(?=^[A-Z][A-Za-z\s\',\-/]+?(?:\n|:)|$)'
        glossary_matches = re.findall(glossary_pattern, glossary_content, re.MULTILINE | re.DOTALL)
        
        for term, definition in glossary_matches:
            term = term.strip()
            definition = definition.strip()
            if len(term) < 50 and len(definition) > 10:  # Basic validation
                glossary[term] = definition
        
        print(f"Parsed {len(glossary)} glossary terms")
    
    return rules, glossary, metadata


def categorize_rules(rules):
    """
    Categorize rules by section for easier querying
    """
    categories = {
        '1': 'Game Concepts (100-199)',
        '2': 'Parts of a Card (200-299)',
        '3': 'Card Types (300-399)',
        '4': 'Zones (400-499)',
        '5': 'Turn Structure (500-599)',
        '6': 'Spells, Abilities, and Effects (600-699)',
        '7': 'Additional Rules (700-799)',
        '8': 'Multiplayer Rules (800-899)',
        '9': 'Casual Variants (900-999)',
    }
    
    # Add specific important sections
    important_sections = {
        '100': 'General',
        '101': 'The Magic Golden Rules',
        '102': 'Players',
        '103': 'Starting the Game',
        '104': 'Ending the Game',
        '105': 'Colors',
        '106': 'Mana',
        '110': 'Permanents',
        '112': 'Spells',
        '113': 'Abilities',
        '117': 'Timing and Priority',
        '120': 'Damage',
        '301': 'Artifacts',
        '302': 'Creatures',
        '303': 'Enchantments',
        '304': 'Instants',
        '305': 'Lands',
        '306': 'Planeswalkers',
        '307': 'Sorceries',
        '400': 'Zones',
        '401': 'Library',
        '402': 'Hand',
        '403': 'Battlefield',
        '404': 'Graveyard',
        '405': 'Stack',
        '406': 'Exile',
        '407': 'Ante',
        '408': 'Command',
        '500': 'Turn Structure',
        '601': 'Casting Spells',
        '603': 'Handling Triggered Abilities',
        '604': 'Handling Static Abilities',
        '608': 'Resolving Spells and Abilities',
        '614': 'Replacement Effects',
        '701': 'Keyword Actions',
        '702': 'Keyword Abilities',
        '704': 'State-Based Actions',
    }
    
    for rule_num, rule_data in rules.items():
        section = rule_data['section']
        
        # Add category
        century = section[0]
        rule_data['category'] = categories.get(century, 'Other')
        
        # Add section name if known
        rule_data['section_name'] = important_sections.get(section, '')


def import_to_mongodb(rules, glossary, metadata):
    """
    Import parsed rules into MongoDB
    """
    print("\n=== Importing to MongoDB ===")
    
    # Connect to MongoDB
    client = MongoClient('mongodb://root:whatever@localhost:27017/')
    db = client['mtg_rules']
    
    # Clear existing data
    print("Clearing existing collections...")
    db.rules.drop()
    db.glossary.drop()
    db.meta.drop()
    
    # Insert metadata
    print("Inserting metadata...")
    metadata_doc = {
        'version': metadata.get('effective_date', 'Unknown'),
        'import_date': datetime.now(),
        'total_rules': len(rules),
        'total_glossary_terms': len(glossary)
    }
    db.meta.insert_one(metadata_doc)
    
    # Insert rules
    print(f"Inserting {len(rules)} rules...")
    if rules:
        rules_list = list(rules.values())
        db.rules.insert_many(rules_list)
        
        # Create indexes for efficient querying
        print("Creating indexes...")
        db.rules.create_index('rule_number')
        db.rules.create_index('section')
        db.rules.create_index('category')
        db.rules.create_index([('text', 'text')])  # Text search index
    
    # Insert glossary
    if glossary:
        print(f"Inserting {len(glossary)} glossary terms...")
        glossary_docs = [
            {'term': term, 'definition': definition}
            for term, definition in glossary.items()
        ]
        db.glossary.insert_many(glossary_docs)
        db.glossary.create_index('term')
        db.glossary.create_index([('definition', 'text')])
    
    print("\n✓ Import complete!")
    print(f"  Database: mtg_rules")
    print(f"  Collections:")
    print(f"    - rules: {db.rules.count_documents({})} documents")
    print(f"    - glossary: {db.glossary.count_documents({})} documents")
    print(f"    - meta: {db.meta.count_documents({})} documents")


def verify_import():
    """
    Verify the import was successful and show sample data
    """
    print("\n=== Verifying Import ===")
    
    client = MongoClient('mongodb://root:whatever@localhost:27017/')
    db = client['mtg_rules']
    
    # Show metadata
    meta = db.meta.find_one()
    if meta:
        print(f"\nMetadata:")
        print(f"  Effective Date: {meta.get('effective_date', 'Unknown')}")
        print(f"  Import Date: {meta.get('import_date')}")
        print(f"  Total Rules: {meta.get('total_rules')}")
        print(f"  Total Glossary Terms: {meta.get('total_glossary_terms')}")
    
    # Show sample rules
    print(f"\nSample Rules:")
    for rule in db.rules.find().limit(3):
        print(f"  [{rule['rule_number']}] {rule['text'][:100]}...")
    
    # Show sample glossary
    print(f"\nSample Glossary Terms:")
    for term in db.glossary.find().limit(3):
        print(f"  {term['term']}: {term['definition'][:100]}...")
    
    # Show category breakdown
    print(f"\nRules by Category:")
    pipeline = [
        {'$group': {'_id': '$category', 'count': {'$sum': 1}}},
        {'$sort': {'_id': 1}}
    ]
    for cat in db.rules.aggregate(pipeline):
        print(f"  {cat['_id']}: {cat['count']} rules")


def main():
    print("="*70)
    print("MTG Comprehensive Rules MongoDB Importer")
    print("="*70)
    
    # Check for rules file
    rules_file = sys.argv[1]
    
    try:
        # Parse the rules
        rules, glossary, metadata = parse_comprehensive_rules(rules_file)
        
        # Categorize rules
        print("\n=== Categorizing Rules ===")
        categorize_rules(rules)
        print("Rules categorized by section")
        
        # Import to MongoDB
        import_to_mongodb(rules, glossary, metadata)
        
        # Verify
        verify_import()
        
        print("\n" + "="*70)
        print("✓ Rules successfully imported to MongoDB!")
        print("  You can now use extract_training_data.py to generate training data")
        print("="*70)
        
    except FileNotFoundError:
        print(f"\nERROR: {rules_file} not found!")
        print("\nPlease download the Comprehensive Rules:")
        print("1. Visit: https://magic.wizards.com/en/rules")
        print("2. Download the TXT version")
        print("3. Save it as 'comprehensive_rules.txt' in this directory")
        print("4. Run this script again")
        return
    except Exception as e:
        print(f"\nERROR during import: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
