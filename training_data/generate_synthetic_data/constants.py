#global MODEL_NAME
MODEL_NAME="qwen2.5:14b"  # Change to 14B when ready

NEW_LINE = "\n"

# Rule sections that are most relevant for gameplay scenarios
RELEVANT_RULE_SECTIONS = [
    '1',   # Game Concepts
    '2',   # Parts of a Card
    '3',   # Card Types
    '4',   # Zones
    '5',   # Turn Structure
    '6',   # Spells, Abilities, and Effects
    '7',   # Additional Rules
    '8',   # Multiplayer Rules
    '9',   # Casual Variants
    '10',  # Commander
    '70',  # Keywords
    '702', # Keyword Abilities
    '704', # State-Based Actions
    '706', # Copying Objects
    '707', # Face-Down Spells and Permanents
    '708', # Split Cards
    '717', # Meld Cards
    '722', # Convenience Actions
]

# Complex sections worth generating edge case questions for
COMPLEX_RULE_SECTIONS = {
    '116': 'Timing and Priority',
    '117': 'Costs',
    '118': 'Paying Costs',
    '119': 'Life',
    '120': 'Damage',
    '121': 'Drawing a Card',
    '122': 'Counters',
    '400': 'General Zone Rules',
    '601': 'Casting Spells',
    '602': 'Activating Activated Abilities',
    '603': 'Handling Triggered Abilities',
    '604': 'Handling Static Abilities',
    '608': 'Resolving Spells and Abilities',
    '700': 'General Additional Rules',
    '701': 'Keyword Actions',
    '702': 'Keyword Abilities',
    '704': 'State-Based Actions',
    '706': 'Copying Objects',
    '800': 'Multiplayer Rules',
    '903': 'Commander',
}

# =============================================================================
# MTG NOTATION LEGEND
# =============================================================================

MTG_NOTATION_LEGEND = """
MTG NOTATION GUIDE:
- {T}: Tap symbol (rotate card 90°, can only use if untapped)
- {C}: Colorless mana
- {W}: White mana
- {U}: Blue mana  
- {B}: Black mana
- {R}: Red mana
- {G}: Green mana
- {X}: Variable amount chosen when casting
- {1}, {2}, {3}, etc.: Generic mana (can be paid with any color or colorless)
- Example: {2}{U}{U} = 2 generic + 2 blue mana = 4 total mana

CARD TYPES:
- Creature: Can attack/block, has summoning sickness (can't tap or attack first turn)
- Artifact: Permanent that stays on battlefield, no summoning sickness
- Enchantment: Permanent that stays on battlefield
- Instant: Cast anytime, goes to graveyard after resolving
- Sorcery: Cast only on your turn, goes to graveyard after resolving
- Land: Played once per turn (not cast), produces mana

KEY MECHANICS:
- ETB (Enters the Battlefield): Triggers when permanent comes into play
- Summoning Sickness: Creatures can't tap or attack the turn they enter
- Sacrifice: Put into graveyard as a cost (can't be prevented)
- Destroy: Put into graveyard (can be prevented by indestructible)
- Exile: Remove from game (harder to recover than graveyard)
"""

# =============================================================================
# INSTRUCTION BLOCKS FOR PROMPTS
# =============================================================================

CARD_COMPARISON_INSTRUCTIONS = """
CRITICAL ANALYSIS REQUIREMENTS:
Before writing your answer, analyze step-by-step:

0. Card Types:
   - What TYPE is each card? (Creature, Artifact, Enchantment, Land, etc.)
   - If one is a CREATURE and one is NOT, this is CRITICAL information
   - Creatures have summoning sickness (can't tap immediately)
   - Creatures die to creature removal AND board wipes
   - Non-creature permanents are generally more resilient
   - ALWAYS mention if card types differ

1. Mana Economics:
   - What does each card COST to cast? (compare {1} vs {2} vs {3}, etc.)
   - What does each card PRODUCE or DO?
   - Net benefit = (what you get) - (what you pay)
   - IMPORTANT: If a card costs X mana and produces X mana, that's NET ZERO (mana conversion, not ramp)
   - Example: Paying {3} to untap and tapping for {3} = break even, not profit
   - A card that costs {2} and taps for {C} gives you net +1 mana per turn (after initial investment)

2. Key Mechanics:
   - Does it sacrifice itself? (one-time use only)
   - Does it tap repeatedly? (ongoing value each turn)
   - Does it produce colored mana or colorless mana? (colored is more flexible)
   - Does it draw cards, destroy permanents, or have other effects?
   - Does it enter tapped? (delayed value)
   - If it's a creature, remember it has SUMMONING SICKNESS

3. Common Errors to Avoid:
   - DON'T confuse casting cost with activation cost (they're different things)
   - DON'T claim a card "produces more mana" if it costs X to produce X (that's conversion)
   - DON'T ignore important text like "enters tapped", "draw a card", "destroy", "exile"
   - DON'T forget to mention if mana is colored vs colorless (this matters a lot)
   - DON'T get costs backwards ({2} is MORE expensive than {1})
   - DON'T ignore card types (Creature vs Artifact is HUGE)
   - DON'T forget summoning sickness for creatures

4. Context Matters - Consider:
   - Which is better for fast mana acceleration (ramp)?
   - Which is better for color fixing?
   - Which is better for card advantage?
   - Which is better for removal/control?
   - Which is more resilient to removal?
   - Are there specific deck types or strategies where one shines?

EXAMPLE OF GOOD COMPARISON:
Q: "Which is better, Sol Ring or Fellwar Stone?"
A: "Sol Ring is generally better. Sol Ring costs {1} and taps for {C}{C}, giving you net +1 colorless mana per turn. Fellwar Stone costs {2} and taps for one mana of any color an opponent could produce, also net +1 per turn but more expensive to cast. Sol Ring's lower cost makes it faster, though Fellwar Stone offers color fixing that Sol Ring lacks. For pure ramp, Sol Ring wins. For multicolor decks needing color fixing, Fellwar Stone has merit."

EXAMPLE OF BAD COMPARISON (DO NOT DO THIS):
Q: "Which is better, Hedron Crawler or Dragon's Hoard?"
A: "Hedron Crawler costs {2} and taps for {C}, suitable for any deck. Dragon's Hoard costs {3} and requires Dragons."
[ERROR: Doesn't mention Hedron Crawler is a CREATURE with summoning sickness and dies to board wipes]
"""

VALIDATION_CHECKLIST = """
CRITICAL CARD TYPE CHECKS:
Before anything else, verify the answer addresses card types:

1. Are the card types mentioned?
   - Creature vs Non-Creature is CRITICAL
   - Artifact vs Enchantment vs Land matters
   - If one is a creature and one isn't, this MUST be discussed

2. Type-specific mechanics mentioned?
   - Creatures: Summoning sickness (can't {T} or attack first turn), vulnerable to creature removal, can attack/block
   - Artifacts: No summoning sickness, only vulnerable to artifact removal
   - Enchantments: Only vulnerable to enchantment removal
   - Lands: Can't be countered, don't cost mana to play
   - Instants/Sorceries: One-time spells, not affected by board wipes

3. Vulnerability differences explained?
   - If comparing creature vs non-creature, answer MUST mention board wipes
   - If comparing different permanent types, answer MUST mention removal types
   - If comparing instants/sorceries, focus on EFFECTS not vulnerability

VERIFICATION CHECKLIST:
Check each of these carefully:

1. Casting costs correct?
   - Does the answer correctly state which card costs more to cast?
   - Are mana symbols and costs accurate?

2. Mechanics accurate?
   - Does it correctly describe what each card DOES?
   - Are activation costs vs casting costs distinguished properly?
   - Is net mana production calculated correctly?
   - If a card costs X and produces X, is it correctly identified as net zero (conversion, not ramp)?
   
3. CARD TYPES mentioned and explained?
   - If one card is a creature and one isn't, is this addressed?
   - Are type-specific vulnerabilities mentioned?
   - Is summoning sickness mentioned for creatures?
   - For instants/sorceries, are effects discussed (not board wipe vulnerability)?
   
4. Important details mentioned?
   - Card draw effects mentioned if present?
   - "Enters tapped" mentioned if relevant?
   - Sacrifice requirements mentioned if present?
   - Color restrictions mentioned (colored vs colorless mana)?
   - Destruction/removal effects mentioned if present?

5. No false claims?
   - No invented abilities or effects?
   - No confusion between "costs X, produces X" (net zero) vs actual ramp?
   - No claiming cheaper cards are more expensive?
   - No ignoring critical card text?

COMMON ERROR PATTERNS TO REJECT:
- Claiming "costs less to activate" when actually comparing casting costs
- Saying a card "produces more mana if you pay more" when it's X-for-X conversion
- Ignoring that a card draws cards, destroys things, or has other important effects
- Missing that colored mana ≠ colorless mana
- Confusing one-time effects with repeatable effects
- Backwards cost comparisons (saying {2} is cheaper than {1})
- IGNORING CARD TYPES (creature vs artifact is a HUGE difference)
- NOT MENTIONING summoning sickness for creatures
- MISSING vulnerability differences between card types
- Discussing board wipe vulnerability for INSTANTS/SORCERIES (they're spells, not permanents!)
"""

VALIDATION_SCORING_GUIDE = """
SCORING GUIDE:
- 9-10: Perfect, all mechanics correct, comprehensive, card types addressed
- 7-8: Good, minor omissions but no errors
- 5-6: Acceptable but missing important context
- 3-4: Significant errors or missing critical info (like ignoring card types)
- 1-2: Fundamentally wrong about card mechanics

CRITICAL: 
- If card types are ignored when comparing creature vs non-creature, max score is 4
- If there are ANY factual errors about card mechanics, max score is 4
- If discussing board wipes for instant/sorcery cards, max score is 4
- A score of 7+ is acceptable. Below 7 should be rejected.
"""