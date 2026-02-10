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
        lines = f.readlines()
    
    # Extract metadata from header
    metadata = {}
    for line in lines[:20]:
        if 'effective as of' in line.lower():
            date_match = re.search(r'effective as of (.+?)\.', line, re.IGNORECASE)
            if date_match:
                metadata['effective_date'] = date_match.group(1)
                break
    
    # Find where rules actually start by looking for rule "100.1"
    # The file has a table of contents, so section headers appear twice
    rules_start_idx = None
    glossary_start_idx = None
    
    for i, line in enumerate(lines):
        # Find first rule
        if rules_start_idx is None and re.match(r'^100\.1\.', line):
            rules_start_idx = i
            print(f"Found first rule (100.1) at line {i}")
        
        # Find glossary - it comes AFTER all the rules
        # Look for "Glossary" that's followed by glossary terms (capitalized words)
        if rules_start_idx is not None and i > rules_start_idx + 1000:  # Must be after rules
            if line.strip() == "Glossary":
                # Verify next few lines look like glossary entries
                if i + 5 < len(lines):
                    # Check if next non-empty lines start with capital letters (glossary terms)
                    next_lines = [lines[i+j].strip() for j in range(1, 6) if i+j < len(lines) and lines[i+j].strip()]
                    if next_lines and any(l[0].isupper() for l in next_lines if l):
                        glossary_start_idx = i
                        print(f"Found Glossary section at line {i}")
                        break
    
    # Extract rules section
    if rules_start_idx is not None:
        if glossary_start_idx is not None:
            rules_lines = lines[rules_start_idx:glossary_start_idx]
            print(f"Extracting rules from line {rules_start_idx} to {glossary_start_idx}")
        else:
            rules_lines = lines[rules_start_idx:]
            print(f"Extracting rules from line {rules_start_idx} to end of file")
        print(f"Total lines in rules section: {len(rules_lines)}")
    else:
        print("ERROR: Could not find start of rules (looking for rule 100.1)")
        return {}, {}, metadata
    
    # Join lines back for rule parsing
    rules_content = ''.join(rules_lines)
    
    # Parse individual rules
    # The key is to match "XXX.Y[a-z]. " at the start of a line
    # and capture everything until the next rule starts
    rules = {}
    
    # First, let's try a line-by-line approach which is more reliable
    current_rule = None
    current_text = []
    
    for line in rules_lines:
        # Check if this line starts a new rule: "100.1. " or "100.1a. "
        rule_start = re.match(r'^(\d{3}\.\d+[a-z]?)\.\s+(.*)$', line)
        
        if rule_start:
            # Save previous rule if exists
            if current_rule and current_text:
                text = ' '.join(current_text).strip()
                if len(text) >= 10:  # Only save rules with substantial text
                    # Parse rule number into components
                    parts = current_rule.split('.')
                    section = parts[0]
                    subsection = parts[1] if len(parts) > 1 else ""
                    
                    # Extract base subsection number and letter
                    base_subsection_match = re.match(r'(\d+)', subsection)
                    base_subsection = base_subsection_match.group(1) if base_subsection_match else ""
                    
                    subrule_match = re.search(r'([a-z]+)$', subsection)
                    subrule_letter = subrule_match.group(1) if subrule_match else ""
                    
                    rules[current_rule] = {
                        'rule_number': current_rule,
                        'section': section,
                        'subsection': base_subsection,
                        'subrule': subrule_letter,
                        'text': text,
                        'length': len(text)
                    }
            
            # Start new rule
            current_rule = rule_start.group(1)
            current_text = [rule_start.group(2)] if rule_start.group(2).strip() else []
        
        elif current_rule and line.strip():
            # This is a continuation of the current rule
            current_text.append(line.strip())
        
        # Check if we've hit a section header (means rules section ended)
        elif re.match(r'^[0-9]+\.\s+[A-Z]', line):
            break
    
    # Don't forget the last rule
    if current_rule and current_text:
        text = ' '.join(current_text).strip()
        if len(text) >= 10:
            parts = current_rule.split('.')
            section = parts[0]
            subsection = parts[1] if len(parts) > 1 else ""
            
            base_subsection_match = re.match(r'(\d+)', subsection)
            base_subsection = base_subsection_match.group(1) if base_subsection_match else ""
            
            subrule_match = re.search(r'([a-z]+)$', subsection)
            subrule_letter = subrule_match.group(1) if subrule_match else ""
            
            rules[current_rule] = {
                'rule_number': current_rule,
                'section': section,
                'subsection': base_subsection,
                'subrule': subrule_letter,
                'text': text,
                'length': len(text)
            }
    
    print(f"Parsed {len(rules)} individual rules")
    
    # Parse glossary if present
    glossary = {}
    if glossary_start_idx is not None:
        # Glossary goes to end of file
        glossary_lines = lines[glossary_start_idx:]
        print(f"Extracting glossary from line {glossary_start_idx} to end of file")
        
        # Parse glossary entries
        current_term = None
        current_definition = []
        
        for line in glossary_lines:
            line = line.strip()
            
            # Skip empty lines and the "Glossary" header
            if not line or line == "Glossary":
                continue
            
            # Check if this looks like a new term
            # Terms typically start at column 0 and are capitalized
            # Definitions are typically indented or continue from the term
            if line and not line.startswith(' ') and not line.startswith('\t'):
                # This might be a new term
                # Check if it's actually a term or continuation
                # Terms usually have definitions on the same or next line
                
                # Save previous term if exists
                if current_term and current_definition:
                    definition_text = ' '.join(current_definition).strip()
                    if len(definition_text) > 10:
                        glossary[current_term] = definition_text
                
                # Check if this line has both term and definition
                # Format 1: "Term: Definition"
                # Format 2: "Term\nDefinition"
                if ':' in line:
                    parts = line.split(':', 1)
                    current_term = parts[0].strip()
                    current_definition = [parts[1].strip()] if parts[1].strip() else []
                else:
                    # Term is on its own line, definition comes next
                    # But only if it looks like a term (not a continuation)
                    if line[0].isupper() or line[0].isnumeric():
                        current_term = line.strip()
                        current_definition = []
                    elif current_term:
                        # This is a continuation of the previous definition
                        current_definition.append(line)
            else:
                # This is a continuation of the current definition (indented)
                if current_term:
                    current_definition.append(line)
        
        # Don't forget the last term
        if current_term and current_definition:
            definition_text = ' '.join(current_definition).strip()
            if len(definition_text) > 10:
                glossary[current_term] = definition_text
        
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
    
    # Detailed section names from the actual rules document
    section_names = {
        '100': 'General',
        '101': 'The Magic Golden Rules',
        '102': 'Players',
        '103': 'Starting the Game',
        '104': 'Ending the Game',
        '105': 'Colors',
        '106': 'Mana',
        '107': 'Numbers and Symbols',
        '108': 'Cards',
        '109': 'Objects',
        '110': 'Permanents',
        '111': 'Tokens',
        '112': 'Spells',
        '113': 'Abilities',
        '114': 'Emblems',
        '115': 'Targets',
        '116': 'Special Actions',
        '117': 'Timing and Priority',
        '118': 'Costs',
        '119': 'Life',
        '120': 'Damage',
        '121': 'Drawing a Card',
        '122': 'Counters',
        '123': 'Stickers',
        '200': 'General',
        '201': 'Name',
        '202': 'Mana Cost and Color',
        '203': 'Illustration',
        '204': 'Color Indicator',
        '205': 'Type Line',
        '206': 'Expansion Symbol',
        '207': 'Text Box',
        '208': 'Power/Toughness',
        '209': 'Loyalty',
        '210': 'Defense',
        '211': 'Hand Modifier',
        '212': 'Life Modifier',
        '213': 'Information Below the Text Box',
        '300': 'General',
        '301': 'Artifacts',
        '302': 'Creatures',
        '303': 'Enchantments',
        '304': 'Instants',
        '305': 'Lands',
        '306': 'Planeswalkers',
        '307': 'Sorceries',
        '308': 'Kindreds',
        '309': 'Dungeons',
        '310': 'Battles',
        '311': 'Planes',
        '312': 'Phenomena',
        '313': 'Vanguards',
        '314': 'Schemes',
        '315': 'Conspiracies',
        '400': 'General',
        '401': 'Library',
        '402': 'Hand',
        '403': 'Battlefield',
        '404': 'Graveyard',
        '405': 'Stack',
        '406': 'Exile',
        '407': 'Ante',
        '408': 'Command',
        '500': 'General',
        '501': 'Beginning Phase',
        '502': 'Untap Step',
        '503': 'Upkeep Step',
        '504': 'Draw Step',
        '505': 'Main Phase',
        '506': 'Combat Phase',
        '507': 'Beginning of Combat Step',
        '508': 'Declare Attackers Step',
        '509': 'Declare Blockers Step',
        '510': 'Combat Damage Step',
        '511': 'End of Combat Step',
        '512': 'Ending Phase',
        '513': 'End Step',
        '514': 'Cleanup Step',
        '600': 'General',
        '601': 'Casting Spells',
        '602': 'Activating Activated Abilities',
        '603': 'Handling Triggered Abilities',
        '604': 'Handling Static Abilities',
        '605': 'Mana Abilities',
        '606': 'Loyalty Abilities',
        '607': 'Linked Abilities',
        '608': 'Resolving Spells and Abilities',
        '609': 'Effects',
        '610': 'One-Shot Effects',
        '611': 'Continuous Effects',
        '612': 'Text-Changing Effects',
        '613': 'Interaction of Continuous Effects',
        '614': 'Replacement Effects',
        '615': 'Prevention Effects',
        '616': 'Interaction of Replacement and/or Prevention Effects',
        '700': 'General',
        '701': 'Keyword Actions',
        '702': 'Keyword Abilities',
        '703': 'Turn-Based Actions',
        '704': 'State-Based Actions',
        '705': 'Flipping a Coin',
        '706': 'Rolling a Die',
        '707': 'Copying Objects',
        '708': 'Face-Down Spells and Permanents',
        '709': 'Split Cards',
        '710': 'Flip Cards',
        '711': 'Leveler Cards',
        '712': 'Double-Faced Cards',
        '713': 'Substitute Cards',
        '714': 'Saga Cards',
        '715': 'Adventurer Cards',
        '716': 'Class Cards',
        '717': 'Attraction Cards',
        '718': 'Prototype Cards',
        '719': 'Case Cards',
        '720': 'Omen Cards',
        '721': 'Station Cards',
        '722': 'Controlling Another Player',
        '723': 'Ending Turns and Phases',
        '724': 'The Monarch',
        '725': 'The Initiative',
        '726': 'Restarting the Game',
        '727': 'Rad Counters',
        '728': 'Subgames',
        '729': 'Merging with Permanents',
        '730': 'Day and Night',
        '731': 'Taking Shortcuts',
        '732': 'Handling Illegal Actions',
        '800': 'General',
        '801': 'Limited Range of Influence Option',
        '802': 'Attack Multiple Players Option',
        '803': 'Attack Left and Attack Right Options',
        '804': 'Deploy Creatures Option',
        '805': 'Shared Team Turns Option',
        '806': 'Free-for-All Variant',
        '807': 'Grand Melee Variant',
        '808': 'Team vs. Team Variant',
        '809': 'Emperor Variant',
        '810': 'Two-Headed Giant Variant',
        '811': 'Alternating Teams Variant',
        '900': 'General',
        '901': 'Planechase',
        '902': 'Vanguard',
        '903': 'Commander',
        '904': 'Archenemy',
        '905': 'Conspiracy Draft',
    }
    
    for rule_num, rule_data in rules.items():
        section = rule_data['section']
        
        # Add category
        century = section[0]
        rule_data['category'] = categories.get(century, 'Other')
        
        # Add section name if known
        rule_data['section_name'] = section_names.get(section, '')


def import_to_mongodb(rules, glossary, metadata):
    """
    Import parsed rules into MongoDB
    """
    print("\n=== Importing to MongoDB ===")
    
    # Connect to MongoDB with authentication
    client = MongoClient(
        'mongodb://localhost:27017/',
        username='root',
        password='whatever',
        authSource='admin'
    )
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
    
    client = MongoClient(
        'mongodb://localhost:27017/',
        username='root',
        password='whatever',
        authSource='admin'
    )
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
    
    # Get rules file from command line argument
    if len(sys.argv) > 1:
        rules_file = sys.argv[1]
        print(f"Using file: {rules_file}\n")
    else:
        rules_file = 'comprehensive_rules.txt'
        print(f"Using default file: {rules_file}\n")
    
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
        print("   OR pass the file path as an argument:")
        print("   python import_rules_to_mongo.py /path/to/rules.txt")
        return
    except Exception as e:
        print(f"\nERROR during import: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
