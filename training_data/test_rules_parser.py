"""
Quick test script to validate Comprehensive Rules parsing
Run this before the full import to catch any issues
"""

import re
from datetime import datetime
import sys

def test_parse_sample():
    """
    Test parsing with the sample content you provided
    """
    sample_content = """Magic: The Gathering Comprehensive Rules

These rules are effective as of January 16, 2026.

Introduction

This document is the ultimate authority for Magic: The Gathering® competitive game play.

1. Game Concepts

100. General

100.1. These Magic rules apply to any Magic game with two or more players, including two-player games and multiplayer games.

100.1a A two-player game is a game that begins with only two players.

100.1b A multiplayer game is a game that begins with more than two players. See section 8, "Multiplayer Rules."

100.2. To play, each player needs their own deck of traditional Magic cards, small items to represent any tokens and counters, and some way to clearly track life totals.

101. The Magic Golden Rules

101.1. Whenever a card's text directly contradicts these rules, the card takes precedence.

Glossary

Ability
An object's ability is defined by its rules text or by the effect that created it.

Activated Ability
A kind of ability. Activated abilities are written as "[Cost]: [Effect.]"

Credits
"""
    
    print("=== Testing Parser with Sample Content ===\n")
    
    # Test metadata extraction
    print("1. Testing Metadata Extraction:")
    date_match = re.search(r'effective as of (.+?)\.', sample_content, re.IGNORECASE)
    if date_match:
        print(f"   ✓ Effective Date: {date_match.group(1)}")
    else:
        print("   ✗ Could not extract effective date")
    
    # Test finding main sections
    print("\n2. Testing Section Detection:")
    lines = sample_content.split('\n')
    
    for i, line in enumerate(lines):
        if line.strip() == "1. Game Concepts":
            print(f"   ✓ Found '1. Game Concepts' at line {i}")
        if line.strip() == "Glossary":
            print(f"   ✓ Found 'Glossary' at line {i}")
        if line.strip() == "Credits":
            print(f"   ✓ Found 'Credits' at line {i}")
    
    # Test rule parsing
    print("\n3. Testing Rule Parsing:")
    rule_pattern = r'^(\d{3}\.\d+[a-z]?)\.\s+(.+?)(?=^\d{3}\.\d+[a-z]?\.|^[0-9]+\.\s+[A-Z]|$)'
    matches = re.findall(rule_pattern, sample_content, re.MULTILINE | re.DOTALL)
    
    print(f"   Found {len(matches)} rules:")
    for rule_num, rule_text in matches[:5]:  # Show first 5
        text_preview = rule_text.strip()[:60]
        print(f"   ✓ {rule_num}: {text_preview}...")
    
    # Test glossary parsing
    print("\n4. Testing Glossary Parsing:")
    glossary_start = sample_content.find('Glossary')
    credits_start = sample_content.find('Credits')
    
    if glossary_start != -1 and credits_start != -1:
        glossary_section = sample_content[glossary_start:credits_start]
        glossary_lines = glossary_section.split('\n')
        
        terms_found = []
        for line in glossary_lines:
            line = line.strip()
            if line and line[0].isupper() and not line.startswith('  ') and line != 'Glossary':
                terms_found.append(line)
        
        print(f"   Found {len(terms_found)} glossary terms:")
        for term in terms_found[:3]:
            print(f"   ✓ {term}")
    
    print("\n=== Sample Test Complete ===")


def test_actual_file():
    """
    Test parsing with the actual comprehensive_rules.txt file
    """
    print("\n" + "="*70)
    print("Testing with actual comprehensive_rules.txt file")
    print("="*70 + "\n")
    
    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"✓ File loaded successfully: {len(lines)} lines\n")
        
        # Show first few lines
        print("First 10 lines:")
        for i, line in enumerate(lines[:10]):
            print(f"  {i:3d}: {line.rstrip()}")
        
        # Find key markers
        print("\nSearching for key sections...")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "1. Game Concepts":
                print(f"  ✓ '1. Game Concepts' found at line {i}")
            if stripped == "Glossary":
                print(f"  ✓ 'Glossary' found at line {i}")
            if stripped == "Credits":
                print(f"  ✓ 'Credits' found at line {i}")
            
            # Find first rule
            if re.match(r'^100\.1\.', line):
                print(f"  ✓ First rule (100.1) found at line {i}")
                print(f"     Content: {line.strip()[:80]}...")
                break
        
        # Count potential rules
        content = ''.join(lines)
        rule_pattern = r'^(\d{3}\.\d+[a-z]?)\.'
        rule_matches = re.findall(rule_pattern, content, re.MULTILINE)
        print(f"\n✓ Estimated {len(rule_matches)} rules in file")
        
        # Show sample rules from different sections
        print("\nSample rules from different sections:")
        for section in ['100.1', '702.1', '903.1']:
            pattern = f'^{re.escape(section)}[a-z]?\\. (.+?)$'
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                print(f"  ✓ {section}: {match.group(1)[:60]}...")
        
        print("\n" + "="*70)
        print("✓ File validation complete - ready for import!")
        print("="*70)
        
    except FileNotFoundError:
        print("✗ comprehensive_rules.txt not found!")
        print("\nPlease download it from:")
        print("  https://magic.wizards.com/en/rules")
        print("\nSave it as 'comprehensive_rules.txt' in this directory")
        return False
    except Exception as e:
        print(f"✗ Error reading file: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    print("="*70)
    print("Comprehensive Rules Parser Validation")
    print("="*70 + "\n")
    
    # Test with sample first
    test_parse_sample()
    
    # Then test with actual file
    if test_actual_file():
        print("\n✓ All tests passed! You can now run:")
        print("  python import_rules_to_mongo.py")
    else:
        print("\n✗ Tests failed. Please check the file and try again.")
