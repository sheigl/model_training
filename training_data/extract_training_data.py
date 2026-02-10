"""
Extract High-Quality MTG Training Data from MongoDB
Combines MTGJSON cards, EDHRec articles/guides, and Commander Spellbook combos
"""

from pymongo import MongoClient
import json
import random
from collections import defaultdict
import re

# MongoDB connections
client = MongoClient('mongodb://localhost:27017/')

# Databases
mtg_json_db = client['mtg_json']
edhrec_db = client['edhrec']
spellbook_db = client['commander_spellbook']
rules_db = client['mtg_rules']

# Collections
cards_collection = mtg_json_db['cards']
legalities_collection = mtg_json_db['cardLegalities']
rulings_collection = mtg_json_db['cardRulings']

articles_collection = edhrec_db['articles']
guides_collection = edhrec_db['guides']

combos_collection = spellbook_db['variants']

rules_collection = rules_db['rules']
glossary_collection = rules_db['glossary']
rules_meta_collection = rules_db['meta']


def clean_html(text):
    """Remove HTML tags and clean up text"""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Decode HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&#039;', "'")
    return text.strip()


def extract_card_training_data(max_cards=10000):
    """
    Extract diverse card Q&A from MTGJSON
    Focus on interesting cards with strategic value
    """
    print("\n=== Extracting Card Data ===")
    training_data = []
    
    # Get interesting cards (not basic lands, has text)
    query = {
        'text': {'$exists': True, '$ne': ''},
        'type': {'$not': {'$regex': 'Basic Land'}},
        'language': 'English'
    }
    
    cards = list(cards_collection.find(query).limit(max_cards))
    print(f"Processing {len(cards)} cards...")
    
    for card in cards:
        name = card.get('name', '')
        text = card.get('text', '')
        card_type = card.get('type', '')
        mana_cost = card.get('manaCost', '')
        
        if not name or not text:
            continue
        
        # Q1: What does X do?
        training_data.append({
            "messages": [
                {"role": "user", "content": f"What does {name} do?"},
                {"role": "assistant", "content": f"{name}: {text}"}
            ]
        })
        
        # Q2: Mana cost question
        if mana_cost:
            training_data.append({
                "messages": [
                    {"role": "user", "content": f"What is the mana cost of {name}?"},
                    {"role": "assistant", "content": f"The mana cost of {name} is {mana_cost}."}
                ]
            })
        
        # Q3: Card type question
        if card_type:
            training_data.append({
                "messages": [
                    {"role": "user", "content": f"What type of card is {name}?"},
                    {"role": "assistant", "content": f"{name} is a {card_type}."}
                ]
            })
    
    print(f"Generated {len(training_data)} card training examples")
    return training_data


def extract_card_rulings_data(max_rulings=5000):
    """
    Extract rulings as Q&A about card interactions
    """
    print("\n=== Extracting Card Rulings ===")
    training_data = []
    
    # Group rulings by card UUID
    pipeline = [
        {'$sample': {'size': max_rulings}}
    ]
    
    rulings = list(rulings_collection.aggregate(pipeline))
    print(f"Processing {len(rulings)} rulings...")
    
    # Get card names for UUIDs
    uuid_to_card = {}
    unique_uuids = list(set(r['uuid'] for r in rulings))
    
    for uuid in unique_uuids:
        card = cards_collection.find_one({'uuid': uuid})
        if card:
            uuid_to_card[uuid] = card.get('name', '')
    
    for ruling in rulings:
        uuid = ruling['uuid']
        card_name = uuid_to_card.get(uuid, '')
        ruling_text = ruling.get('text', '')
        
        if not card_name or not ruling_text:
            continue
        
        # Create Q&A about the ruling
        training_data.append({
            "messages": [
                {"role": "user", "content": f"How does {card_name} interact with other cards?"},
                {"role": "assistant", "content": ruling_text}
            ]
        })
    
    print(f"Generated {len(training_data)} ruling examples")
    return training_data


def extract_combo_data_from_list(combos):
    """
    Extract Commander Spellbook combos as strategic Q&A
    """
    print("\n=== Extracting Combo Data ===")
    training_data = []
    
    print(f"Processing {len(combos)} combos...")
    
    for combo in combos:
        # Get card names from combo
        card_names = []
        for card_entry in combo.get('uses', []):
            card = card_entry.get('card', {})
            if card and 'name' in card:
                card_names.append(card['name'])
        
        if len(card_names) < 2:
            continue
        
        description = combo.get('description', '')
        produces = combo.get('produces', [])
        
        if not description:
            continue
        
        # Create combo question
        card_list = ' and '.join(card_names)
        
        # Q1: How does this combo work?
        training_data.append({
            "messages": [
                {"role": "user", "content": f"How does the {card_list} combo work?"},
                {"role": "assistant", "content": description}
            ]
        })
        
        # Q2: What does this combo produce?
        if produces:
            results = []
            for feature in produces:
                feature_info = feature.get('feature', {})
                if feature_info:
                    results.append(feature_info.get('name', ''))
            
            if results:
                result_text = ', '.join(results[:3])  # Limit to top 3
                training_data.append({
                    "messages": [
                        {"role": "user", "content": f"What does {card_names[0]} combo with?"},
                        {"role": "assistant", "content": f"{card_names[0]} combos with {' and '.join(card_names[1:])} to create {result_text}."}
                    ]
                })
    
    print(f"Generated {len(training_data)} combo examples")
    return training_data


def extract_combo_data(max_combos=5000):
    """
    Extract Commander Spellbook combos as strategic Q&A
    (Legacy function - kept for compatibility)
    """
    combos = list(combos_collection.find({'status': 'OK'}).limit(max_combos))
    return extract_combo_data_from_list(combos)


def extract_article_data(max_articles=500):
    """
    Extract strategic content from EDHRec articles
    """
    print("\n=== Extracting Article Data ===")
    training_data = []
    
    articles = list(articles_collection.find().limit(max_articles))
    print(f"Processing {len(articles)} articles...")
    
    for article in articles:
        title = article.get('title', '')
        content = article.get('content', '')
        excerpt = article.get('excerpt', '')
        
        if not title:
            continue
        
        # Clean HTML from content
        clean_content = clean_html(content)
        clean_excerpt = clean_html(excerpt)
        
        # Use excerpt if content is too long
        response_text = clean_excerpt if len(clean_content) > 2000 else clean_content[:2000]
        
        if not response_text or len(response_text) < 100:
            continue
        
        # Q1: Article summary question
        training_data.append({
            "messages": [
                {"role": "user", "content": f"Tell me about {title}"},
                {"role": "assistant", "content": response_text}
            ]
        })
        
        # Q2: Specific topic question from tags
        tags = article.get('tags', [])
        if tags and len(tags) > 0:
            tag = tags[0].get('name', '')
            if tag:
                training_data.append({
                    "messages": [
                        {"role": "user", "content": f"What should I know about {tag} in Commander?"},
                        {"role": "assistant", "content": response_text[:1000]}
                    ]
                })
    
    print(f"Generated {len(training_data)} article examples")
    return training_data


def extract_guide_data():
    """
    Extract structured guide content from EDHRec guides
    """
    print("\n=== Extracting Guide Data ===")
    training_data = []
    
    guides = list(guides_collection.find())
    print(f"Processing {len(guides)} guides...")
    
    for guide in guides:
        title = guide.get('title', '')
        guide_sections = guide.get('guide', [])
        
        if not guide_sections:
            continue
        
        for chapter in guide_sections:
            chapter_title = chapter.get('chapter', '')
            sections = chapter.get('sections', [])
            
            for section in sections:
                section_title = section.get('section', '')
                section_content = section.get('section_content', '')
                
                if not section_content:
                    continue
                
                # Clean HTML
                clean_content = clean_html(section_content)
                
                if len(clean_content) < 100:
                    continue
                
                # Create Q&A from guide section
                question = f"How do I {section_title.lower()}?" if section_title else f"Tell me about {chapter_title}"
                
                training_data.append({
                    "messages": [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": clean_content[:1500]}
                    ]
                })
    
    print(f"Generated {len(training_data)} guide examples")
    return training_data


def extract_comprehensive_rules_data(max_rules=2000):
    """
    Extract training data from Comprehensive Rules
    """
    print("\n=== Extracting Comprehensive Rules Data ===")
    training_data = []
    
    # Check if rules database exists
    try:
        rules_count = rules_collection.count_documents({})
        if rules_count == 0:
            print("WARNING: No rules found in database. Run import_rules_to_mongo.py first!")
            return []
    except Exception as e:
        print(f"WARNING: Cannot access rules database: {e}")
        print("Run import_rules_to_mongo.py first!")
        return []
    
    print(f"Found {rules_count} rules in database")
    
    # Extract keyword abilities (section 702)
    print("Extracting keyword abilities...")
    keyword_rules = list(rules_collection.find({'section': '702'}).limit(500))
    
    # Group keywords by base number
    keyword_groups = {}
    for rule in keyword_rules:
        rule_num = rule['rule_number']
        base_num = rule['section'] + '.' + rule['subsection']
        
        if base_num not in keyword_groups:
            keyword_groups[base_num] = []
        keyword_groups[base_num].append(rule)
    
    for base_num, rules in keyword_groups.items():
        # Try to extract keyword name from first rule
        main_rule = rules[0]
        text = main_rule['text']
        
        # Extract keyword (usually quoted or first word)
        keyword_match = re.search(r'(?:"([^"]+)"|^([A-Z][a-z]+))', text)
        if not keyword_match:
            continue
        
        keyword = keyword_match.group(1) or keyword_match.group(2)
        
        # Combine subrules
        combined = '\n'.join([r['text'] for r in rules[:3]])
        
        # Q1: What is X?
        training_data.append({
            "messages": [
                {"role": "user", "content": f"What is {keyword}?"},
                {"role": "assistant", "content": f"[CR {base_num}] {combined[:1000]}"}
            ]
        })
        
        # Q2: How does X work?
        training_data.append({
            "messages": [
                {"role": "user", "content": f"How does {keyword} work?"},
                {"role": "assistant", "content": f"According to the Comprehensive Rules [CR {base_num}]: {combined[:1000]}"}
            ]
        })
    
    # Extract important game concepts
    print("Extracting game concepts...")
    important_sections = {
        '101': 'The Magic Golden Rules',
        '104': 'Ending the Game',
        '106': 'Mana',
        '110': 'Permanents',
        '113': 'Abilities',
        '117': 'Timing and Priority',
        '120': 'Damage',
        '601': 'Casting Spells',
        '603': 'Handling Triggered Abilities',
        '608': 'Resolving Spells and Abilities',
        '614': 'Replacement Effects',
        '701': 'Keyword Actions',
        '704': 'State-Based Actions',
    }
    
    for section, section_name in important_sections.items():
        section_rules = list(rules_collection.find({'section': section}).limit(5))
        
        if not section_rules:
            continue
        
        combined = '\n\n'.join([f"[CR {r['rule_number']}] {r['text']}" for r in section_rules])
        
        # Create Q&A
        training_data.append({
            "messages": [
                {"role": "user", "content": f"Explain {section_name.lower()}"},
                {"role": "assistant", "content": combined[:1500]}
            ]
        })
        
        training_data.append({
            "messages": [
                {"role": "user", "content": f"What are the rules for {section_name.lower()}?"},
                {"role": "assistant", "content": combined[:1500]}
            ]
        })
    
    # Extract glossary terms
    print("Extracting glossary terms...")
    try:
        glossary_terms = list(glossary_collection.find().limit(200))
        
        for term_doc in glossary_terms:
            term = term_doc['term']
            definition = term_doc['definition']
            
            training_data.append({
                "messages": [
                    {"role": "user", "content": f"What is {term} in Magic?"},
                    {"role": "assistant", "content": definition[:1000]}
                ]
            })
    except Exception as e:
        print(f"Could not extract glossary: {e}")
    
    # Extract random rules for general knowledge
    print("Extracting general rules...")
    random_rules = list(rules_collection.aggregate([
        {'$sample': {'size': min(500, max_rules)}}
    ]))
    
    for rule in random_rules:
        rule_num = rule['rule_number']
        text = rule['text']
        
        training_data.append({
            "messages": [
                {"role": "user", "content": f"What does rule {rule_num} say?"},
                {"role": "assistant", "content": f"[CR {rule_num}] {text[:1000]}"}
            ]
        })
    
    print(f"Generated {len(training_data)} rules examples")
    return training_data


def create_honesty_examples(known_combos):
    """
    Create training examples that teach the model to:
    1. Admit when it doesn't know if cards combo
    2. Distinguish between known combos and speculation
    3. Recommend verification sources
    """
    print("\n=== Creating Honesty Training Examples ===")
    training_data = []
    
    # Get list of known combo card names
    known_card_sets = set()
    for combo in known_combos:
        cards = []
        for card_entry in combo.get('uses', []):
            card = card_entry.get('card', {})
            if card and 'name' in card:
                cards.append(card['name'])
        if len(cards) >= 2:
            known_card_sets.add(tuple(sorted(cards)))
    
    # Example 1: Admit uncertainty for unknown combos
    honesty_templates = [
        {
            "messages": [
                {"role": "user", "content": "Do Fictitious Card A and Fictitious Card B combo?"},
                {"role": "assistant", "content": "I don't have information about a combo between those specific cards in my training data. To verify if they combo, I recommend checking Commander Spellbook (commanderspellbook.com) which has a comprehensive database of known combos. If you share the card text, I can analyze the interaction patterns, but I can't guarantee they form a working combo without verification."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Can Unknown Card X create an infinite loop?"},
                {"role": "assistant", "content": "I don't have specific information about Unknown Card X in my training data. If you can share the card's text, I can look for patterns that typically create infinite loops (like untap abilities, free casting, or bounce effects), but I'd recommend verifying any potential combo on Commander Spellbook to be certain it works."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Is there a combo with Random Card Y?"},
                {"role": "assistant", "content": "I don't have information about Random Card Y in my combo database. If this is a newer card or an uncommon combo piece, I might not know about it. Commander Spellbook is the best resource for comprehensive combo searches - you can search by card name there."}
            ]
        }
    ]
    
    # Example 2: Distinguish known combos from speculation
    speculation_templates = [
        {
            "messages": [
                {"role": "user", "content": "Do you think these cards might combo?"},
                {"role": "assistant", "content": "Based on the patterns I've learned, they might have synergy, but I should be clear: I can only confirm combos I've specifically seen in my training data. For definitive answers about whether cards combo, check Commander Spellbook. I can analyze the card text and suggest if there's potential, but that's different from confirming a working combo."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What happens if I play Card A with Card B?"},
                {"role": "assistant", "content": "If you're asking whether they form an infinite combo, I'd need to check my knowledge of known combos. If I haven't seen this specific combination in combo databases, I can only speculate based on the card text. Would you like me to analyze the interaction, or would you prefer to verify on Commander Spellbook first?"}
            ]
        }
    ]
    
    # Example 3: Confidently explain known combos
    confidence_templates = [
        {
            "messages": [
                {"role": "user", "content": "How does Thassa's Oracle and Demonic Consultation work?"},
                {"role": "assistant", "content": "This is a well-known combo from my training data. Here's how it works:\n\n1. Cast Demonic Consultation, name a card not in your deck\n2. This exiles your entire library\n3. With your library empty, cast Thassa's Oracle\n4. When Oracle enters, its trigger checks devotion and library size\n5. Since your library is empty, you win the game\n\nThis is a common win condition in cEDH."}
            ]
        }
    ]
    
    # Example 4: Explain limitations clearly
    limitation_templates = [
        {
            "messages": [
                {"role": "user", "content": "Can you discover new combos by reading card text?"},
                {"role": "assistant", "content": "I need to be honest about my limitations: I'm trained on known combos from Commander Spellbook and other databases. I can recognize patterns similar to combos I've seen (like 'untap' effects with tap abilities), but I can't logically deduce completely novel combos from card text alone. For new or unusual combinations, I recommend using Commander Spellbook's search or testing in a game. I'm best at explaining combos I've seen, not discovering new ones."}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Are you sure these cards combo?"},
                {"role": "assistant", "content": "I can only be certain if I've seen this exact combo in my training data from Commander Spellbook or similar sources. If I haven't seen it specifically, I should tell you that. I don't have a rules engine, so I can't simulate card interactions - I rely on learned patterns. For verification, always check Commander Spellbook or test in practice."}
            ]
        }
    ]
    
    # Example 5: Teach when to defer to Spellbook
    deferral_templates = [
        {
            "messages": [
                {"role": "user", "content": "Find all combos with Sol Ring."},
                {"role": "assistant", "content": "I can tell you about combos I know involving Sol Ring from my training data, but for a comprehensive search of ALL combos with a specific card, Commander Spellbook is the definitive source. Their database has 76,000+ combo variants and lets you search by card name. Would you like me to explain some well-known Sol Ring combos I'm familiar with, or would you prefer to search the complete database?"}
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What's the best combo in Commander?"},
                {"role": "assistant", "content": "That depends on your definition of 'best' - power level, simplicity, or popularity? I can discuss well-known powerful combos from my training data, but Commander Spellbook tracks popularity metrics if you want data-driven answers. Some consistently powerful combos I know include Thassa's Oracle + Demonic Consultation, but 'best' is meta-dependent."}
            ]
        }
    ]
    
    # Combine all templates
    training_data.extend(honesty_templates * 50)  # Repeat to emphasize
    training_data.extend(speculation_templates * 50)
    training_data.extend(confidence_templates * 30)
    training_data.extend(limitation_templates * 40)
    training_data.extend(deferral_templates * 30)
    
    print(f"Generated {len(training_data)} honesty training examples")
    return training_data


def balance_dataset(all_data, target_total=50000):
    """
    Balance the dataset to have good distribution
    """
    print("\n=== Balancing Dataset ===")
    
    # Shuffle and limit
    random.shuffle(all_data)
    
    if len(all_data) > target_total:
        all_data = all_data[:target_total]
    
    print(f"Final dataset size: {len(all_data)}")
    return all_data


def main():
    print("="*70)
    print("MTG Training Data Extraction from MongoDB")
    print("="*70)
    
    all_training_data = []
    
    # Extract from each source
    all_training_data.extend(extract_card_training_data(max_cards=10000))
    all_training_data.extend(extract_card_rulings_data(max_rulings=3000))
    
    # Get combos for both extraction and honesty training
    combos = list(combos_collection.find({'status': 'OK'}).limit(5000))
    all_training_data.extend(extract_combo_data_from_list(combos))
    
    # Add honesty examples that teach limitations
    all_training_data.extend(create_honesty_examples(combos))
    
    all_training_data.extend(extract_article_data(max_articles=500))
    all_training_data.extend(extract_guide_data())
    
    # Extract comprehensive rules (NEW!)
    all_training_data.extend(extract_comprehensive_rules_data(max_rules=2000))
    
    # Balance dataset
    final_data = balance_dataset(all_training_data, target_total=50000)
    
    # Save to file
    output_file = 'mongodb_mtg_training.jsonl'
    with open(output_file, 'w') as f:
        for example in final_data:
            f.write(json.dumps(example) + '\n')
    
    print(f"\n{'='*70}")
    print(f"✓ Saved {len(final_data)} training examples to {output_file}")
    print(f"{'='*70}")
    
    # Show distribution
    print("\nDataset composition:")
    print(f"  Total examples: {len(final_data)}")
    print(f"  Includes:")
    print(f"    - Card facts and abilities")
    print(f"    - Card rulings and interactions")
    print(f"    - Combo explanations")
    print(f"    - Strategic articles and guides")
    print(f"    - Comprehensive Rules (keywords, game concepts, glossary)")
    print(f"    - Honesty/uncertainty examples")
    print(f"\nYour model will be an expert on MTG cards, combos, strategy, AND rules!")


if __name__ == "__main__":
    main()
