"""
Convert EDHREC commander data to training format
==================================================

WHAT THIS SCRIPT DOES:
    Fetches data from EDHREC (edhrec.com) -- the most popular resource for
    Commander/EDH deck building -- and converts it into training data.

    EDHREC aggregates deck data from thousands of players to determine which
    cards are most commonly played with each commander. This script uses their
    public JSON API to generate training examples about commander deck building.

    Real-world analogy: EDHREC is like Yelp for MTG cards. Instead of
    restaurant reviews, it has data on which cards players actually use in
    their decks. This script reads those "reviews" and creates study material.

HOW IT DIFFERS FROM THE OTHER SCRIPTS:
    - convert_mtg_data.py: Generates Q&A from raw card DATABASE (offline data)
    - convert_curated_mtg.py: Uses hand-written expert knowledge (offline data)
    - convert_edhrec_data.py: Fetches LIVE data from the internet (online data)

    This script requires an internet connection and may be slower due to
    API rate limiting (we wait between requests to be polite to EDHREC's servers).

    Real-world analogy: The first two scripts are like studying from books you
    already own. This script is like going to the library to research -- you
    need to travel there (internet) and wait in line (rate limiting).

DATA SOURCES:
    1. EDHREC API (online): Commander pages, card recommendations, themes
    2. Built-in knowledge (offline): General Commander strategy and strategy tips

    The script generates two types of training data:
    - Commander-specific: "What creatures go in a Muldrotha deck?" (from API)
    - General strategy: "How many lands should I run?" (hardcoded knowledge)

Usage:
    python convert_edhrec_data.py --output edhrec_training.jsonl --num-commanders 50
"""

# =============================================================================
# IMPORTS
# =============================================================================

# json: For parsing API responses (which come as JSON) and writing JSONL output.
import json

# requests: A popular HTTP library for making web requests.
# Unlike urllib (used in convert_mtg_data.py), requests has a friendlier API:
#   urllib: response = urllib.request.urlopen(url); data = response.read()
#   requests: response = requests.get(url); data = response.json()
#
# Real-world analogy: urllib is like a manual transmission car -- it works but
# requires more effort. requests is like an automatic -- easier to use, same
# destination. We use requests here because we're making many API calls and
# need better error handling.
#
# NOTE: 'requests' is NOT part of Python's standard library. You need to
# install it: pip install requests (or it's in our pyproject.toml dependencies).
import requests

# random: Not used heavily here, but available for shuffling if needed.
import random

# time: For adding delays between API requests (rate limiting).
# time.sleep(1) pauses execution for 1 second.
# This is important for being a good internet citizen -- hammering a server
# with rapid requests can get you blocked and hurts the service for everyone.
# Real-world analogy: Like waiting your turn in line instead of cutting ahead.
import time

# argparse: For command-line arguments (see finetune_qwen.py for detailed explanation).
import argparse

# pathlib.Path: Modern file path handling (see convert_mtg_data.py for explanation).
from pathlib import Path


# =============================================================================
# EDHREC API CONFIGURATION
# =============================================================================
# EDHREC provides a public JSON API that returns card data in structured format.
# These URLs are the base endpoints we'll use to fetch commander information.
#
# The API returns data in a nested JSON structure:
#   {"container": {"json_dict": {"cardlists": [...], "themes": [...], ...}}}
#
# NOTE: This is an unofficial API (EDHREC doesn't officially document it).
# The endpoints may change over time. If the script breaks, check if EDHREC
# has updated their URL structure.

EDHREC_BASE = "https://json.edhrec.com"
EDHREC_COMMANDERS = f"{EDHREC_BASE}/pages/commanders"  # List of popular commanders
EDHREC_THEMES = f"{EDHREC_BASE}/pages/themes"          # Deck themes/strategies


# =============================================================================
# HTTP FETCH FUNCTION
# =============================================================================

def fetch_json(url, max_retries=3):
    """
    Fetch JSON data from a URL with automatic retry logic.

    Web requests can fail for many reasons: the server is busy, your internet
    hiccups, the API has a temporary error. Retry logic automatically tries
    again instead of crashing on the first failure.

    Real-world analogy: Like redialing a phone number when you get a busy
    signal. You try a few times with short pauses between attempts. If it
    still doesn't work after 3 tries, you give up.

    Args:
        url: The web address to fetch data from
        max_retries: How many times to try before giving up (default: 3)

    Returns:
        Parsed JSON data (as a Python dict/list), or None if all retries failed
    """
    for attempt in range(max_retries):
        try:
            print(f"Fetching: {url}")

            # requests.get() sends an HTTP GET request to the URL.
            # timeout=10 means "give up if the server doesn't respond in 10 seconds."
            # Without a timeout, the script could hang forever on a dead server.
            response = requests.get(url, timeout=10)

            # raise_for_status() checks the HTTP status code.
            # 200 = OK (success)
            # 404 = Not Found (bad URL)
            # 500 = Server Error
            # If the status is an error (4xx or 5xx), this raises an exception.
            response.raise_for_status()

            # Rate limiting: wait 1 second between requests.
            # EDHREC is a community-run site, so we're polite and don't spam them.
            # Real-world analogy: Like saying "thank you" and pausing before
            # asking your next question, instead of rapid-fire interrogating.
            time.sleep(1)

            # .json() parses the response body from a JSON string into a
            # Python dictionary. This is the parsed data we return.
            return response.json()

        except Exception as e:
            # Something went wrong. Print the error and maybe try again.
            print(f"Attempt {attempt + 1} failed: {e}")

            if attempt < max_retries - 1:
                # We have more retries left -- wait a bit and try again.
                # We wait longer (2 seconds) between retries to give the
                # server time to recover.
                time.sleep(2)
            else:
                # All retries exhausted. Give up and return None.
                print(f"Failed to fetch {url}")
                return None


# =============================================================================
# EDHREC DATA FETCHING FUNCTIONS
# =============================================================================

def get_popular_commanders(limit=100):
    """
    Fetch a list of popular commanders from EDHREC.

    EDHREC ranks commanders by the number of decks registered with them.
    This function gets the top commanders so we can generate training data
    about the most commonly played ones.

    Real-world analogy: Like getting the Billboard Top 100 songs -- we want
    to teach the model about the most popular commanders, not obscure ones.

    Args:
        limit: Maximum number of commanders to return

    Returns:
        List of dicts with 'name' and 'url' for each commander
    """
    try:
        # Fetch the commanders index page from EDHREC's API
        data = fetch_json(f"{EDHREC_COMMANDERS}.json")

        if data and 'container' in data and 'json_dict' in data['container']:
            # Navigate the nested JSON structure to find commander lists.
            # EDHREC organizes commanders into categories (by color, by theme, etc.)
            # Each category has a 'cardviews' list of commander cards.
            commanders = data['container']['json_dict'].get('cardlists', [])

            top_commanders = []
            for cardlist in commanders[:limit]:
                if 'cardviews' in cardlist:
                    # Get top 20 commanders from each category
                    for card in cardlist['cardviews'][:20]:
                        if 'name' in card:
                            top_commanders.append({
                                'name': card['name'],
                                'url': card.get('url', '')
                            })
            # Trim to the requested limit
            return top_commanders[:limit]

    except Exception as e:
        print(f"Error getting commanders: {e}")

    # Return empty list on failure (instead of crashing)
    return []


def get_commander_page(commander_name):
    """
    Fetch detailed data for a specific commander from EDHREC.

    Each commander has a dedicated page with:
    - Recommended cards by category (creatures, instants, artifacts, etc.)
    - Popular themes/synergies
    - Deck statistics

    Real-world analogy: Like looking up a specific recipe on a cooking site.
    The index page (get_popular_commanders) is the table of contents, and
    this function opens a specific recipe page.

    Args:
        commander_name: The card name (e.g., "Muldrotha, the Gravetide")

    Returns:
        Parsed JSON data for the commander's page, or None if not found
    """
    # Convert the commander's name into a URL-safe format.
    # "Muldrotha, the Gravetide" -> "muldrotha-the-gravetide"
    # EDHREC uses lowercase, hyphen-separated names in their URLs.
    url_name = commander_name.lower().replace(' ', '-').replace(',', '').replace("'", '')
    url = f"{EDHREC_BASE}/pages/commanders/{url_name}.json"

    return fetch_json(url)


# =============================================================================
# QUESTION GENERATION FROM EDHREC DATA
# =============================================================================

def generate_commander_questions(commander_data):
    """
    Generate training Q&A pairs from a commander's EDHREC page.

    This function reads the structured data from EDHREC and creates natural
    language questions and answers about deck building for that commander.

    For example, if EDHREC says the top creatures for Muldrotha are
    [Sakura-Tribe Elder, Mulldrifter, Eternal Witness], we generate:
        Q: "What are good creatures for a Muldrotha, the Gravetide deck?"
        A: "Popular creatures include: Sakura-Tribe Elder, Mulldrifter, ..."

    Real-world analogy: Like reading a "Best Products" review article and
    turning it into flashcard-style Q&A for studying.

    Args:
        commander_data: Parsed JSON from get_commander_page()

    Returns:
        List of Q&A dicts (could be empty if data is malformed)
    """
    questions = []

    # Guard clause: if we got no data, return empty list immediately.
    # This is a defensive programming pattern -- handle the error case first,
    # then proceed with the "happy path."
    if not commander_data:
        return questions

    try:
        # Navigate EDHREC's nested JSON structure.
        # The .get() method returns a default value (empty dict) if the key
        # doesn't exist, preventing KeyError crashes.
        container = commander_data.get('container', {})
        json_dict = container.get('json_dict', {})

        # Get the commander's name from the data
        commander_name = json_dict.get('name', 'this commander')

        # --- Card recommendations by category ---
        # EDHREC groups recommended cards into categories: creatures, instants,
        # sorceries, artifacts, enchantments, lands, etc.
        # Each category has a 'tag' (category name) and 'cardviews' (card list).
        cardlists = json_dict.get('cardlists', [])

        for cardlist in cardlists:
            tag = cardlist.get('tag', '')          # Category name (e.g., "creatures")
            cards = cardlist.get('cardviews', [])[:5]  # Top 5 cards in this category

            if not cards:
                continue  # Skip empty categories

            # Extract just the card names from the card data objects
            card_names = [c.get('name', '') for c in cards if 'name' in c]

            if not card_names:
                continue  # Skip if no valid names found

            # Generate a question for each card category.
            # We only handle the most common categories to keep the data clean.
            # Each question asks about what cards to include in a deck, and
            # the answer lists the top recommendations from EDHREC.
            if tag == 'creatures':
                questions.append({
                    "user": f"What are good creatures for a {commander_name} deck?",
                    "assistant": f"Popular creatures in {commander_name} decks include: {', '.join(card_names[:3])}. These cards synergize well with the commander's strategy."
                })
            elif tag == 'instants':
                questions.append({
                    "user": f"What instants should I include in {commander_name}?",
                    "assistant": f"Top instant choices for {commander_name} include: {', '.join(card_names[:3])}. These provide interaction while supporting your game plan."
                })
            elif tag == 'sorceries':
                questions.append({
                    "user": f"What sorceries work well in {commander_name}?",
                    "assistant": f"Strong sorceries for {commander_name} include: {', '.join(card_names[:3])}. These help advance your strategy effectively."
                })
            elif tag == 'artifacts':
                questions.append({
                    "user": f"What artifacts should I run in {commander_name}?",
                    "assistant": f"Key artifacts for {commander_name} include: {', '.join(card_names[:3])}. These provide ramp and utility."
                })
            elif tag == 'lands':
                questions.append({
                    "user": f"What lands are good in {commander_name}?",
                    "assistant": f"Important lands for {commander_name} include: {', '.join(card_names[:3])}. These help fix your mana and provide utility."
                })

        # --- Themes/synergies ---
        # EDHREC identifies themes that work well with each commander.
        # Themes are strategic directions like "Graveyard," "Tokens," "+1/+1 counters."
        themes = json_dict.get('themes', [])
        if themes:
            theme_list = [t.get('name', '') for t in themes[:3] if 'name' in t]
            if theme_list:
                questions.append({
                    "user": f"What themes work well with {commander_name}?",
                    "assistant": f"{commander_name} synergizes with these themes: {', '.join(theme_list)}. Build around these strategies for best results."
                })

    except Exception as e:
        # If anything goes wrong parsing this commander's data, log the error
        # and return whatever questions we managed to generate (could be empty).
        print(f"Error generating questions: {e}")

    return questions


# =============================================================================
# HARDCODED GENERAL KNOWLEDGE
# =============================================================================
# These functions provide general Commander format knowledge that doesn't
# depend on EDHREC's API. Even if the API calls fail, we still get useful
# training data from these.
#
# This is a resilience pattern: always have a fallback data source.
# Real-world analogy: Like a teacher who has lecture notes (hardcoded data)
# even if the projector (API) breaks.

def generate_general_commander_questions():
    """
    General Commander format strategy questions.

    These cover the universal deck-building principles that apply to
    virtually every Commander deck, regardless of the commander chosen.
    They represent the foundational knowledge every EDH player needs.
    """
    questions = [
        {
            # LAND COUNT: The most fundamental deck-building question.
            # Too few lands = can't cast spells. Too many = draw too many blanks.
            "user": "How many lands should I run in a Commander deck?",
            "assistant": "Most Commander decks run 36-38 lands. Use 36 lands if you have 10+ ramp sources (mana rocks/dorks), 37-38 as a baseline, and 38-40 if your curve is high or you lack ramp. Adjust based on your deck's mana curve and strategy."
        },
        {
            # MANA CURVE: The distribution of cards by mana cost.
            # Commander curves higher than 60-card formats because games go longer.
            "user": "What's the ideal mana curve for Commander?",
            "assistant": "Commander curves are typically higher than other formats. A good distribution: 1-2 CMC (8-10 cards for early plays/ramp), 3-4 CMC (12-15 cards for your engine), 5-6 CMC (8-10 cards for powerful effects), 7+ CMC (4-6 bombs/finishers). Adjust based on strategy - aggro curves lower, control curves higher."
        },
        {
            # REMOVAL: Interaction is essential in a multiplayer format.
            # You need answers to other players' threats.
            "user": "How much removal should I include in Commander?",
            "assistant": "Include 8-12 removal spells in Commander. This should be a mix of: single-target removal (4-6 cards like Path to Exile, Beast Within), board wipes (2-4 cards like Wrath of God), and flexible answers (2-3 cards like Generous Gift). More removal for competitive metas, less for casual."
        },
        {
            # RULE OF 8: A popular heuristic for Commander deck building.
            # It's a starting point, not a strict rule.
            "user": "What's the rule of 8 in Commander deck building?",
            "assistant": "The Rule of 8: For each effect you want in your deck, include 8 cards that provide it. For example, 8 ramp sources, 8 card draw effects, 8 removal spells. This increases consistency while still allowing for 99 unique cards. It's a guideline, not a strict rule."
        },
        {
            # CARD DRAW: The engine that keeps your deck running.
            # Running out of cards in hand = running out of options.
            "user": "How much card draw should a Commander deck have?",
            "assistant": "Include 8-12 sources of card advantage in Commander. This includes: card draw spells (Rhystic Study, Fact or Fiction), repeatable draw (Phyrexian Arena), and wheel effects (Wheel of Fortune). Blue decks want more (10-12), aggressive decks can run less (6-8) if they have other velocity."
        },
        {
            # RAMP: Mana acceleration to cast bigger spells faster.
            # In Commander, games go longer, so ramp lets you stay ahead.
            "user": "What's the best ramp package for Commander?",
            "assistant": "A good ramp package includes 10-12 sources: 2-mana rocks (Sol Ring, Arcane Signet, Signets), 3-mana rocks (Commander's Sphere, Coalition Relic), land ramp (Cultivate, Kodama's Reach, Rampant Growth), and mana dorks (Llanowar Elves, Birds of Paradise). Green gets land ramp, other colors focus on artifacts."
        },
        {
            # TUTORS: Consistency vs variance tradeoff.
            # More tutors = more consistent but potentially less fun.
            "user": "Should I include tutors in my Commander deck?",
            "assistant": "Tutors are powerful but meta-dependent. Competitive decks run 4-8 tutors (Demonic Tutor, Vampiric Tutor, Worldly Tutor). Casual decks might run 0-3. Tutors increase consistency but slow down games and reduce variance. Discuss with your playgroup - some prefer lower-power without tutors."
        },
    ]
    return questions


def generate_strategy_questions():
    """
    General MTG strategy questions that apply across formats.

    These cover the strategic foundations that separate beginners from
    intermediate players: understanding matchups, card advantage,
    deck building fundamentals.
    """
    questions = [
        {
            # BEATING COMBO: Requires understanding the opponent's gameplan
            # and choosing the right angle of attack.
            "user": "What's the best way to deal with a combo deck?",
            "assistant": "Combat combo decks with: 1) Interaction - hold up counterspells or removal for combo pieces, 2) Pressure - kill them before they combo, 3) Hate pieces - Rest in Peace vs graveyard combos, Rule of Law vs storm, 4) Disruption - thoughtseize their key pieces. Know the popular combos in your meta."
        },
        {
            # BEATING CONTROL: Requires patience and resource management.
            # The biggest mistake is overextending into board wipes.
            "user": "How do I beat control decks?",
            "assistant": "Beat control with: 1) Threats that stick - uncounterable (Cavern of Souls, Carnage Tyrant), or recursive threats, 2) Card advantage - draw more cards than they can answer, 3) Protection - Veil of Summer, Boseiju, 4) Diverse threats - don't overextend into board wipes, 5) Efficient threats - make them have the answer immediately."
        },
        {
            # BEST REMOVAL BY COLOR: A reference for deck builders.
            # Each color has different strengths in interaction.
            "user": "What's the best removal spell in each color?",
            "assistant": "Best removal by color: White - Path to Exile (1 mana exile), Swords to Plowshares. Black - Fatal Push, Terminate. Blue - Counterspell, Pongify (creature only). Red - Lightning Bolt, Chaos Warp. Green - Beast Within, Force of Vigor. Colorless - Dismember, Oblivion Stone."
        },
        {
            # 3-COLOR MANA BASES: One of the hardest deck-building challenges.
            # Getting three colors consistently requires careful land selection.
            "user": "How do I build a mana base for a 3-color deck?",
            "assistant": "For 3-color mana bases: 1) Fetchlands (9-10 if budget allows), 2) Shocklands/duals (6-9), 3) Basics (3-6 of each color), 4) Utility lands (2-4), 5) Color-fixing lands (Triomes, Command Tower). Total ~36 lands. Prioritize your primary colors, ensure you can cast turn 1-2 plays reliably."
        },
        {
            # CARD ADVANTAGE: One of the most important concepts in all of MTG.
            # Understanding card advantage separates good players from great ones.
            "user": "What's card advantage and why does it matter?",
            "assistant": "Card advantage is having more cards than your opponent. It matters because: more cards = more options = better chance to win. Generate card advantage through: 1) Draw spells (divination effects), 2) 2-for-1s (one card kills two), 3) Recursive threats, 4) Engines (Rhystic Study). The player with more cards usually wins long games."
        },
    ]
    return questions


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    """
    Main entry point: fetch EDHREC data, combine with general knowledge, save.

    This script's pipeline is:
    1. Add hardcoded general Commander knowledge (always available, offline)
    2. Fetch popular commanders from EDHREC (requires internet)
    3. For each commander, fetch their page and generate Q&A pairs
    4. Combine all data into training format and save to JSONL

    The hardcoded data ensures we always get SOME training data even if
    EDHREC's API is down or we have no internet connection.
    """

    # --- Parse command-line arguments ---
    parser = argparse.ArgumentParser(
        description="Convert EDHREC data to training format"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="edhrec_training.jsonl",
        help="Output JSONL file"
    )
    parser.add_argument(
        "--num-commanders",
        type=int,
        default=50,
        # How many commanders to fetch data for. More commanders = more
        # diverse training data, but takes longer due to API rate limiting.
        # At ~1 second per request, 50 commanders takes about a minute.
        help="Number of commanders to fetch data for"
    )
    parser.add_argument(
        "--include-general",
        action="store_true",
        default=True,
        # Include the hardcoded general strategy questions.
        # Almost always want this True for richer training data.
        help="Include general Commander strategy questions"
    )

    args = parser.parse_args()

    print("\n" + "="*70)
    print("GENERATING EDHREC TRAINING DATA")
    print("="*70)
    print(f"This will take a while (~{args.num_commanders} seconds with rate limiting)")
    print("="*70 + "\n")

    all_questions = []

    # --- Step 1: Add hardcoded general knowledge ---
    # This is our "offline" data that's always available.
    if args.include_general:
        print("Adding general Commander strategy questions...")
        all_questions.extend(generate_general_commander_questions())
        all_questions.extend(generate_strategy_questions())
        print(f"Added {len(all_questions)} general questions")

    # --- Step 2: Fetch commander list from EDHREC ---
    # This is the "online" portion that requires internet access.
    print("\nFetching popular commanders...")
    commanders = get_popular_commanders(args.num_commanders)
    print(f"Found {len(commanders)} commanders")

    # --- Step 3: Fetch data for each commander ---
    # This is the longest part due to rate limiting (1 second between requests).
    # We process each commander one at a time, generating Q&A pairs from their
    # EDHREC page data.
    for i, commander in enumerate(commanders, 1):
        # Print progress so the user knows the script isn't stuck.
        # enumerate(commanders, 1) starts counting from 1 instead of 0.
        print(f"\n[{i}/{len(commanders)}] Processing {commander['name']}...")

        # Fetch the commander's EDHREC page
        commander_data = get_commander_page(commander['name'])

        if commander_data:
            # Generate Q&A pairs from the fetched data
            questions = generate_commander_questions(commander_data)
            all_questions.extend(questions)
            print(f"  Generated {len(questions)} questions")
        else:
            # API call failed for this commander -- skip and continue.
            # We don't crash on individual failures; we just note them and
            # move on. This makes the script resilient to partial API outages.
            print(f"  Failed to get data")

    # --- Step 4: Convert to training format and save ---
    # Same conversion as the other scripts: internal format -> messages format.
    training_data = []
    for q in all_questions:
        training_data.append({
            "messages": [
                {"role": "user", "content": q["user"]},
                {"role": "assistant", "content": q["assistant"]}
            ]
        })

    # Write to JSONL file
    print(f"\nSaving to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item) + '\n')

    # --- Print summary ---
    print("\n" + "="*70)
    print("DONE!")
    print("="*70)
    print(f"Generated {len(training_data)} training examples")
    print(f"Saved to: {args.output}")
    print("\nYou can now train with:")
    print(f"python finetune_qwen.py --dataset file --data-file {args.output}")
    print("="*70)


# Only run main() when executed directly.
# See convert_mtg_data.py for detailed explanation of this pattern.
if __name__ == "__main__":
    main()
