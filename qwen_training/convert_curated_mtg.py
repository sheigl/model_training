"""
Generate MTG training data from curated knowledge
===================================================

WHAT THIS SCRIPT DOES:
    Creates high-quality, hand-written training data about Magic: The Gathering.
    Unlike convert_mtg_data.py (which auto-generates Q&A from a card database),
    this script contains MANUALLY CURATED knowledge that captures the kind of
    strategic understanding you can't get from card text alone.

    Real-world analogy: convert_mtg_data.py is like a textbook of facts
    (definitions, dates, formulas). THIS script is like a study guide written
    by an expert tutor -- it covers combos, strategies, and deep understanding
    that goes beyond raw data.

WHY CURATED DATA MATTERS:
    Auto-generated data (from convert_mtg_data.py) teaches the model FACTS:
        "What does Lightning Bolt do?" -> "Deal 3 damage to any target."

    Curated data teaches the model UNDERSTANDING:
        "What's the Splinter Twin combo?" -> (detailed combo explanation)
        "What's the BREAD method for drafting?" -> (strategic framework)

    In ML, data quality matters more than quantity. 100 expert-written examples
    can teach more than 10,000 auto-generated ones. This is because curated
    data captures:
    - Multi-card interactions (combos)
    - Strategic frameworks (BREAD, Rule of 8)
    - Format-specific metagame knowledge
    - Nuanced gameplay decisions

    Real-world analogy: A medical student learns anatomy from textbooks (auto-
    generated data), but learns to diagnose patients from experienced doctors'
    case studies (curated data). Both are needed, but the case studies develop
    the deeper reasoning skills.

DATA CATEGORIES IN THIS SCRIPT:
    1. Combos: Multi-card winning combinations (Splinter Twin, Thassa's Oracle)
    2. Rules: How game mechanics work (the stack, priority, damage prevention)
    3. Format staples: Best cards in each format (Modern removal, Legacy counters)
    4. Draft strategy: Limited format techniques (BREAD, mana curves)
    5. Deck archetypes: Broad strategy types (tempo, midrange, toolbox)

Usage:
    python convert_curated_mtg.py --output curated_mtg.jsonl
"""

# =============================================================================
# IMPORTS
# =============================================================================

# json: For writing the output JSONL file. Each training example is serialized
# (converted) to a JSON string and written as one line.
import json

# argparse: For command-line arguments. See finetune_qwen.py for detailed explanation.
import argparse


# =============================================================================
# COMBO KNOWLEDGE
# =============================================================================
# Combos are multi-card interactions that win the game (usually on the spot).
# They're a core part of competitive MTG and require understanding how
# multiple cards interact -- something that card-level data can't capture.
#
# Real-world analogy: Individual puzzle pieces (cards) don't tell you what
# the finished picture (combo) looks like. You need someone to show you
# how the pieces fit together.
#
# Each Q&A pair is structured as {"user": question, "assistant": answer}.
# This is an intermediate format -- main() converts it to the final
# {"messages": [...]} format that the trainer expects.

def get_combo_questions():
    """
    Well-known MTG combos and how they work.

    These combos span multiple formats (Modern, Legacy, Commander) and
    represent the kind of "tribal knowledge" that experienced players share.
    Teaching the model about combos helps it understand card synergies
    and multi-step game plans.
    """
    return [
        {
            # SPLINTER TWIN COMBO (Modern, now banned in Modern but legal in other formats)
            # This is an "infinite creature" combo -- it creates unlimited attackers.
            "user": "What's the Splinter Twin combo?",
            "assistant": "Splinter Twin combo creates infinite creature tokens:\n1. Enchant Pestermite or Deceiver Exarch with Splinter Twin\n2. Tap the creature to create a hasty token copy\n3. The token's ETB trigger untaps the original\n4. Repeat infinitely\n5. Attack with infinite hasty tokens for lethal\n\nYou need the creature already in play before casting Twin, or have haste enabler. The combo wins the turn you assemble it."
        },
        {
            # THASSA'S ORACLE COMBO (Commander, Legacy, Vintage)
            # This is a "deterministic win" -- once you start it, you can't be stopped
            # (unless opponent has a specific counter for the Oracle trigger).
            "user": "How does the Thassa's Oracle combo work?",
            "assistant": "Thassa's Oracle wins with an empty library:\n1. Cast Demonic Consultation or Tainted Pact\n2. Name a card not in your deck to exile your entire library\n3. Cast Thassa's Oracle\n4. Oracle's ETB trigger checks your empty library and you win\n\nThis is a 2-card combo that wins instantly. Can be done at instant speed with Tainted Pact + flash for Oracle."
        },
        {
            # KIKI-JIKI COMBO (Modern, Commander)
            # Similar to Splinter Twin but uses a creature instead of an enchantment.
            "user": "What's the Kiki-Jiki combo?",
            "assistant": "Kiki-Jiki combos similarly to Splinter Twin:\n1. Use Kiki-Jiki to copy Pestermite, Deceiver Exarch, or Restoration Angel\n2. The copy untaps Kiki-Jiki\n3. Repeat for infinite hasty tokens\n\nVariations:\n- Kiki-Jiki + Zealous Conscripts\n- Kiki-Jiki + Combat Celebrant\n\nRequires Kiki-Jiki untapped and summoning sickness gone, or haste enabler."
        },
        {
            # HELIOD + WALKING BALLISTA (Modern, Pioneer)
            # An "infinite damage" combo that doesn't need the combat step.
            "user": "How does Heliod + Walking Ballista combo work?",
            "assistant": "Heliod, Sun-Crowned + Walking Ballista creates infinite damage:\n1. Have Heliod in play\n2. Cast Walking Ballista with X≥1\n3. Ballista deals 1 damage (remove counter)\n4. Heliod's ability triggers, put a +1/+1 counter on Ballista\n5. Repeat infinitely to kill all opponents\n\nRequires 4 mana (3 for Heliod + 1 for Ballista). Works at instant speed."
        },
        {
            # STORM COMBO (Legacy)
            # Storm is a keyword that copies a spell for each spell cast before it
            # this turn. The goal is to cast many cheap spells, then a finisher.
            "user": "What's the Storm combo in Legacy?",
            "assistant": "Storm combos generate high storm count then win:\n\nTypical Storm Turn:\n1. Ritual effects (Dark Ritual, Rite of Flame) for mana\n2. Cantrips (Ponder, Preordain, Brainstorm) to find pieces\n3. Lions Eye Diamond / Lotus Petal for more mana\n4. Past in Flames to flashback everything\n5. Tendrils of Agony for lethal (storm count 10+)\n\nVariations use Grapeshot, Empty the Warrens, or other storm cards."
        },
        {
            # DEVOTED DRUID COMBO (Modern)
            # An "infinite mana" combo that needs a separate "payoff" card to win.
            "user": "How does Vizier of Remedies combo with Devoted Druid?",
            "assistant": "Devoted Druid + Vizier of Remedies makes infinite green mana:\n1. Have both creatures in play\n2. Tap Druid for {G}\n3. Use Druid's ability to untap (put -1/-1 counter)\n4. Vizier prevents the counter\n5. Repeat infinitely for unlimited green mana\n\nAlternatives to Vizier: Melira, Sylvok Outcast or Luxior, Giada's Gift. Use mana with Walking Ballista or other outlet."
        },
        {
            # SCAPESHIFT COMBO (Modern)
            # A "lands-based" combo that uses the land-searching spell Scapeshift
            # to trigger Valakut, the Molten Pinnacle's damage ability many times.
            "user": "What's the Scapeshift combo?",
            "assistant": "Scapeshift wins by sacrificing all lands for Valakut triggers:\n1. Get to 7-8 lands\n2. Cast Scapeshift\n3. Sacrifice all lands\n4. Search for: Valakut + 6+ Mountains\n5. Valakut triggers 18+ times (each mountain sees 5+ other mountains)\n6. Deal 54+ damage to opponent\n\nModern version uses Dryad of the Ilysian Grove to make all lands Mountains. Can also get Field of the Dead for zombie tokens."
        },
    ]


# =============================================================================
# RULES KNOWLEDGE
# =============================================================================
# MTG has a complex rules system. Understanding the rules (not just card text)
# is essential for playing correctly. These questions cover commonly
# misunderstood rules and interactions.
#
# Real-world analogy: Card text tells you what each piece does (like reading
# individual traffic signs). Rules knowledge tells you how the whole system
# works (like understanding traffic laws). You need both to drive correctly.

def get_rules_questions():
    """
    MTG rules and mechanical interactions.

    These cover the game's core systems that players frequently ask about
    or misunderstand. Getting rules right is especially important for
    competitive play where incorrect plays can result in penalties.
    """
    return [
        {
            # THE STACK: The most important game mechanic to understand.
            # It determines the ORDER in which spells and abilities resolve.
            # Real-world analogy: Like a stack of plates -- you can only take
            # the top one off (LIFO: Last In, First Out).
            "user": "How does the stack work in Magic?",
            "assistant": "The stack is a zone where spells and abilities wait to resolve. It follows Last In, First Out (LIFO):\n\n1. When you cast a spell or activate an ability, it goes on the stack\n2. Players can respond by adding more items\n3. When all players pass priority, the top item resolves\n4. Players can respond again before the next item resolves\n\nExample: You cast Lightning Bolt. Opponent casts Counterspell. Counterspell resolves first (being on top), countering the Bolt."
        },
        {
            # DAMAGE PREVENTION: A commonly misunderstood mechanic.
            # Key insight: if damage is prevented, it NEVER HAPPENED, so
            # anything that triggers off "dealing damage" doesn't trigger.
            "user": "What happens when damage is prevented?",
            "assistant": "When damage is prevented:\n- The damage never happens\n- Lifelink doesn't trigger (no damage dealt = no life gained)\n- Deathtouch doesn't apply\n- Combat damage triggers don't happen\n\nExample: If you prevent all damage to a 3/3, it takes 0 damage and survives. If you prevent 2 damage to a 3/3 taking 5 damage, it takes 3 damage and dies."
        },
        {
            # PRIORITY: Determines who gets to act and when.
            # Without understanding priority, you can't play instants or
            # abilities at the right time.
            "user": "How does priority work?",
            "assistant": "Priority determines who can take actions:\n\n1. Active player (whose turn it is) gets priority first\n2. They can cast spells, activate abilities, or pass\n3. Priority passes clockwise\n4. When all players pass in succession, top stack item resolves\n5. Active player gets priority again\n\nYou need priority to:\n- Cast spells\n- Activate abilities\n- Play lands (main phase only)\n\nYou don't need priority for:\n- Special actions (turning face-down creatures face-up)\n- Mana abilities"
        },
        {
            # COUNTERING ABILITIES: A very common misconception.
            # Players often try to "Counterspell" abilities, which doesn't work.
            # Counterspells only work on SPELLS (cards being cast from hand).
            "user": "Can you counterspell a creature ability?",
            "assistant": "It depends on the ability type:\n\nYES - Can counter TRIGGERED abilities:\n- Use Stifle, Disallow, Tale's End\n- Example: Counter Thassa's Oracle ETB trigger\n\nNO - Cannot counter ACTIVATED abilities with normal counterspells:\n- Need Stifle or similar\n- Example: Can't Counterspell an equipment's equip ability\n\nNO - Cannot counter STATIC abilities:\n- These don't use the stack\n- Example: Can't counter Hexproof\n\nMost counterspells only work on spells (cards on the stack), not abilities."
        },
        {
            # DESTROY vs SACRIFICE: Different mechanics with different rules.
            # Key insight: sacrifice BYPASSES indestructible and hexproof,
            # making it one of the strongest removal types.
            "user": "What's the difference between destroy and sacrifice?",
            "assistant": "Destroy vs Sacrifice:\n\nDESTROY:\n- One player destroys another's permanent\n- Can be prevented by indestructible or regeneration\n- Example: \"Destroy target creature\"\n- Hexproof/shroud prevent targeting, but not mass destruction\n\nSACRIFICE:\n- Controller chooses and sacrifices their own permanent\n- CANNOT be prevented (not destruction)\n- Gets around indestructible and hexproof\n- Example: \"Each player sacrifices a creature\"\n\nSacrifice is stronger because it bypasses most protections."
        },
        {
            # DOUBLE STRIKE: A combat mechanic that's more complex than it looks.
            # The key insight is that first strike damage and regular damage
            # happen in SEPARATE STEPS with state-based actions checked between.
            "user": "How does double strike work?",
            "assistant": "Double strike deals combat damage twice:\n\n1. First strike damage step:\n   - Double strike and first strike creatures deal damage\n   - Regular creatures don't deal damage yet\n   - State-based actions are checked (creatures with lethal damage die)\n\n2. Regular combat damage step:\n   - Double strike and regular creatures deal damage\n   - First strike-only creatures don't deal damage again\n\nResult: Double strike creature deals damage twice. If it kills its blocker in first strike, the second hit goes through to player. Triggers like lifelink and card draw happen twice."
        },
        {
            # PLAYING LANDS: A "special action" that doesn't use the stack.
            # This surprises many new players who think everything goes on the stack.
            "user": "Can I respond to someone playing a land?",
            "assistant": "NO - You cannot respond to playing a land:\n\nPlaying a land:\n- Is a special action, not a spell\n- Doesn't use the stack\n- Can't be countered or responded to\n- Limited to once per turn\n- Only during main phase when stack is empty\n\nHowever, you CAN respond to:\n- Triggered abilities when land enters (fetchland crack, Valakut trigger)\n- Abilities lands have after entering\n\nExample: Can't stop someone playing a fetchland, but CAN respond when they crack it."
        },
        {
            # THE LEGEND RULE: Governs legendary permanents.
            # This is a state-based action (happens automatically, no stack).
            "user": "What's the legend rule?",
            "assistant": "Legend Rule: Only one legendary permanent with the same name per player.\n\nWhat happens:\n1. If you control two+ legends with same name, choose one to keep\n2. Put the others into graveyard\n3. This is a state-based action (doesn't use stack)\n\nKey points:\n- You choose which to keep\n- Different players can each have a copy\n- Applies to all legendary permanents (creatures, planeswalkers, lands, etc.)\n- Clone effects can copy legends, triggering the rule\n\nExample: If you clone opponent's legendary, you both keep yours."
        },
    ]


# =============================================================================
# FORMAT STAPLES
# =============================================================================
# "Staples" are cards that are so powerful they appear in most decks of
# their color within a given format. Knowing the staples is foundational
# MTG knowledge.
#
# Real-world analogy: Like knowing the "must-have" ingredients for a cuisine.
# Every Italian kitchen needs olive oil, garlic, and tomatoes. Every Modern
# red deck needs Lightning Bolt.

def get_format_staples():
    """
    Format staple cards -- the most-played and most-important cards in each format.

    These questions teach the model about the competitive landscape and what
    cards define each format's metagame.
    """
    return [
        {
            # Modern is Magic's most popular competitive format (sets from 2003+).
            # This covers the best removal spells (cards that destroy/exile threats).
            "user": "What are the best removal spells in Modern?",
            "assistant": "Top Modern removal by color:\n\nWhite:\n- Path to Exile (1 mana, exile creature)\n- Prismatic Ending (flexible permanent removal)\n\nBlack:\n- Fatal Push (1 mana, kills 2 or 4 CMC)\n- Thoughtseize (hand disruption)\n- Terminate (unconditional creature kill)\n\nRed:\n- Lightning Bolt (3 damage anywhere)\n- Unholy Heat (with delirium, kills anything)\n\nBlue:\n- Counterspell (2 mana hard counter)\n- Archmage's Charm (versatile)\n\nGreen:\n- Force of Vigor (free artifact/enchantment removal)\n\nColorless:\n- Dismember, Ratchet Bomb"
        },
        {
            # Legacy is the most powerful "fair" format (almost all cards legal).
            # Free counterspells define Legacy because combo decks can win on turn 1-2.
            "user": "What are the best counterspells in Legacy?",
            "assistant": "Top Legacy counterspells:\n\n**Free counters:**\n- Force of Will (pitch blue card)\n- Force of Negation (pitch blue, only opponent's turn)\n- Daze (return island)\n\n**Mana-efficient:**\n- Counterspell (2 mana, hard counter)\n- Flusterstorm (storm counter, 1 mana)\n- Spell Pierce (1 mana, tax)\n- Pyroblast/Red Elemental Blast (1 mana vs blue)\n\n**Versatile:**\n- Force of Will (emergency answer)\n- Counterspell (efficient hard counter)\n- Veil of Summer (protection + draw)\n\nLegacy favors free interaction because of fast combo decks."
        },
        {
            # Commander (EDH) is the most popular casual format.
            # The mana base (lands) is the foundation of every deck.
            "user": "What lands should every Commander deck run?",
            "assistant": "Essential Commander lands by category:\n\n**Universal:**\n- Command Tower\n- Sol Ring (not a land but always include)\n- Reliquary Tower (if you draw lots of cards)\n\n**Color Fixing:**\n- Check lands (Sunpetal Grove, etc.)\n- Pain lands (Adarkar Wastes, etc.)\n- Filter lands (Mystic Gate, etc.)\n- Triomes (3-color lands with basic types)\n\n**Utility:**\n- Bojuka Bog (graveyard hate)\n- Strip Mine (land destruction)\n- Ghost Quarter (budget strip mine)\n- Rogue's Passage (make creature unblockable)\n\n**Budget:**\n- Evolving Wilds / Terramorphic Expanse\n- Exotic Orchard\n- Myriad Landscape\n- Path of Ancestry (tribal)\n\nRun 36-38 lands total."
        },
    ]


# =============================================================================
# DRAFT STRATEGY
# =============================================================================
# "Limited" (draft and sealed) is a completely different skill from constructed.
# In Limited, you build a deck from a random pool of cards, so you need
# frameworks for evaluating cards on the fly.
#
# Real-world analogy: Constructed is like cooking with a fully stocked kitchen
# (you choose exactly what to buy). Limited is like a cooking competition
# where you're given random ingredients and have to make the best dish.

def get_draft_strategy():
    """
    Limited/draft strategy questions.

    These teach foundational draft concepts that apply to any set.
    Draft is a format where you open booster packs and pick cards one at a time,
    building a deck from your picks.
    """
    return [
        {
            # BREAD: The most widely-taught draft framework.
            # It gives you a priority order for picking cards.
            "user": "What's the BREAD method for drafting?",
            "assistant": "BREAD is a draft pick priority system:\n\n**B - Bombs:**\nGame-winning cards (planeswalkers, big evasive creatures, removal on a stick)\nPick: 1st-2nd\n\n**R - Removal:**\nKill spells to answer opponent's threats\nPick: 2nd-3rd\n\n**E - Evasion:**\nCreatures that are hard to block (flying, menace, unblockable)\nPick: 3rd-4th\n\n**A - Aggro:**\nEfficient creatures that fill your curve (2-3 drops)\nPick: 4th\n\n**D - Duds:**\nCards you don't want\nPick: Never\n\nModern variation: CABS (Cards that Affect Board State) focuses on board impact over curve."
        },
        {
            # DECK COMPOSITION: The numbers behind a well-built Limited deck.
            # 40 cards total, split roughly into 17 lands, 15 creatures, 8 spells.
            "user": "How many creatures should I draft?",
            "assistant": "Typical draft deck composition:\n\n**Creatures: 14-17** (15-16 ideal)\n- Early drops (2-3 CMC): 6-8 creatures\n- Mid game (4-5 CMC): 5-7 creatures\n- Late game (6+ CMC): 2-3 creatures\n\n**Non-creatures: 6-9**\n- Removal: 3-5 spells\n- Combat tricks: 1-2\n- Card draw: 1-2\n\n**Lands: 17**\n(Sometimes 16 for aggro, 18 for control)\n\nAdjust based on archetype:\n- Aggro: 16-17 creatures, lower curve\n- Control: 13-15 creatures, more removal\n- Midrange: 15-16 creatures, balanced\n\nPrioritize good cards over hitting exact numbers."
        },
        {
            # MANA CURVE: The distribution of cards by mana cost.
            # A good curve ensures you have something to play every turn.
            # Real-world analogy: Like a balanced diet -- you need variety
            # across all cost ranges, not just expensive power cards.
            "user": "What's a good mana curve for Limited?",
            "assistant": "Ideal Limited mana curve:\n\n**1 CMC: 0-2 cards**\n- Rarely good in Limited\n- Exception: Aggressive commons\n\n**2 CMC: 4-6 cards**\n- Critical for tempo\n- Play these on turn 2-3\n\n**3 CMC: 5-7 cards**\n- Your bread and butter\n- Most impactful commons/uncommons\n\n**4 CMC: 4-5 cards**\n- Strong creatures/removal\n\n**5 CMC: 2-4 cards**\n- Powerful finishers\n\n**6+ CMC: 1-3 cards**\n- Bombs only at this cost\n\nAverage CMC: ~3.5\n\nAggro decks curve lower (average 2.5-3), control curves higher (4-4.5)."
        },
    ]


# =============================================================================
# DECK ARCHETYPES
# =============================================================================
# Archetypes are broad strategic categories that most decks fall into.
# Understanding archetypes helps players identify what strategy a deck is
# trying to execute and how to counter it.
#
# Real-world analogy: Like weight classes in boxing. Knowing your opponent
# is a "heavyweight" (control deck) vs a "lightweight" (aggro deck) tells
# you how to fight them before you even see their specific cards.

def get_archetype_questions():
    """
    Deck archetype questions -- the broad strategic categories in MTG.

    The classic "metagame clock" describes how archetypes beat each other:
        Aggro beats Combo (kills before combo assembles)
        Combo beats Control (goes over the top)
        Control beats Aggro (stabilizes and grinds)
        Midrange sits in the middle (flexible, adapts to matchup)
    """
    return [
        {
            # TEMPO: The hardest archetype to understand.
            # It's not about card advantage -- it's about MANA advantage.
            # You deploy a cheap threat then protect it while disrupting your opponent.
            "user": "What's a tempo deck in Magic?",
            "assistant": "Tempo decks aim to get ahead early and stay ahead:\n\n**Strategy:**\n1. Deploy cheap, efficient threats (Delver, Ragavan)\n2. Protect them with cheap interaction (Spell Pierce, Daze)\n3. Disrupt opponent's gameplan\n4. Win before they stabilize\n\n**Key Elements:**\n- Efficient threats (1-2 mana)\n- Cheap interaction (0-2 mana counters/removal)\n- Card selection (Brainstorm, Ponder)\n- Tempo plays (bounce spells like Vapor Snag)\n\n**Examples:**\n- UR Delver (Legacy)\n- Mono-Blue Tempo (Standard)\n- Izzet Phoenix (Modern)\n\n**Weakness:**\nRuns out of steam if game goes long. Needs to close quickly."
        },
        {
            # AGGRO vs MIDRANGE: The most commonly confused archetypes.
            # The key difference is speed and how they use resources.
            "user": "What's the difference between aggro and midrange?",
            "assistant": "Aggro vs Midrange:\n\n**AGGRO:**\n- Strategy: Win fast (turn 4-6)\n- Creatures: Small, efficient (1-3 CMC)\n- Interaction: Minimal, focused on damage\n- Plan: Play threats, attack, finish with reach\n- Example: Burn, White Weenie, Mono-Red\n\n**MIDRANGE:**\n- Strategy: Flexible, wins turn 6-10\n- Creatures: Larger, value-generating (2-5 CMC)\n- Interaction: Efficient removal + some counters\n- Plan: Trade resources, stabilize, win with quality\n- Example: Jund, UWx Control, Abzan\n\n**Key Difference:**\nAggro wants to end game before opponent stabilizes. Midrange wants to trade efficiently then win with superior threats.\n\nMidrange beats aggro by stabilizing. Control beats midrange by going over the top. Aggro beats control by going under."
        },
        {
            # TOOLBOX: A strategy based on having the right answer for any situation.
            # The key mechanic is "tutoring" -- searching your deck for specific cards.
            # Real-world analogy: Like a Swiss army knife vs a regular knife.
            # The toolbox is less powerful at any single thing but has an answer
            # for every situation.
            "user": "What's a toolbox deck?",
            "assistant": "Toolbox decks have access to many situational answers:\n\n**How it works:**\n1. Run tutors (Chord of Calling, Collected Company, Birthing Pod)\n2. Include silver bullets (situational answers)\n3. Search for the perfect answer to current threat\n\n**Examples:**\n- Yisan, the Wanderer Bard (Commander): Tutor creatures in sequence\n- Kiki-Chord (Modern): Chord for combo or hate pieces\n- Birthing Pod (Historic): Chain creatures into answers\n\n**Common Toolbox Cards:**\n- Graveyard hate: Scavenging Ooze\n- Artifact/enchantment: Reclamation Sage\n- Big creatures: Archon of Emeria\n- Combo pieces: Kiki-Jiki\n\n**Advantage:** Always have the right answer\n**Disadvantage:** Needs tutors to function, weaker topdecks"
        },
    ]


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    """
    Main entry point: collect all curated Q&A data, convert to training format, save.

    The flow is simple since all data is hardcoded in this script:
    1. Gather all Q&A pairs from each category function
    2. Wrap each in the {"messages": [...]} format
    3. Write to JSONL file

    This is the simplest of the three data scripts because there's no external
    data source to load or API to call -- everything is defined above.
    """

    # --- Parse command-line arguments ---
    parser = argparse.ArgumentParser(
        description="Generate curated MTG training data"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="curated_mtg.jsonl",
        # Output path for the training data JSONL file.
        help="Output JSONL file"
    )

    args = parser.parse_args()

    print("\n" + "="*70)
    print("GENERATING CURATED MTG TRAINING DATA")
    print("="*70 + "\n")

    # --- Collect all Q&A pairs ---
    # Each function returns a list of {"user": ..., "assistant": ...} dicts.
    # We extend() (not append()) to add each list's items individually,
    # rather than nesting lists inside lists.
    #
    # extend() vs append():
    #   list.append([1, 2])  -> [existing_items, [1, 2]]  (adds the list as one item)
    #   list.extend([1, 2])  -> [existing_items, 1, 2]    (adds each item individually)
    all_questions = []

    print("Adding combo questions...")
    all_questions.extend(get_combo_questions())

    print("Adding rules questions...")
    all_questions.extend(get_rules_questions())

    print("Adding format staples...")
    all_questions.extend(get_format_staples())

    print("Adding draft strategy...")
    all_questions.extend(get_draft_strategy())

    print("Adding archetype questions...")
    all_questions.extend(get_archetype_questions())

    # --- Convert to training format ---
    # Transform from our simple internal format to the format the SFTTrainer expects.
    # Internal: {"user": "question", "assistant": "answer"}
    # Training: {"messages": [{"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"}]}
    #
    # The "messages" format is the standard for chat/instruction fine-tuning.
    # It mirrors how chat APIs work (user sends a message, assistant responds).
    training_data = []
    for q in all_questions:
        training_data.append({
            "messages": [
                {"role": "user", "content": q["user"]},
                {"role": "assistant", "content": q["assistant"]}
            ]
        })

    # --- Save to JSONL ---
    # Write one JSON object per line. This format can be directly fed to
    # finetune_qwen.py using: --dataset file --data-file curated_mtg.jsonl
    print(f"\nSaving to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item) + '\n')

    # --- Print summary ---
    print("\n" + "="*70)
    print("DONE!")
    print("="*70)
    print(f"Generated {len(training_data)} high-quality training examples")
    print(f"Saved to: {args.output}")
    print("\nCategories included:")
    print("  - Combo knowledge")
    print("  - Rules and interactions")
    print("  - Format staples")
    print("  - Draft strategy")
    print("  - Deck archetypes")
    print("\nYou can now combine with other data and train!")
    print("="*70)


# Only run main() when executed directly (not when imported).
# See convert_mtg_data.py for detailed explanation of this pattern.
if __name__ == "__main__":
    main()
