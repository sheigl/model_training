"""
Generate MTG training data from curated knowledge

This creates training data for:
- Common combos
- Rules interactions
- Format staples
- Deck archetypes
- Sideboard guides
- Draft strategy

This is manually curated high-quality data.

Usage:
    python convert_curated_mtg.py --output curated_mtg.jsonl
"""

import json
import argparse

def get_combo_questions():
    """Well-known MTG combos"""
    return [
        {
            "user": "What's the Splinter Twin combo?",
            "assistant": "Splinter Twin combo creates infinite creature tokens:\n1. Enchant Pestermite or Deceiver Exarch with Splinter Twin\n2. Tap the creature to create a hasty token copy\n3. The token's ETB trigger untaps the original\n4. Repeat infinitely\n5. Attack with infinite hasty tokens for lethal\n\nYou need the creature already in play before casting Twin, or have haste enabler. The combo wins the turn you assemble it."
        },
        {
            "user": "How does the Thassa's Oracle combo work?",
            "assistant": "Thassa's Oracle wins with an empty library:\n1. Cast Demonic Consultation or Tainted Pact\n2. Name a card not in your deck to exile your entire library\n3. Cast Thassa's Oracle\n4. Oracle's ETB trigger checks your empty library and you win\n\nThis is a 2-card combo that wins instantly. Can be done at instant speed with Tainted Pact + flash for Oracle."
        },
        {
            "user": "What's the Kiki-Jiki combo?",
            "assistant": "Kiki-Jiki combos similarly to Splinter Twin:\n1. Use Kiki-Jiki to copy Pestermite, Deceiver Exarch, or Restoration Angel\n2. The copy untaps Kiki-Jiki\n3. Repeat for infinite hasty tokens\n\nVariations:\n- Kiki-Jiki + Zealous Conscripts\n- Kiki-Jiki + Combat Celebrant\n\nRequires Kiki-Jiki untapped and summoning sickness gone, or haste enabler."
        },
        {
            "user": "How does Heliod + Walking Ballista combo work?",
            "assistant": "Heliod, Sun-Crowned + Walking Ballista creates infinite damage:\n1. Have Heliod in play\n2. Cast Walking Ballista with X≥1\n3. Ballista deals 1 damage (remove counter)\n4. Heliod's ability triggers, put a +1/+1 counter on Ballista\n5. Repeat infinitely to kill all opponents\n\nRequires 4 mana (3 for Heliod + 1 for Ballista). Works at instant speed."
        },
        {
            "user": "What's the Storm combo in Legacy?",
            "assistant": "Storm combos generate high storm count then win:\n\nTypical Storm Turn:\n1. Ritual effects (Dark Ritual, Rite of Flame) for mana\n2. Cantrips (Ponder, Preordain, Brainstorm) to find pieces\n3. Lions Eye Diamond / Lotus Petal for more mana\n4. Past in Flames to flashback everything\n5. Tendrils of Agony for lethal (storm count 10+)\n\nVariations use Grapeshot, Empty the Warrens, or other storm cards."
        },
        {
            "user": "How does Vizier of Remedies combo with Devoted Druid?",
            "assistant": "Devoted Druid + Vizier of Remedies makes infinite green mana:\n1. Have both creatures in play\n2. Tap Druid for {G}\n3. Use Druid's ability to untap (put -1/-1 counter)\n4. Vizier prevents the counter\n5. Repeat infinitely for unlimited green mana\n\nAlternatives to Vizier: Melira, Sylvok Outcast or Luxior, Giada's Gift. Use mana with Walking Ballista or other outlet."
        },
        {
            "user": "What's the Scapeshift combo?",
            "assistant": "Scapeshift wins by sacrificing all lands for Valakut triggers:\n1. Get to 7-8 lands\n2. Cast Scapeshift\n3. Sacrifice all lands\n4. Search for: Valakut + 6+ Mountains\n5. Valakut triggers 18+ times (each mountain sees 5+ other mountains)\n6. Deal 54+ damage to opponent\n\nModern version uses Dryad of the Ilysian Grove to make all lands Mountains. Can also get Field of the Dead for zombie tokens."
        },
    ]

def get_rules_questions():
    """MTG rules and interactions"""
    return [
        {
            "user": "How does the stack work in Magic?",
            "assistant": "The stack is a zone where spells and abilities wait to resolve. It follows Last In, First Out (LIFO):\n\n1. When you cast a spell or activate an ability, it goes on the stack\n2. Players can respond by adding more items\n3. When all players pass priority, the top item resolves\n4. Players can respond again before the next item resolves\n\nExample: You cast Lightning Bolt. Opponent casts Counterspell. Counterspell resolves first (being on top), countering the Bolt."
        },
        {
            "user": "What happens when damage is prevented?",
            "assistant": "When damage is prevented:\n- The damage never happens\n- Lifelink doesn't trigger (no damage dealt = no life gained)\n- Deathtouch doesn't apply\n- Combat damage triggers don't happen\n\nExample: If you prevent all damage to a 3/3, it takes 0 damage and survives. If you prevent 2 damage to a 3/3 taking 5 damage, it takes 3 damage and dies."
        },
        {
            "user": "How does priority work?",
            "assistant": "Priority determines who can take actions:\n\n1. Active player (whose turn it is) gets priority first\n2. They can cast spells, activate abilities, or pass\n3. Priority passes clockwise\n4. When all players pass in succession, top stack item resolves\n5. Active player gets priority again\n\nYou need priority to:\n- Cast spells\n- Activate abilities\n- Play lands (main phase only)\n\nYou don't need priority for:\n- Special actions (turning face-down creatures face-up)\n- Mana abilities"
        },
        {
            "user": "Can you counterspell a creature ability?",
            "assistant": "It depends on the ability type:\n\nYES - Can counter TRIGGERED abilities:\n- Use Stifle, Disallow, Tale's End\n- Example: Counter Thassa's Oracle ETB trigger\n\nNO - Cannot counter ACTIVATED abilities with normal counterspells:\n- Need Stifle or similar\n- Example: Can't Counterspell an equipment's equip ability\n\nNO - Cannot counter STATIC abilities:\n- These don't use the stack\n- Example: Can't counter Hexproof\n\nMost counterspells only work on spells (cards on the stack), not abilities."
        },
        {
            "user": "What's the difference between destroy and sacrifice?",
            "assistant": "Destroy vs Sacrifice:\n\nDESTROY:\n- One player destroys another's permanent\n- Can be prevented by indestructible or regeneration\n- Example: \"Destroy target creature\"\n- Hexproof/shroud prevent targeting, but not mass destruction\n\nSACRIFICE:\n- Controller chooses and sacrifices their own permanent\n- CANNOT be prevented (not destruction)\n- Gets around indestructible and hexproof\n- Example: \"Each player sacrifices a creature\"\n\nSacrifice is stronger because it bypasses most protections."
        },
        {
            "user": "How does double strike work?",
            "assistant": "Double strike deals combat damage twice:\n\n1. First strike damage step:\n   - Double strike and first strike creatures deal damage\n   - Regular creatures don't deal damage yet\n   - State-based actions are checked (creatures with lethal damage die)\n\n2. Regular combat damage step:\n   - Double strike and regular creatures deal damage\n   - First strike-only creatures don't deal damage again\n\nResult: Double strike creature deals damage twice. If it kills its blocker in first strike, the second hit goes through to player. Triggers like lifelink and card draw happen twice."
        },
        {
            "user": "Can I respond to someone playing a land?",
            "assistant": "NO - You cannot respond to playing a land:\n\nPlaying a land:\n- Is a special action, not a spell\n- Doesn't use the stack\n- Can't be countered or responded to\n- Limited to once per turn\n- Only during main phase when stack is empty\n\nHowever, you CAN respond to:\n- Triggered abilities when land enters (fetchland crack, Valakut trigger)\n- Abilities lands have after entering\n\nExample: Can't stop someone playing a fetchland, but CAN respond when they crack it."
        },
        {
            "user": "What's the legend rule?",
            "assistant": "Legend Rule: Only one legendary permanent with the same name per player.\n\nWhat happens:\n1. If you control two+ legends with same name, choose one to keep\n2. Put the others into graveyard\n3. This is a state-based action (doesn't use stack)\n\nKey points:\n- You choose which to keep\n- Different players can each have a copy\n- Applies to all legendary permanents (creatures, planeswalkers, lands, etc.)\n- Clone effects can copy legends, triggering the rule\n\nExample: If you clone opponent's legendary, you both keep yours."
        },
    ]

def get_format_staples():
    """Format staple cards and explanations"""
    return [
        {
            "user": "What are the best removal spells in Modern?",
            "assistant": "Top Modern removal by color:\n\nWhite:\n- Path to Exile (1 mana, exile creature)\n- Prismatic Ending (flexible permanent removal)\n\nBlack:\n- Fatal Push (1 mana, kills 2 or 4 CMC)\n- Thoughtseize (hand disruption)\n- Terminate (unconditional creature kill)\n\nRed:\n- Lightning Bolt (3 damage anywhere)\n- Unholy Heat (with delirium, kills anything)\n\nBlue:\n- Counterspell (2 mana hard counter)\n- Archmage's Charm (versatile)\n\nGreen:\n- Force of Vigor (free artifact/enchantment removal)\n\nColorless:\n- Dismember, Ratchet Bomb"
        },
        {
            "user": "What are the best counterspells in Legacy?",
            "assistant": "Top Legacy counterspells:\n\n**Free counters:**\n- Force of Will (pitch blue card)\n- Force of Negation (pitch blue, only opponent's turn)\n- Daze (return island)\n\n**Mana-efficient:**\n- Counterspell (2 mana, hard counter)\n- Flusterstorm (storm counter, 1 mana)\n- Spell Pierce (1 mana, tax)\n- Pyroblast/Red Elemental Blast (1 mana vs blue)\n\n**Versatile:**\n- Force of Will (emergency answer)\n- Counterspell (efficient hard counter)\n- Veil of Summer (protection + draw)\n\nLegacy favors free interaction because of fast combo decks."
        },
        {
            "user": "What lands should every Commander deck run?",
            "assistant": "Essential Commander lands by category:\n\n**Universal:**\n- Command Tower\n- Sol Ring (not a land but always include)\n- Reliquary Tower (if you draw lots of cards)\n\n**Color Fixing:**\n- Check lands (Sunpetal Grove, etc.)\n- Pain lands (Adarkar Wastes, etc.)\n- Filter lands (Mystic Gate, etc.)\n- Triomes (3-color lands with basic types)\n\n**Utility:**\n- Bojuka Bog (graveyard hate)\n- Strip Mine (land destruction)\n- Ghost Quarter (budget strip mine)\n- Rogue's Passage (make creature unblockable)\n\n**Budget:**\n- Evolving Wilds / Terramorphic Expanse\n- Exotic Orchard\n- Myriad Landscape\n- Path of Ancestry (tribal)\n\nRun 36-38 lands total."
        },
    ]

def get_draft_strategy():
    """Limited/draft strategy questions"""
    return [
        {
            "user": "What's the BREAD method for drafting?",
            "assistant": "BREAD is a draft pick priority system:\n\n**B - Bombs:**\nGame-winning cards (planeswalkers, big evasive creatures, removal on a stick)\nPick: 1st-2nd\n\n**R - Removal:**\nKill spells to answer opponent's threats\nPick: 2nd-3rd\n\n**E - Evasion:**\nCreatures that are hard to block (flying, menace, unblockable)\nPick: 3rd-4th\n\n**A - Aggro:**\nEfficient creatures that fill your curve (2-3 drops)\nPick: 4th\n\n**D - Duds:**\nCards you don't want\nPick: Never\n\nModern variation: CABS (Cards that Affect Board State) focuses on board impact over curve."
        },
        {
            "user": "How many creatures should I draft?",
            "assistant": "Typical draft deck composition:\n\n**Creatures: 14-17** (15-16 ideal)\n- Early drops (2-3 CMC): 6-8 creatures\n- Mid game (4-5 CMC): 5-7 creatures\n- Late game (6+ CMC): 2-3 creatures\n\n**Non-creatures: 6-9**\n- Removal: 3-5 spells\n- Combat tricks: 1-2\n- Card draw: 1-2\n\n**Lands: 17**\n(Sometimes 16 for aggro, 18 for control)\n\nAdjust based on archetype:\n- Aggro: 16-17 creatures, lower curve\n- Control: 13-15 creatures, more removal\n- Midrange: 15-16 creatures, balanced\n\nPrioritize good cards over hitting exact numbers."
        },
        {
            "user": "What's a good mana curve for Limited?",
            "assistant": "Ideal Limited mana curve:\n\n**1 CMC: 0-2 cards**\n- Rarely good in Limited\n- Exception: Aggressive commons\n\n**2 CMC: 4-6 cards**\n- Critical for tempo\n- Play these on turn 2-3\n\n**3 CMC: 5-7 cards**\n- Your bread and butter\n- Most impactful commons/uncommons\n\n**4 CMC: 4-5 cards**\n- Strong creatures/removal\n\n**5 CMC: 2-4 cards**\n- Powerful finishers\n\n**6+ CMC: 1-3 cards**\n- Bombs only at this cost\n\nAverage CMC: ~3.5\n\nAggro decks curve lower (average 2.5-3), control curves higher (4-4.5)."
        },
    ]

def get_archetype_questions():
    """Deck archetype questions"""
    return [
        {
            "user": "What's a tempo deck in Magic?",
            "assistant": "Tempo decks aim to get ahead early and stay ahead:\n\n**Strategy:**\n1. Deploy cheap, efficient threats (Delver, Ragavan)\n2. Protect them with cheap interaction (Spell Pierce, Daze)\n3. Disrupt opponent's gameplan\n4. Win before they stabilize\n\n**Key Elements:**\n- Efficient threats (1-2 mana)\n- Cheap interaction (0-2 mana counters/removal)\n- Card selection (Brainstorm, Ponder)\n- Tempo plays (bounce spells like Vapor Snag)\n\n**Examples:**\n- UR Delver (Legacy)\n- Mono-Blue Tempo (Standard)\n- Izzet Phoenix (Modern)\n\n**Weakness:**\nRuns out of steam if game goes long. Needs to close quickly."
        },
        {
            "user": "What's the difference between aggro and midrange?",
            "assistant": "Aggro vs Midrange:\n\n**AGGRO:**\n- Strategy: Win fast (turn 4-6)\n- Creatures: Small, efficient (1-3 CMC)\n- Interaction: Minimal, focused on damage\n- Plan: Play threats, attack, finish with reach\n- Example: Burn, White Weenie, Mono-Red\n\n**MIDRANGE:**\n- Strategy: Flexible, wins turn 6-10\n- Creatures: Larger, value-generating (2-5 CMC)\n- Interaction: Efficient removal + some counters\n- Plan: Trade resources, stabilize, win with quality\n- Example: Jund, UWx Control, Abzan\n\n**Key Difference:**\nAggro wants to end game before opponent stabilizes. Midrange wants to trade efficiently then win with superior threats.\n\nMidrange beats aggro by stabilizing. Control beats midrange by going over the top. Aggro beats control by going under."
        },
        {
            "user": "What's a toolbox deck?",
            "assistant": "Toolbox decks have access to many situational answers:\n\n**How it works:**\n1. Run tutors (Chord of Calling, Collected Company, Birthing Pod)\n2. Include silver bullets (situational answers)\n3. Search for the perfect answer to current threat\n\n**Examples:**\n- Yisan, the Wanderer Bard (Commander): Tutor creatures in sequence\n- Kiki-Chord (Modern): Chord for combo or hate pieces\n- Birthing Pod (Historic): Chain creatures into answers\n\n**Common Toolbox Cards:**\n- Graveyard hate: Scavenging Ooze\n- Artifact/enchantment: Reclamation Sage\n- Big creatures: Archon of Emeria\n- Combo pieces: Kiki-Jiki\n\n**Advantage:** Always have the right answer\n**Disadvantage:** Needs tutors to function, weaker topdecks"
        },
    ]

def main():
    parser = argparse.ArgumentParser(
        description="Generate curated MTG training data"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="curated_mtg.jsonl",
        help="Output JSONL file"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("GENERATING CURATED MTG TRAINING DATA")
    print("="*70 + "\n")
    
    # Collect all questions
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
    
    # Convert to training format
    training_data = []
    for q in all_questions:
        training_data.append({
            "messages": [
                {"role": "user", "content": q["user"]},
                {"role": "assistant", "content": q["assistant"]}
            ]
        })
    
    # Save
    print(f"\nSaving to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item) + '\n')
    
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

if __name__ == "__main__":
    main()
