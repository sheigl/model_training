"""
Scraper for MTG Fandom Wiki archetype data.

Stage 1: Scrape https://mtg.fandom.com/wiki/Category:Deck_archetypes
          to get seed archetype page links (~55 pages).

Stage 2: Scrape each seed page (L0), collecting outbound wiki links.

Stage 3: Scrape each unique outbound link (L1) once — no further recursion.
          Dedup is handled by the visited set, so a page that appears in both
          the category list and as an outbound link is only scraped once.

Output: MongoDB collection 'mtg_archetypes.archetypes'

Requirements:
    pip install selenium beautifulsoup4 pymongo requests
"""

import re
import time
import random
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver

from pymongo import MongoClient

# ── MongoDB ───────────────────────────────────────────────────────────────────
client     = MongoClient('mongodb://root:whatever@server.home:27017/')
db         = client['mtg_archetypes']
collection = db['archetypes']

# ── Config ────────────────────────────────────────────────────────────────────
CATEGORY_URL   = "https://mtg.fandom.com/wiki/Category:Deck_archetypes"
BASE_URL       = "https://mtg.fandom.com"
PAGE_LOAD_WAIT = 15
PAGE_DELAY_MIN = 3.0
PAGE_DELAY_MAX = 6.0
MAX_RETRIES    = 3
# ─────────────────────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# ── Link following filters ────────────────────────────────────────────────────

SKIP_NAMESPACES = re.compile(
    r'^(Category:|Talk:|User:|File:|Template:|Special:|Help:|Magic:|MediaWiki:)',
    re.IGNORECASE
)

NON_ARCHETYPE_SUFFIXES = re.compile(
    r'(_block|_set|_expansion|_format|_mechanic|_cycle|_symbol|_token|'
    r'_card|_rules|_tournament|_pro_tour|_grand_prix|_world_championship|'
    r'_artists?|_designers?|_authors?|_judges?)$',
    re.IGNORECASE
)

NON_ARCHETYPE_EXACT = {
    'Standard', 'Modern', 'Legacy', 'Vintage', 'Pioneer', 'Pauper', 'Commander',
    'Limited', 'Draft', 'Sealed', 'Cube',
    'Tempest', 'Mirage', 'Onslaught', 'Mirrodin', 'Ravnica', 'Kamigawa',
    'Lorwyn', 'Alara', 'Zendikar', 'Innistrad', 'Theros', 'Tarkir', 'Eldraine',
    'Ice_Age', 'Odyssey', 'Masques', 'Invasion', 'Scourge', 'Darksteel',
    'Jay_Schneider', 'Paul_Sligh', 'Dave_Price', 'Mark_Rosewater',
    'Mana_curve', 'Mana_screw', 'Mana_flood', 'Card_advantage', 'Tempo',
    'Netdecking', 'Metagame', 'Sideboard', 'Cantrip', 'Beatdown',
}

ARCHETYPE_KEYWORDS = re.compile(
    r'(_deck|aggro|control|combo|midrange|tempo|ramp|burn|dredge|storm|'
    r'reanimator|infect|affinity|tron|prison|stax|taxes|loam|madness|'
    r'threshold|flashback|shadow|suicide|turbo|belcher|depths|enchantress|'
    r'painter|miracle|sneak|aristocrats|weenie|stompy|fish|zoo|jund|'
    r'jeskai|sultai|abzan|grixis|bant|naya|elves|goblins|merfolk|humans|'
    r'zombies|slivers|sligh|necropotence|tog|gro|pox|manaless|workshop|'
    r'rebels|survival|cradle|academy|bargain|draw.go|land_destruction|'
    r'hate_bears|death.and.taxes)',
    re.IGNORECASE
)


def should_follow(href: str) -> bool:
    """Return True if this wiki link should be queued for crawling."""
    if not href.startswith("/wiki/"):
        return False
    page = href[len("/wiki/"):]
    if SKIP_NAMESPACES.match(page):
        return False
    if NON_ARCHETYPE_SUFFIXES.search(page):
        return False
    if page in NON_ARCHETYPE_EXACT:
        return False
    return bool(ARCHETYPE_KEYWORDS.search(page))


# ── Archetype tagging ─────────────────────────────────────────────────────────

ARCHETYPE_MAP = {
    "aggro":    "Aggro",
    "control":  "Control",
    "combo":    "Combo",
    "midrange": "Midrange",
    "tempo":    "Tempo",
    "ramp":     "Ramp",
    "prison":   "Prison",
    "stax":     "Stax",
}


def extract_archetype(categories: list[str], name: str = "") -> list[str]:
    """
    Derive archetype tags from wiki category labels and/or page name.
    Returns a list since some pages belong to multiple archetypes.
    Returns ["Unknown"] if no archetype keyword is found.
    """
    found = []
    # Check categories first
    combined = " ".join(categories).lower()
    for keyword, label in ARCHETYPE_MAP.items():
        if keyword in combined and label not in found:
            found.append(label)
    # Fallback: check the page name itself
    if not found and name:
        name_lower = name.lower()
        for keyword, label in ARCHETYPE_MAP.items():
            if keyword in name_lower and label not in found:
                found.append(label)
    return found if found else ["Unknown"]


# ── Card name validation ──────────────────────────────────────────────────────

CARD_NAMES: set[str] = set()
CARD_PATTERN: re.Pattern | None = None  # compiled regex for plain-text card matching



def normalise_apostrophes(s: str) -> str:
    """Normalise Unicode quote variants to ASCII apostrophe for consistent matching."""
    return s.replace('’', "'").replace('‘', "'").replace('ʼ', "'")


# ── Card match filtering ──────────────────────────────────────────────────────
# Single-word matches are almost always false positives (creature types, set
# names, common English words that happen to share a name with a card).
# We require 2+ words OR the single word passes a strict allowlist check.

SINGLE_WORD_BLOCKLIST = {
    # Creature types
    'angel', 'angels', 'demon', 'demons', 'dragon', 'dragons',
    'goblin', 'goblins', 'merfolk', 'human', 'humans', 'rebel', 'rebels',
    'rogue', 'rogues', 'zombie', 'zombies', 'soldier', 'soldiers',
    'knight', 'knights', 'wizard', 'wizards', 'elf', 'elves',
    'spirit', 'spirits', 'vampire', 'vampires', 'sliver', 'slivers',
    'beast', 'beasts', 'elemental', 'elementals', 'shaman', 'shamans',
    'cleric', 'clerics', 'druid', 'druids', 'warrior', 'warriors',
    'pirate', 'pirates', 'ally', 'allies', 'construct', 'constructs',
    # Set names that share a card name
    'onslaught', 'torment', 'judgment', 'invasion', 'scourge', 'exodus',
    'tempest', 'mirage', 'visions', 'weatherlight', 'portal', 'homelands',
    'prophecy', 'nemesis', 'mercadian', 'planeshift', 'apocalypse',
    # Common MTG strategy words that are also card names
    'fish', 'bear', 'hate', 'balance', 'tinker', 'survival', 'academy',
    'bargain', 'survival', 'upheaval', 'armageddon', 'wrath', 'damnation',
    # Common English words / verbs
    'lands', 'spells', 'creatures', 'artifacts', 'enchantments',
    'six', 'seven', 'eight', 'nine', 'ten', 'powerful', 'dominate',
    'sacrifice', 'recycle', 'overcome', 'control', 'storm', 'affinity',
    'aggro', 'combo', 'midrange', 'tempo', 'ramp', 'prison',
}

# Multi-word phrases that are common English but happen to be card names
MULTIWORD_BLOCKLIST = {
    'mirror match', 'wear down', 'game over', 'game plan', 'win condition',
    'card advantage', 'mana curve', 'mana base', 'land destruction',
    'board wipe', 'board state', 'combat damage', 'direct damage',
}



def clean_card_match(name: str) -> str:
    """
    Clean up a raw regex card name match:
    - Strip leading/trailing whitespace and punctuation
    - Remove trailing possessives like 's
    - Preserves internal apostrophes (Urza's Saga, Umezawa's Jitte)
    - Preserves internal commas (Lin Sivvi, Defiant Hero)
    """
    name = name.strip()
    name = re.sub(r"[\s.,;:!?()\[\]]+$", "", name)
    name = re.sub(r"^[\s.,;:!?()\[\]]+", "", name)
    name = re.sub(r"['\u2019]s$", "", name)
    return name.strip()

def is_valid_card_match(name: str) -> bool:
    """
    Return True if a regex card name match should be kept.
    Filters out single-word creature types, set names, common words,
    and known multi-word false positives.
    """
    clean = name.strip()
    lower = clean.lower()

    # Block known multi-word false positives
    if lower in MULTIWORD_BLOCKLIST:
        return False

    words = clean.split()

    # Multi-word (2+): keep unless in multiword blocklist above
    if len(words) >= 2:
        # Also reject if it starts with a lowercase word (not a proper noun)
        if words[0][0].islower():
            return False
        return True

    # Single word: must start uppercase and not be in blocklist
    if not clean[0].isupper():
        return False
    if lower in SINGLE_WORD_BLOCKLIST:
        return False
    return True


def deep_normalise(obj):
    """
    Recursively walk a dict/list structure and normalise all string values —
    replacing Unicode quote variants with plain ASCII apostrophes before
    saving to MongoDB.
    """
    if isinstance(obj, str):
        return normalise_apostrophes(obj)
    if isinstance(obj, list):
        return [deep_normalise(i) for i in obj]
    if isinstance(obj, dict):
        return {k: deep_normalise(v) for k, v in obj.items()}
    return obj

def build_card_pattern(names: set[str]) -> re.Pattern | None:
    """
    Build a single compiled regex that matches any card name as a whole word.
    Sorted longest-first so multi-word names match before partial substrings.
    """
    if not names:
        return None
    sorted_names = sorted(names, key=len, reverse=True)
    # Use the original-cased names for canonical output — store a lookup too
    return re.compile(
        r'\b(' + '|'.join(re.escape(n) for n in sorted_names) + r')\b',
        re.IGNORECASE
    )


def load_card_names() -> set[str]:
    names: set[str] = set()
    try:
        cards_col = client["scryfall"]["all_cards"]
        if cards_col.count_documents({}) > 0:
            for doc in cards_col.find({}, {"name": 1, "_id": 0}):
                if "name" in doc:
                    names.add(normalise_apostrophes(doc["name"]).lower())
            print(f"[*] Loaded {len(names):,} card names from MongoDB 'scryfall.all_cards'")
            return names
        print("[!] MongoDB 'scryfall.all_cards' is empty, trying Scryfall API ...")
    except Exception as e:
        print(f"[!] MongoDB card load failed: {e}")

    try:
        import requests
        r = requests.get(
            "https://api.scryfall.com/catalog/card-names",
            headers={"User-Agent": "MTGScraper/1.0"},
            timeout=15,
        )
        if r.status_code == 200:
            names = {normalise_apostrophes(n).lower() for n in r.json().get("data", [])}
            print(f"[*] Loaded {len(names):,} card names from Scryfall catalog API")
            return names
        print(f"[!] Scryfall API returned {r.status_code}")
    except Exception as e:
        print(f"[!] Scryfall API failed: {e}")

    print("[!] WARNING: No card name list available — card fields will be empty")
    return names


def extract_cards(tag: Tag) -> list[str]:
    """Return card names from wiki links whose text exactly matches a known card."""
    if not CARD_NAMES:
        return []
    seen: set[str] = set()
    cards: list[str] = []
    for a in tag.find_all("a", href=True):
        if not a["href"].startswith("/wiki/"):
            continue
        text = a.get_text(strip=True)
        if normalise_apostrophes(text).lower() in CARD_NAMES and text not in seen:
            seen.add(text)
            cards.append(clean_card_match(text))
    return cards


def extract_cards_from_text(text: str, existing: list[str]) -> list[str]:
    """
    Scan plain text for card name mentions using the compiled regex.
    Skips any names already found via link extraction.
    Returns only the new cards found (deduped, canonical casing).
    """
    if not CARD_PATTERN:
        return []
    if not text:
        return []
    text = normalise_apostrophes(text)
    existing_lower = {normalise_apostrophes(c).lower() for c in existing}
    seen: set[str] = set()
    new_cards: list[str] = []
    for m in CARD_PATTERN.finditer(text):
        matched = m.group()
        key = matched.lower()
        if key not in existing_lower and key not in seen:
            cleaned = clean_card_match(matched)
            if not cleaned or not is_valid_card_match(cleaned):
                continue
            # If cleaning changed the name (e.g. stripped trailing 's),
            # verify the cleaned version is still a real card name
            if normalise_apostrophes(cleaned).lower() != key and                normalise_apostrophes(cleaned).lower() not in CARD_NAMES:
                continue
            seen.add(key)
            new_cards.append(cleaned)
    return new_cards


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ArchetypePage:
    name: str
    url: str
    summary: list[str]                  = field(default_factory=list)
    sections: dict[str, list[str]]      = field(default_factory=dict)
    categories: list[str]               = field(default_factory=list)
    also_see: list[str]                 = field(default_factory=list)
    summary_cards: list[str]            = field(default_factory=list)
    section_cards: dict[str, list[str]] = field(default_factory=dict)
    outbound_links: list[str]           = field(default_factory=list)


def page_to_doc(page: ArchetypePage) -> dict:
    sections_out = []
    all_cards_seen: set[str] = set()
    all_cards: list[str] = []

    for title, paragraphs in page.sections.items():
        section_cards = page.section_cards.get(title, [])
        sections_out.append({
            "title":   title,
            "content": paragraphs,
            "cards":   section_cards,
        })
        for c in section_cards:
            if c not in all_cards_seen:
                all_cards_seen.add(c)
                all_cards.append(c)

    for c in page.summary_cards:
        if c not in all_cards_seen:
            all_cards_seen.add(c)
            all_cards.append(c)

    return {
        "name":       page.name,
        "url":        page.url,
        "archetypes": extract_archetype(page.categories, page.name),
        "summary":    page.summary,
        "sections":   sections_out,
        "cards":      all_cards,
        "categories": page.categories,
        "also_see":   page.also_see,
    }


# ── Selenium ──────────────────────────────────────────────────────────────────

def build_driver() -> WebDriver:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--no-first-run")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    return webdriver.Chrome(options=opts)


def fetch_html(driver: WebDriver, url: str) -> str:
    driver.get(url)
    WebDriverWait(driver, PAGE_LOAD_WAIT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".mw-parser-output"))
    )
    time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))
    return driver.page_source


def fetch_with_retry(url: str, name: str) -> Optional[str]:
    for attempt in range(1, MAX_RETRIES + 1):
        driver = None
        try:
            driver = build_driver()
            html = fetch_html(driver, url)
            driver.quit()
            return html
        except Exception as e:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            print(f"         [!] Attempt {attempt}/{MAX_RETRIES} failed for '{name}': {str(e)[:120]}")
            if attempt < MAX_RETRIES:
                wait = 5 * attempt
                print(f"         [~] Waiting {wait}s before retry ...")
                time.sleep(wait)
    return None


# ── Stage 1: category page ────────────────────────────────────────────────────

# Pages from the category list that aren't actual deck archetypes
CATEGORY_EXCLUDES = {"Archetype", "Direct damage", "Group Hug", "Land destruction"}

def scrape_category_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for container in soup.select(".category-page__members, .mw-category"):
        for a in container.find_all("a", href=True):
            href = a["href"]
            name = a.get_text(strip=True)
            if name in CATEGORY_EXCLUDES:
                continue
            if href.startswith("/wiki/") and ":" not in href.replace("/wiki/", "", 1):
                full_url = BASE_URL + href
                if (name, full_url) not in links:
                    links.append((name, full_url))
    return links


# ── Page parser ───────────────────────────────────────────────────────────────

def is_noise(text: str) -> bool:
    if not text or len(text) < 15:
        return True
    if re.match(r"^(\[\d+\]\s*)+$", text):
        return True
    return False


def clean_text(tag: Tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(separator=" ", strip=True))


def collect_outbound_links(content: Tag) -> list[str]:
    """Collect internal wiki links that look like archetype/deck pages."""
    links = []
    seen: set[str] = set()
    for a in content.find_all("a", href=True):
        href = a["href"]
        if should_follow(href):
            full_url = BASE_URL + href
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
    return links


def scrape_archetype_page(html: str, url: str, name: str) -> ArchetypePage:
    soup = BeautifulSoup(html, "html.parser")
    page = ArchetypePage(name=name, url=url)

    content = soup.select_one(".mw-parser-output")
    if not content:
        return page

    page.outbound_links = collect_outbound_links(content)

    current_section: Optional[str] = None

    for tag in content.children:
        if not isinstance(tag, Tag):
            continue

        tag_classes = " ".join(tag.get("class", []))
        if any(c in tag_classes for c in ("navbox", "toc", "reflist", "references",
                                           "thumb", "infobox", "hatnote")):
            continue
        if tag.get("id") in ("toc", "references"):
            continue

        if tag.name in ("h2", "h3"):
            heading = re.sub(r"\[.*?\]", "", tag.get_text(strip=True)).strip()
            if heading.lower() in ("references", "notes", "external links"):
                break
            current_section = heading
            page.sections.setdefault(current_section, [])

        elif tag.name == "p":
            text = re.sub(r"\[\d+\]", "", clean_text(tag)).strip()
            if is_noise(text):
                continue
            if current_section is None:
                page.summary.append(text)
                link_cards = extract_cards(tag)
                for c in link_cards:
                    if c not in page.summary_cards:
                        page.summary_cards.append(c)
                for c in extract_cards_from_text(text, page.summary_cards):
                    if c not in page.summary_cards:
                        page.summary_cards.append(c)
            else:
                page.sections[current_section].append(text)
                sc = page.section_cards.setdefault(current_section, [])
                link_cards = extract_cards(tag)
                for c in link_cards:
                    if c not in sc:
                        sc.append(c)
                for c in extract_cards_from_text(text, sc):
                    if c not in sc:
                        sc.append(c)

        elif tag.name in ("ul", "ol"):
            if current_section is None:
                continue
            for li in tag.find_all("li", recursive=False):
                text = re.sub(r"\[\d+\]", "", clean_text(li)).strip()
                if not is_noise(text):
                    page.sections[current_section].append(text)
                    sc = page.section_cards.setdefault(current_section, [])
                    for c in extract_cards(li):
                        if c not in sc:
                            sc.append(c)
                    for c in extract_cards_from_text(text, sc):
                        if c not in sc:
                            sc.append(c)

    # Fandom renders categories in several possible locations
    cat_selectors = [
        "#catlinks a",
        ".page-footer__categories a",
        ".categories a",
        "[data-tracking-label='categories'] a",
        ".wds-list a[href*='/wiki/Category:']",
    ]
    seen_cats: set[str] = set()
    for selector in cat_selectors:
        for cat_link in soup.select(selector):
            cat_text = cat_link.get_text(strip=True)
            if cat_text and cat_text.lower() not in ("categories", "community content", "add category") and cat_text not in seen_cats:
                seen_cats.add(cat_text)
                page.categories.append(cat_text)
        if page.categories:
            break  # stop once we find categories from one selector

    # Fallback: derive archetype from page name itself if categories empty
    if not page.categories:
        page_slug = url.split("/wiki/")[-1].lower()
        for keyword in ("aggro", "control", "combo", "midrange", "tempo", "ramp", "prison", "stax"):
            if keyword in page_slug:
                page.categories.append(f"{keyword.title()} deck")

    page.also_see = page.sections.get("See also", [])
    return page


def url_to_name(url: str) -> str:
    return url.split("/wiki/")[-1].replace("_", " ")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global CARD_NAMES, CARD_PATTERN
    CARD_NAMES = load_card_names()
    if CARD_NAMES:
        print("[*] Building card name regex pattern ...")
        CARD_PATTERN = build_card_pattern(CARD_NAMES)
        print(f"[*] Pattern ready ({len(CARD_NAMES):,} card names)")
        print(f"[*] Sample card names in set: {list(CARD_NAMES)[:5]}")
    else:
        print("[!] CARD_NAMES is empty — card extraction disabled\n")

    # ── Seed from category page ───────────────────────────────────────────────
    print(f"\n[*] Fetching category page ...")
    html = fetch_with_retry(CATEGORY_URL, "Category page")
    if not html:
        print("[!] Failed to fetch category page. Aborting.")
        return

    seed_links = scrape_category_links(html)
    print(f"[*] Found {len(seed_links)} seed pages from category\n")

    collection.delete_many({})
    success, failed = 0, []
    visited: set[str] = set()
    level1_urls: set[str] = set()

    # ── L0: scrape category pages ─────────────────────────────────────────────
    for i, (name, url) in enumerate(seed_links, 1):
        visited.add(url)
        print(f"  [L0 {i}/{len(seed_links)}] {name}")

        html = fetch_with_retry(url, name)
        if html is None:
            print(f"         [!] Giving up on '{name}'")
            failed.append(name)
            continue

        page = scrape_archetype_page(html, url, name)
        doc  = deep_normalise(page_to_doc(page))
        collection.insert_one(doc)
        success += 1

        new = [u for u in page.outbound_links if u not in visited]
        level1_urls.update(new)

        total_paras = len(page.summary) + sum(len(v) for v in page.sections.values())
        print(
            f"         archetypes={doc['archetypes']}"
            f"  |  {len(page.summary)} summary paras"
            f"  |  {len(page.sections)} sections"
            f"  |  {total_paras} total paras"
            f"  |  {len(doc['cards'])} cards"
            f"  |  {len(new)} L1 links found"
        )

    print(f"\n[*] L0 done. {len(level1_urls)} unique L1 pages to scrape\n")

    # ── L1: scrape one level deeper, no further recursion ─────────────────────
    level1_list = sorted(level1_urls)
    for i, url in enumerate(level1_list, 1):
        if url in visited:
            continue
        visited.add(url)
        name = url_to_name(url)
        print(f"  [L1 {i}/{len(level1_list)}] {name}")

        html = fetch_with_retry(url, name)
        if html is None:
            print(f"         [!] Giving up on '{name}'")
            failed.append(name)
            continue

        page = scrape_archetype_page(html, url, name)
        doc  = deep_normalise(page_to_doc(page))
        collection.insert_one(doc)
        success += 1

        total_paras = len(page.summary) + sum(len(v) for v in page.sections.values())
        print(
            f"         archetypes={doc['archetypes']}"
            f"  |  {len(page.summary)} summary paras"
            f"  |  {len(page.sections)} sections"
            f"  |  {total_paras} total paras"
            f"  |  {len(doc['cards'])} cards"
        )

    print(f"\n[+] Done: {success} scraped, {len(failed)} failed")
    if failed:
        print(f"    Failed: {failed}")
    print(f"[+] MongoDB '{collection.full_name}' has {collection.count_documents({})} documents")


if __name__ == "__main__":
    main()