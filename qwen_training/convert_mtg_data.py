"""
Convert MTGJSON data to instruction-following training format
==============================================================

WHAT THIS SCRIPT DOES:
    Takes raw Magic: The Gathering card data (from MTGJSON.com) and transforms
    it into question-answer pairs that can be used to train a language model.

    Real-world analogy: Imagine you have an encyclopedia of every MTG card ever
    printed (AllPrintings.json). This script reads that encyclopedia and creates
    a set of flashcards (Q&A pairs) from it. The language model then studies
    these flashcards to learn about MTG cards.

HOW THE DATA FLOWS:
    1. Input:  AllPrintings.json (raw card database, ~150MB, every card ever printed)
               -- OR --
               AtomicCards.json (deduplicated cards, ~50MB, one entry per unique card)
    2. Process: For each card, generate multiple Q&A pairs:
               "What type of card is Lightning Bolt?" -> "Lightning Bolt is an Instant."
               "What does Lightning Bolt do?" -> "Lightning Bolt deals 3 damage..."
    3. Output: mtg_training.jsonl (one Q&A pair per line, ready for fine-tuning)

WHY JSONL FORMAT?
    JSONL (JSON Lines) stores one JSON object per line. This is the standard
    format for ML training data because:
    - Each line is independent (easy to shuffle, sample, or split)
    - Can process line-by-line without loading entire file into memory
    - Easy to concatenate multiple JSONL files together (just cat them)

    Real-world analogy: JSONL is like a deck of index cards. Each card is
    self-contained. You can shuffle them, split the deck, or combine decks.
    Regular JSON is like a book -- you need the whole thing to make sense of it.

MTGJSON DATA SOURCES:
    - AllPrintings.json: Every printing of every card, organized by set.
      Like a catalog that lists every edition of every book ever published.
    - AtomicCards.json: One entry per unique card (no duplicates from reprints).
      Like a catalog that lists each book title only once.

Usage:
    # Use existing AllPrintings.json
    python convert_mtg_data.py --data-file AllPrintings.json --output mtg_training.jsonl --num-examples 1000

    # Download fresh AtomicCards.json
    python convert_mtg_data.py --download --file-type atomic --output mtg_training.jsonl

    # Download fresh AllPrintings.json
    python convert_mtg_data.py --download --file-type allprintings --output mtg_training.jsonl
"""

# =============================================================================
# IMPORTS
# =============================================================================

# json: For reading the MTGJSON data files and writing the output JSONL.
# JSON (JavaScript Object Notation) is a text format for structured data.
# It uses key-value pairs like {"name": "Lightning Bolt", "type": "Instant"}.
import json

# random: For shuffling and sampling cards. We use randomness to:
# 1. Shuffle which cards get processed (so we get a diverse mix)
# 2. Sample random card pairs for comparison questions
# Without shuffling, we'd always get cards from the same sets/alphabetical range.
import random

# argparse: For command-line arguments (see finetune_qwen.py for detailed explanation).
import argparse

# urllib.request: Python's built-in HTTP download library.
# We use it to download card data files from mtgjson.com.
# It's simpler than the 'requests' library but comes with Python by default,
# so no extra installation needed.
# Real-world analogy: urllib is like a basic web browser that can only download
# files -- no fancy features, but it gets the job done.
import urllib.request

# pathlib.Path: A modern way to work with file paths.
# Path("my_file.json").exists() checks if a file exists.
# It's more readable than os.path.exists() and works the same on all operating systems.
from pathlib import Path


# =============================================================================
# DOWNLOAD FUNCTION
# =============================================================================

def download_mtg_data(file_type="atomic", output_file=None):
    """
    Download MTGJSON data file from the internet.

    MTGJSON (mtgjson.com) is a free, open-source project that maintains a
    complete database of every Magic: The Gathering card ever printed.
    They provide their data as JSON files via a REST API.

    Real-world analogy: This is like going to a library's website and
    downloading their entire catalog as a single file.

    Args:
        file_type: Which database file to download:
            'atomic' = AtomicCards.json (~50MB) -- one entry per unique card name
            'allprintings' = AllPrintings.json (~150MB) -- every printing of every card
        output_file: Custom filename to save as (optional, uses default if None)

    Returns:
        Path to the downloaded file as a string
    """
    # Dictionary mapping file types to their download URLs.
    # These are the official MTGJSON v5 API endpoints.
    urls = {
        "atomic": "https://mtgjson.com/api/v5/AtomicCards.json",
        "allprintings": "https://mtgjson.com/api/v5/AllPrintings.json"
    }

    # Default filenames for each type
    default_names = {
        "atomic": "AtomicCards.json",
        "allprintings": "AllPrintings.json"
    }

    # Validate the file_type argument
    if file_type not in urls:
        raise ValueError(f"Unknown file type: {file_type}. Use 'atomic' or 'allprintings'")

    url = urls[file_type]
    # Use the custom filename if provided, otherwise use the default
    filename = output_file or default_names[file_type]

    print(f"Downloading {url}...")
    if file_type == "allprintings":
        print("This is a large file (~150MB), may take 5-10 minutes...")
    else:
        print("This may take a few minutes (~50MB)...")

    # urlretrieve() downloads a URL and saves it directly to a file.
    # This is a simple "download and save" operation -- no streaming or
    # progress bars, but it works reliably.
    urllib.request.urlretrieve(url, filename)
    print(f"Downloaded to {filename}")
    return filename


# =============================================================================
# DATA LOADING FUNCTION
# =============================================================================

def load_mtg_data(filepath):
    """
    Load MTGJSON data and extract unique cards into a dictionary.

    This function auto-detects whether you've given it AtomicCards.json or
    AllPrintings.json and handles each format differently.

    Real-world analogy: Imagine someone hands you either a phone book
    (organized by name) or a city directory (organized by neighborhood).
    This function figures out which one you got and extracts the people's
    info either way.

    THE TWO FORMATS:
        AtomicCards.json structure:
            {"data": {
                "Lightning Bolt": [card_data_variant1, ...],
                "Counterspell": [card_data_variant1, ...],
                ...
            }}
        Cards are already organized by name. Each card name maps to a list
        of variants (different printings may have different art but same rules).

        AllPrintings.json structure:
            {"data": {
                "LEA": {"name": "Limited Edition Alpha", "cards": [card1, card2, ...]},
                "M21": {"name": "Core Set 2021", "cards": [card1, card2, ...]},
                ...
            }}
        Cards are organized by SET CODE. The same card appears multiple times
        if it was printed in multiple sets. We need to deduplicate.

    Returns:
        Dictionary keyed by card name, where each value is a list of card
        data objects (different printings/variants of that card).
        Example: {"Lightning Bolt": [{printing1_data}, {printing2_data}, ...]}
    """
    print(f"Loading {filepath}...")

    # Load the entire JSON file into memory.
    # For AllPrintings.json (~150MB), this will use about 1-2GB of RAM after
    # parsing. json.load() reads the file and converts it to Python dicts/lists.
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Both MTGJSON formats have a top-level "data" key containing the actual content.
    # The "meta" key (also present) contains version info, which we ignore.
    if "data" in data:
        raw_data = data["data"]

        # AUTO-DETECT FORMAT:
        # Peek at the first entry to determine if it's AtomicCards or AllPrintings.
        # next(iter(...)) gets the first key from the dictionary without loading all keys.
        first_key = next(iter(raw_data.keys()))
        first_value = raw_data[first_key]

        if isinstance(first_value, list):
            # ATOMICCARDS FORMAT: values are lists (of card variants)
            # The data is already organized by card name -- no work needed!
            # Example: raw_data["Lightning Bolt"] = [{card_data}]
            print(f"Detected AtomicCards format")
            cards = raw_data
            print(f"Loaded {len(cards)} unique cards")
            return cards

        elif isinstance(first_value, dict) and "cards" in first_value:
            # ALLPRINTINGS FORMAT: values are set objects containing card lists
            # We need to iterate through every set, extract every card, and
            # group them by name (deduplication).
            #
            # Real-world analogy: Like going through every bookstore in the
            # country and building a master list of unique book titles. The
            # same book might be in many stores, but we only need one entry.
            print(f"Detected AllPrintings format")
            cards_dict = {}       # Our output: card_name -> [printings]
            total_printings = 0   # Counter for total card printings found

            # Iterate through every set in the database
            for set_code, set_data in raw_data.items():
                # Each set has a "cards" list containing all cards in that set
                for card in set_data.get("cards", []):
                    card_name = card.get("name")
                    if card_name:
                        # If we haven't seen this card name before, create a new list
                        if card_name not in cards_dict:
                            cards_dict[card_name] = []
                        # Add this printing to the card's list
                        cards_dict[card_name].append(card)
                        total_printings += 1

            print(f"Loaded {len(cards_dict)} unique cards from {total_printings} printings")
            return cards_dict
        else:
            raise ValueError("Unknown MTGJSON format")
    else:
        raise ValueError("Not a valid MTGJSON file (missing 'data' key)")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
# These small utility functions format raw card data into human-readable text
# for use in the Q&A pairs. Think of them as "translators" that convert the
# database's shorthand into natural English.

def format_mana_cost(mana_cost):
    """
    Convert mana cost symbols to readable English.

    MTGJSON stores mana costs in a symbolic format: "{1}{R}" means
    "1 generic mana + 1 red mana." This function converts those symbols
    into readable text like "1 Red."

    Real-world analogy: Like converting chemical formulas to English names.
    "H2O" becomes "water." "{2}{U}{U}" becomes "2 Blue Blue."

    The five colors of Magic and their letter codes:
        W = White (Plains)
        U = Blue  (Island) -- "U" because "B" was taken by Black
        B = Black (Swamp)
        R = Red   (Mountain)
        G = Green (Forest)
    """
    if not mana_cost:
        return "no mana cost"

    # Strip the curly braces and replace color letters with full names.
    # "{2}{W}{U}" -> "2 W U " -> "2 White Blue"
    readable = mana_cost.replace("{", "").replace("}", " ")
    readable = readable.replace("W", "White").replace("U", "Blue")
    readable = readable.replace("B", "Black").replace("R", "Red")
    readable = readable.replace("G", "Green").replace("C", "Colorless")
    readable = readable.replace("X", "X").strip()

    return readable


def get_card_colors(card):
    """
    Get a card's color identity as a readable string.

    Color identity determines which colors are associated with a card.
    This is especially important in Commander, where your deck can only
    contain cards within your commander's color identity.

    We prefer 'colorIdentity' over 'colors' because:
    - 'colors' = the colors the card IS (based on mana cost)
    - 'colorIdentity' = all colors associated with the card (includes
      colors in the rules text, not just the mana cost)

    Example: Kenrith, the Returned King has a White mana cost but has
    abilities of all 5 colors, so colorIdentity = [W, U, B, R, G].

    Real-world analogy: 'colors' is like someone's nationality (where
    they're from). 'colorIdentity' is like all the languages they speak
    (which might include more than just their native tongue).
    """
    # Try colorIdentity first, fall back to colors
    colors = card.get('colorIdentity', card.get('colors', []))
    if not colors:
        return "colorless"

    # Map single-letter codes to full color names
    color_names = {
        'W': 'White', 'U': 'Blue', 'B': 'Black',
        'R': 'Red', 'G': 'Green'
    }

    color_list = [color_names.get(c, c) for c in colors]

    # Format with proper English grammar (commas and "and")
    if len(color_list) == 1:
        return color_list[0]                    # "Red"
    elif len(color_list) == 2:
        return f"{color_list[0]} and {color_list[1]}"  # "Red and Blue"
    else:
        # Oxford comma for 3+ colors: "Red, Blue, and Green"
        return ", ".join(color_list[:-1]) + f", and {color_list[-1]}"


# =============================================================================
# QUESTION GENERATION FUNCTIONS
# =============================================================================
# Each function below generates a specific TYPE of question about a card.
# Together, they create diverse training data that teaches the model about
# different aspects of MTG cards.
#
# WHY MULTIPLE QUESTION TYPES?
# If we only asked "What does X do?", the model would only learn to answer
# that one question format. By generating many question types (mana cost,
# colors, creature type, format legality, strategy), the model learns to
# discuss cards from many angles.
#
# Real-world analogy: Studying for an exam is more effective when you use
# different question formats (multiple choice, short answer, essay) rather
# than just one format. Each format tests understanding in a different way.

def generate_basic_info_questions(card_name, card):
    """
    Generate questions about a card's basic properties.

    These are the fundamental facts: type, mana cost, colors, and rules text.
    Think of these as the "ID card" questions -- name, age, address, etc.
    """
    questions = []

    # --- Card Type ---
    # "type" in MTGJSON is the full type line, e.g., "Legendary Creature - Human Wizard"
    # This tells you what kind of game object the card is and what rules apply to it.
    card_type = card.get('type', 'Unknown')
    questions.append({
        "user": f"What type of card is {card_name}?",
        "assistant": f"{card_name} is a {card_type}."
    })

    # --- Mana Cost ---
    # The mana cost determines when you can play the card.
    # Not all cards have a mana cost (e.g., lands, some special cards).
    if 'manaCost' in card:
        mana = format_mana_cost(card['manaCost'])
        questions.append({
            "user": f"What is the mana cost of {card_name}?",
            "assistant": f"The mana cost of {card_name} is {mana}."
        })

    # --- Colors ---
    # A card's colors affect what deck it goes in and how it interacts with
    # color-specific abilities (like "protection from red").
    colors = get_card_colors(card)
    questions.append({
        "user": f"What colors is {card_name}?",
        "assistant": f"{card_name} is {colors}."
    })

    # --- Rules Text ---
    # The "text" field contains the card's abilities and effects.
    # This is the most important part for gameplay -- what the card DOES.
    if 'text' in card and card['text']:
        questions.append({
            "user": f"What does {card_name} do?",
            "assistant": f"{card_name}: {card['text']}"
        })

    return questions


def generate_stats_questions(card_name, card):
    """
    Generate questions about a card's numerical stats.

    Different card types have different stats:
    - Creatures have power/toughness (attack/defense)
    - Planeswalkers have loyalty (their "health")
    - All cards with a mana cost have a mana value (total cost)

    Real-world analogy: Like asking about a sports player's stats.
    "What's their batting average?" (power/toughness)
    "How much does this car cost?" (mana value)
    """
    questions = []

    # --- Power and Toughness ---
    # Only creatures (and some vehicles) have these.
    # Power = damage dealt in combat (like attack strength)
    # Toughness = how much damage it takes to destroy (like health points)
    # A 3/4 creature deals 3 damage and survives up to 4 damage.
    if 'power' in card and 'toughness' in card:
        questions.append({
            "user": f"What are the power and toughness of {card_name}?",
            "assistant": f"{card_name} is a {card['power']}/{card['toughness']}."
        })

    # --- Planeswalker Loyalty ---
    # Planeswalkers are special cards that act like allies on the battlefield.
    # Loyalty is their "health" -- they start with this amount and gain/lose
    # loyalty when you activate their abilities. They die when loyalty hits 0.
    if 'loyalty' in card:
        questions.append({
            "user": f"What is the starting loyalty of {card_name}?",
            "assistant": f"{card_name} starts with {card['loyalty']} loyalty counters."
        })

    # --- Mana Value ---
    # Mana value (formerly "converted mana cost" or CMC) is the TOTAL mana
    # cost as a single number. {2}{R}{R} = mana value 4.
    # This matters for many game effects that reference mana value.
    if 'manaValue' in card:
        questions.append({
            "user": f"What is the mana value of {card_name}?",
            "assistant": f"{card_name} has a mana value of {card['manaValue']}."
        })

    return questions


def generate_subtypes_questions(card_name, card):
    """
    Generate questions about a card's creature/spell subtypes.

    Subtypes are the specific classifications after the dash on the type line.
    For "Legendary Creature - Human Wizard":
        Supertypes: Legendary
        Types: Creature
        Subtypes: Human, Wizard

    Subtypes matter for "tribal" effects -- cards that care about creature types.
    E.g., "All Goblins get +1/+1" affects any creature with the Goblin subtype.

    Real-world analogy: Types are like "animal" and subtypes are like "golden
    retriever." A card that says "all Dogs get +1/+1" would affect golden
    retrievers because they're a type of dog.
    """
    questions = []

    if 'subtypes' in card and card['subtypes']:
        # Join subtypes into a readable string: ["Human", "Wizard"] -> "Human, Wizard"
        subtypes = ", ".join(card['subtypes'])

        # For creature cards, ask specifically about creature type
        if 'Creature' in card.get('type', ''):
            questions.append({
                "user": f"What creature type is {card_name}?",
                "assistant": f"{card_name} is a {subtypes}."
            })

        # General subtype question (works for any card type)
        questions.append({
            "user": f"What are the subtypes of {card_name}?",
            "assistant": f"The subtypes of {card_name} are: {subtypes}."
        })

    return questions


def generate_format_questions(card_name, card):
    """
    Generate questions about which formats a card is legal in.

    Magic has multiple "formats" (rulesets) that restrict which cards you can
    use. Think of formats like different leagues in sports:
    - Standard: Only recent sets (like playing with this year's roster)
    - Modern: Sets from 2003+ (larger card pool)
    - Legacy: Almost all cards ever printed (very powerful)
    - Vintage: All cards, but some are restricted to 1 copy
    - Commander: 100-card singleton decks with a legendary creature leader

    Some cards are "banned" in certain formats because they're too powerful
    and warp the game around them.

    Real-world analogy: Like how certain equipment is banned in some sports
    leagues but allowed in others. A corked bat might be fine in a casual
    league but banned in the MLB.
    """
    questions = []

    if 'legalities' in card:
        legalities = card['legalities']

        # Check each major format
        for format_name in ['standard', 'modern', 'commander', 'legacy', 'vintage']:
            if format_name in legalities:
                legality = legalities[format_name]
                if legality == 'Legal':
                    questions.append({
                        "user": f"Is {card_name} legal in {format_name.capitalize()}?",
                        "assistant": f"Yes, {card_name} is legal in {format_name.capitalize()}."
                    })
                elif legality == 'Banned':
                    questions.append({
                        "user": f"Is {card_name} legal in {format_name.capitalize()}?",
                        "assistant": f"No, {card_name} is banned in {format_name.capitalize()}."
                    })

    return questions


def generate_comparison_questions(cards_dict):
    """
    Generate questions that compare two different cards.

    Comparison questions teach the model to reason about relationships
    between cards, not just recite facts about individual ones.

    Real-world analogy: Like asking a student "Which is heavier, iron or
    aluminum?" instead of just "What does iron weigh?" Comparisons require
    UNDERSTANDING, not just memorization.

    Args:
        cards_dict: The full dictionary of all cards (we sample pairs from it)

    Returns:
        List of comparison Q&A pairs
    """
    questions = []

    # Get all card names for random sampling
    card_names = list(cards_dict.keys())

    # Generate a small number of comparison questions.
    # We limit this because comparisons between random cards aren't always
    # interesting (comparing a land to a creature doesn't make much sense).
    # min(50, ...) caps at 50 comparisons even for huge card pools.
    for _ in range(min(50, len(card_names) // 100)):
        # Pick two random cards to compare
        card1_name = random.choice(card_names)
        card2_name = random.choice(card_names)

        # Skip if we randomly picked the same card twice
        if card1_name == card2_name:
            continue

        # Get the first printing of each card (all printings have the same rules)
        card1 = cards_dict[card1_name][0]
        card2 = cards_dict[card2_name][0]

        # Compare mana values (total casting cost)
        if 'manaValue' in card1 and 'manaValue' in card2:
            mv1 = card1['manaValue']
            mv2 = card2['manaValue']

            # Only generate a question if they have different costs
            # (comparing two cards with the same cost isn't interesting)
            if mv1 < mv2:
                questions.append({
                    "user": f"Which costs more mana, {card1_name} or {card2_name}?",
                    "assistant": f"{card2_name} costs more mana. {card1_name} has a mana value of {mv1}, while {card2_name} has a mana value of {mv2}."
                })
            elif mv1 > mv2:
                questions.append({
                    "user": f"Which costs less mana, {card1_name} or {card2_name}?",
                    "assistant": f"{card2_name} costs less mana. {card2_name} has a mana value of {mv2}, while {card1_name} has a mana value of {mv1}."
                })

    return questions


def generate_strategy_questions(card_name, card):
    """
    Generate strategic/gameplay-oriented questions about a card.

    These go beyond pure facts and teach the model about HOW to use cards.
    This is the difference between knowing "Lightning Bolt deals 3 damage"
    and knowing "Lightning Bolt is best used as removal in the early game."

    Real-world analogy: Like the difference between reading a recipe
    (the card text) and getting cooking tips from a chef (strategy advice).
    """
    questions = []

    card_type = card.get('type', '')

    # --- Creature strategy ---
    # Creatures are the most common card type, and combat strategy is core
    # to Magic gameplay. We ask about how to use them in combat.
    if 'Creature' in card_type:
        if 'power' in card and 'toughness' in card:
            power = card['power']
            toughness = card['toughness']

            questions.append({
                "user": f"How can I use {card_name} in combat?",
                "assistant": f"{card_name} is a {power}/{toughness} creature. {card.get('text', 'It can attack and block.')} Consider its power and toughness when deciding whether to attack or block."
            })

    # --- Instant vs Sorcery timing ---
    # One of the most fundamental rules in Magic: instants can be cast
    # anytime (even on your opponent's turn), sorceries only on your turn.
    # This timing distinction is crucial for strategic play.
    elif 'Instant' in card_type or 'Sorcery' in card_type:
        questions.append({
            "user": f"When can I cast {card_name}?",
            "assistant": f"{card_name} is {'an instant' if 'Instant' in card_type else 'a sorcery'}. {'You can cast it at any time you have priority, including during combat or on your opponent\\'s turn.' if 'Instant' in card_type else 'You can only cast it during your main phase when the stack is empty.'}"
        })

    return questions


# =============================================================================
# MAIN DATA GENERATION FUNCTION
# =============================================================================

def generate_training_data(cards_dict, num_examples=1000):
    """
    Generate training examples from the MTG card database.

    This is the main orchestrator function. It:
    1. Iterates through cards (in random order for diversity)
    2. Calls each question generator on each card
    3. Collects all Q&A pairs
    4. Adds comparison questions
    5. Shuffles and trims to the requested number

    Real-world analogy: Like a textbook author going through an encyclopedia
    and writing study questions for each entry. They write questions about
    definitions, comparisons, and applications, then curate the best ones.

    Args:
        cards_dict: Dictionary of card data from load_mtg_data()
        num_examples: How many training examples to generate (target count)

    Returns:
        List of training examples in the {"messages": [...]} format
    """
    all_questions = []

    # Get all card names and shuffle them randomly.
    # Shuffling ensures we get a diverse mix of cards, not just the first
    # 200 cards alphabetically (which would bias toward cards starting with 'A').
    card_names = list(cards_dict.keys())
    random.shuffle(card_names)

    print(f"Generating training examples from {len(card_names)} cards...")

    for card_name in card_names:
        # Get the first printing of this card.
        # Different printings of the same card have the same rules text,
        # power/toughness, etc. -- only the art, set symbol, and rarity differ.
        # So we just use the first printing for generating questions.
        card = cards_dict[card_name][0]

        # Generate all question types for this card.
        # Each generator returns a list of Q&A dicts (could be 0-5 items
        # depending on what info the card has).
        questions = []
        questions.extend(generate_basic_info_questions(card_name, card))
        questions.extend(generate_stats_questions(card_name, card))
        questions.extend(generate_subtypes_questions(card_name, card))
        questions.extend(generate_format_questions(card_name, card))
        questions.extend(generate_strategy_questions(card_name, card))

        all_questions.extend(questions)

        # Early exit once we've generated enough questions.
        # No need to process all 25,000+ cards if we only need 1,000 examples.
        if len(all_questions) >= num_examples:
            break

    # Add comparison questions (these use the full card pool, not just the
    # ones we generated questions for above).
    all_questions.extend(generate_comparison_questions(cards_dict))

    # Shuffle all questions randomly and trim to the requested count.
    # Shuffling ensures a good mix of question types in the final dataset
    # (rather than all "what type" questions first, then all "mana cost" ones).
    random.shuffle(all_questions)
    all_questions = all_questions[:num_examples]

    # Convert from our internal format {"user": ..., "assistant": ...}
    # to the training format {"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}
    # This is the format that finetune_qwen.py and the SFTTrainer expect.
    training_data = []
    for q in all_questions:
        training_data.append({
            "messages": [
                {"role": "user", "content": q["user"]},
                {"role": "assistant", "content": q["assistant"]}
            ]
        })

    print(f"Generated {len(training_data)} training examples")
    return training_data


# =============================================================================
# SAVE FUNCTION
# =============================================================================

def save_training_data(training_data, output_file):
    """
    Save training data to a JSONL (JSON Lines) file.

    Each training example is written as a single line of JSON.
    This format is directly compatible with finetune_qwen.py's --data-file option.

    Real-world analogy: Like writing one flashcard per line in a text file.
    Each line is a complete, self-contained flashcard.
    """
    print(f"Saving to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        for item in training_data:
            # json.dumps() converts a Python dict to a JSON string.
            # Each line is one complete JSON object.
            f.write(json.dumps(item) + '\n')

    print(f"Saved {len(training_data)} examples to {output_file}")


# =============================================================================
# MAIN FUNCTION (ENTRY POINT)
# =============================================================================

def main():
    """
    Main entry point: parse arguments, load data, generate examples, save output.

    This function orchestrates the entire pipeline:
    1. Parse command-line arguments (where to get data, how many examples, etc.)
    2. Obtain the card data (download or load from file)
    3. Generate Q&A training examples from the cards
    4. Save to JSONL for use with finetune_qwen.py
    """

    # --- Command-line argument setup ---
    parser = argparse.ArgumentParser(
        description="Convert MTGJSON data to instruction-following training format"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="mtg_training.jsonl",
        # The output file that finetune_qwen.py will read.
        help="Output JSONL file for training data"
    )
    parser.add_argument(
        "--num-examples",
        type=int,
        default=1000,
        # How many Q&A pairs to generate. More examples = more training data
        # = better model (up to a point). Start with 1000 for testing,
        # increase to 5000-10000 for real training runs.
        help="Number of training examples to generate"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        # When this flag is present, download fresh data from MTGJSON.
        # Otherwise, use a local file.
        help="Download fresh data from MTGJSON"
    )
    parser.add_argument(
        "--file-type",
        type=str,
        choices=["atomic", "allprintings"],
        default="atomic",
        # Which MTGJSON format to download. AtomicCards is smaller and faster
        # to download. AllPrintings has more data (like set-specific info).
        help="Which MTGJSON file to download: 'atomic' (AtomicCards.json, ~50MB) or 'allprintings' (AllPrintings.json, ~150MB)"
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        # Point to an existing file on disk instead of downloading.
        # This is what we'll use since we already have AllPrintings.json.
        help="Path to existing MTGJSON data file (AtomicCards.json or AllPrintings.json). If not specified, will look for standard filenames."
    )

    args = parser.parse_args()

    # --- Determine which data file to use ---
    # There are three ways to get the data, checked in this priority order:
    # 1. Download fresh data (--download flag)
    # 2. Use a specified file (--data-file path)
    # 3. Auto-detect files in the current directory
    data_file = None

    if args.download:
        # OPTION 1: Download fresh data from the internet
        print("\n" + "="*70)
        print("DOWNLOADING FRESH DATA")
        print("="*70)
        data_file = download_mtg_data(file_type=args.file_type)

    elif args.data_file:
        # OPTION 2: Use a file the user specified
        if not Path(args.data_file).exists():
            print(f"Error: File not found: {args.data_file}")
            print("\nOptions:")
            print("  1. Check the file path")
            print("  2. Use --download to download fresh data")
            return
        data_file = args.data_file
        print(f"\nUsing existing data file: {data_file}")

    else:
        # OPTION 3: Look for standard filenames in the current directory
        # Check AllPrintings first (more complete), then AtomicCards
        possible_files = ["AllPrintings.json", "AtomicCards.json"]

        for filename in possible_files:
            if Path(filename).exists():
                data_file = filename
                print(f"\nFound existing data file: {data_file}")
                break

        if not data_file:
            # No data file found anywhere -- print helpful instructions
            print("\nNo data file found!")
            print("\nOptions:")
            print("  1. Download AtomicCards.json:")
            print("     python convert_mtg_data.py --download --file-type atomic")
            print("  2. Download AllPrintings.json:")
            print("     python convert_mtg_data.py --download --file-type allprintings")
            print("  3. Specify existing file:")
            print("     python convert_mtg_data.py --data-file path/to/your/file.json")
            return

    # --- Run the pipeline ---
    # Load raw card data from the JSON file
    cards_dict = load_mtg_data(data_file)

    # Generate Q&A training examples from the card data
    training_data = generate_training_data(cards_dict, args.num_examples)

    # Save the training examples to JSONL
    save_training_data(training_data, args.output)

    # --- Print summary ---
    print("\n" + "="*70)
    print("DONE!")
    print("="*70)
    print(f"Training data saved to: {args.output}")
    print(f"Total examples: {len(training_data)}")
    print(f"Source file: {data_file}")
    print("\nYou can now train with:")
    print(f"python finetune_qwen.py --dataset file --data-file {args.output}")
    print("="*70)


# This is a Python convention: only run main() if this script is executed
# directly (e.g., "python convert_mtg_data.py"). If this file is imported
# by another script (e.g., "import convert_mtg_data"), main() won't run
# automatically -- the importer can call individual functions instead.
#
# Real-world analogy: Like a power tool that runs when you press the trigger
# but stays off when you just pick it up. __name__ == "__main__" is the trigger.
if __name__ == "__main__":
    main()
