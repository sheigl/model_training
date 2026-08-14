"""
Scraper for FunTrivia quiz data.

Fetches FunTrivia quiz pages, extracts questions, multiple-choice answers,
and correct answers (via their internal API), and stores them in MongoDB.

Usage:
    # Scrape specific quiz URLs
    python scrape_funtrivia.py URL [URL ...]

    # Crawl an entire category/subcategory
    python scrape_funtrivia.py --crawl URL [--max-pages N] [--max-quizzes N]
    python scrape_funtrivia.py --crawl https://www.funtrivia.com/quizzes/hobbies/index.html
    python scrape_funtrivia.py --crawl https://www.funtrivia.com/quizzes/hobbies/games__toys.html

Requires:
    pip install pymongo
"""

import re
import time
import base64
import json
import random
import sys
import urllib.request
import http.cookiejar
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

from pymongo import MongoClient

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URIS = [
    'mongodb://root:whatever@server.home:27017/',
    'mongodb://root:whatever@172.25.5.3:27017/',
]
client     = None
db         = None
collection = None


def connect_mongo():
    global client, db, collection
    for uri in MONGO_URIS:
        try:
            c = MongoClient(uri, serverSelectionTimeoutMS=3000)
            c.server_info()
            client = c
            db = client['funtrivia']
            collection = db['quizzes']
            print(f"[*] Connected to MongoDB at {uri}", flush=True)
            return
        except Exception:
            continue
    print("[!] WARNING: Could not connect to MongoDB. Data will be saved as JSON.", flush=True)
# ── Config ────────────────────────────────────────────────────────────────────
PAGE_DELAY_MIN = 1.0
PAGE_DELAY_MAX = 3.0
MAX_RETRIES    = 3
CHROME_UA      = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# ─────────────────────────────────────────────────────────────────────────────

BASE_DOMAIN = "https://www.funtrivia.com"

QUIZ_URL_RE = re.compile(r'/trivia-quiz/[^"]+-(\d+)\.html')
QUIZ_URL_RE2 = re.compile(r'/quiz/[^"]+-(\d+)\.html')


@dataclass
class QuizQuestion:
    number: int
    text: str
    qtype: int
    choices: list[str] = field(default_factory=list)
    correct_answer: str = ""
    acceptable_answers: list[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class Quiz:
    quiz_id: int
    url: str
    title: str
    author: str
    category: str
    intro: str
    questions: list[QuizQuestion] = field(default_factory=list)


def extract_quiz_id(url: str) -> Optional[int]:
    m = re.search(r'-(\d+)\.html$', url)
    if m:
        return int(m.group(1))
    return None


def _build_opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj)
    )
    return opener, cj


def _fetch(url: str, referer: str = "", label: str = "") -> Optional[str]:
    payload = {
        "url": url,
        "magic": True,
        "summarize": False,
        "timeout": 30
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            "http://server.home:8111/fetch",
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode('utf-8'))
        # The Browse API returns a JSON object. Prefer raw HTML if available,
        # otherwise fall back to the "content" field (markdown or text).
        content = result.get("html") or result.get("content") or result.get("markdown", "")
        if not content:
            print(f"  [!] Browse API returned empty content for '{label or url}'")
            return None
        return content
    except urllib.error.HTTPError as e:
        print(f"  [!] Browse API error for '{label or url}': HTTP {e.code} {e.reason}")
        return None
    except Exception as e:
        print(f"  [!] Browse API error for '{label or url}': {str(e)[:100]}")
        return None


def _fetch_with_retry(url: str, referer: str = "", label: str = "") -> Optional[str]:
    for attempt in range(1, MAX_RETRIES + 1):
        result = _fetch(url, referer=referer, label=label)
        if result is not None:
            return result
        if attempt < MAX_RETRIES:
            print(f"  [!] Retrying {label or url} in {3 * attempt}s ...")
            time.sleep(3 * attempt)
    print(f"  [!] All retries exhausted for '{label or url}'")
    return None


def _fetch_raw(url: str, opener, referer: str = "", label: str = "") -> Optional[str]:
    """Fetch raw HTML/JSON directly via urllib (for embed page and internal API)."""
    headers = {'User-Agent': CHROME_UA}
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = opener.open(req, timeout=15)
            return resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            status = e.code
            reason = e.reason
            print(f"  [!] Attempt {attempt}/{MAX_RETRIES} for '{label or url}': HTTP {status} {reason}")
            if attempt < MAX_RETRIES:
                time.sleep(3 * attempt)
        except Exception as e:
            print(f"  [!] Attempt {attempt}/{MAX_RETRIES} for '{label or url}': {str(e)[:100]}")
            if attempt < MAX_RETRIES:
                time.sleep(3 * attempt)
    return None


def scrape_quiz(url: str) -> Optional[Quiz]:
    quiz_id = extract_quiz_id(url)
    if not quiz_id:
        print(f"  [!] Could not extract quiz ID from URL: {url}")
        return None

    print(f"\n  Scraping quiz ID {quiz_id} ...")

    opener, cj = _build_opener()

    # Fetch main page via Browse API (markdown)
    md = _fetch_with_retry(url, label="main page")
    if not md:
        print(f"  [!] Failed to fetch main page via Browse API after all retries (see errors above)")
        return None

    # The quiz ID from the URL is the same as the embed qid
    embed_url = f'{BASE_DOMAIN}/html5/embedquiz.cfm?qid={quiz_id}'
    
    # Fetch embed page via raw HTTP (needs HTML with JavaScript)
    embed_html = _fetch_raw(embed_url, opener, referer=url, label="embed page")
    if not embed_html:
        print(f"  [!] Failed to fetch embed page via direct HTTP after all retries (see errors above)")
        return None

    mgr = re.search(r'Manager\((\d+),"([^"]+)","([^"]+)"\)', embed_html)
    if not mgr:
        snippet = embed_html[:300].replace('\n', ' ')
        print(f"  [!] Could not find Manager() call in embed page")
        print(f"      Content length: {len(embed_html)} chars")
        print(f"      Snippet: {snippet}...")
        return None

    qid, pts, skey = mgr.groups()
    qid = int(qid)

    bust = int(time.time() / 10)
    api_url = f'{BASE_DOMAIN}/qserver2.cfm?timed=1&qid={qid}&skey={skey}&bust={bust}'
    
    # Fetch internal API via raw HTTP (needs JSON response)
    api_json = _fetch_raw(api_url, opener, referer=embed_url, label="quiz API")
    if not api_json:
        print(f"  [!] Failed to fetch quiz API data via direct HTTP")
        print(f"      URL: {api_url}")
        return None

    try:
        data = json.loads(api_json)
    except json.JSONDecodeError as e:
        print(f"  [!] API response not valid JSON: {e}")
        print(f"      Response: {api_json[:200]}")
        return None

    quiz = Quiz(
        quiz_id=qid,
        url=url,
        title=data.get('title', ''),
        author=data.get('author', ''),
        category=data.get('category', ''),
        intro=data.get('intro', ''),
    )

    for q_data in data.get('questions', []):
        qtype = q_data.get('qtype', 1)
        qnum = q_data.get('qnum', 0)
        qanswer_b64 = q_data.get('qanswer', '')

        q = QuizQuestion(
            number=qnum,
            text=q_data.get('qtext', ''),
            qtype=qtype,
            explanation=q_data.get('qinfo', ''),
        )

        if qtype >= 1:
            q.choices = q_data.get('qchoices', [])
            if qanswer_b64:
                try:
                    q.correct_answer = base64.b64decode(qanswer_b64).decode('utf-8')
                except Exception:
                    q.correct_answer = str(qanswer_b64)
        else:
            if isinstance(qanswer_b64, list):
                for ans_b64 in qanswer_b64:
                    try:
                        q.acceptable_answers.append(base64.b64decode(ans_b64).decode('utf-8'))
                    except Exception:
                        q.acceptable_answers.append(str(ans_b64))
                if q.acceptable_answers:
                    q.correct_answer = q.acceptable_answers[0]
            elif qanswer_b64:
                try:
                    decoded = base64.b64decode(qanswer_b64).decode('utf-8')
                    q.acceptable_answers = [a.strip() for a in decoded.split('&')]
                    q.correct_answer = q.acceptable_answers[0] if q.acceptable_answers else ""
                except Exception:
                    pass

        quiz.questions.append(q)

    return quiz


def quiz_to_doc(quiz: Quiz) -> dict:
    questions_out = []
    for q in quiz.questions:
        qd = {
            "number":    q.number,
            "text":      q.text,
            "type":      "multiple_choice" if q.qtype >= 1 else "fill_in_blank",
            "choices":   q.choices,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
        }
        if q.acceptable_answers:
            qd["acceptable_answers"] = q.acceptable_answers
        questions_out.append(qd)

    return {
        "quiz_id":    quiz.quiz_id,
        "url":        quiz.url,
        "title":      quiz.title,
        "author":     quiz.author,
        "category":   quiz.category,
        "intro":      quiz.intro,
        "questions":  questions_out,
    }


# ── Crawling ──────────────────────────────────────────────────────────────────

def is_category_page(url: str) -> bool:
    return url.rstrip('/').endswith('/index.html') or '/quizzes/' in url and url.count('/') == 5


def _category_prefix(url: str) -> str:
    """Extract the category prefix path from a quizzes URL.
    e.g. /quizzes/hobbies/games__toys.html -> /quizzes/hobbies/
    """
    path = urlparse(url).path
    parts = path.strip('/').split('/')
    # /quizzes/{category}/... -> keep /quizzes/{category}/
    if len(parts) >= 2 and parts[0] == 'quizzes':
        return '/' + '/'.join(parts[:2]) + '/'
    return '/' + '/'.join(parts[:1]) + '/'


def extract_subcategory_urls(md: str, base_url: str) -> list[str]:
    """Extract subcategory URLs from markdown (Browse API output)."""
    prefix = _category_prefix(base_url)
    urls = set()
    # Match markdown links: [text](url)
    for m in re.finditer(r'\[([^\]]+)\]\((https://www\.funtrivia\.com/quizzes/[^)]+)\)', md):
        full = m.group(2)
        href = urlparse(full).path
        if full == base_url:
            continue
        # Only follow links under the same category prefix
        if href.startswith(prefix) and href.count('/') >= 3:
            urls.add(full)
    return sorted(urls)


def extract_quiz_urls(md: str) -> list[str]:
    """Extract quiz URLs from markdown (Browse API output)."""
    urls = {}
    # Match markdown links: [text](https://www.funtrivia.com/trivia-quiz/...)
    for m in re.finditer(r'\[([^\]]+)\]\((https://www\.funtrivia\.com/trivia-quiz/[^)]+)\)', md):
        url = m.group(2)
        qid = extract_quiz_id(url)
        if qid:
            urls[str(qid)] = url
    for m in re.finditer(r'\[([^\]]+)\]\((https://www\.funtrivia\.com/quiz/[^)]+)\)', md):
        url = m.group(2)
        qid = extract_quiz_id(url)
        if qid:
            urls[str(qid)] = url
    return list(urls.values())


def crawl_quiz_urls(start_url: str, max_pages: int = 0, max_quizzes: int = 0) -> list[str]:
    """Walk category/subcategory pages and collect all unique quiz URLs."""
    visited_pages = set()
    quiz_urls = {}
    to_visit = [start_url]

    while to_visit:
        if max_pages > 0 and len(visited_pages) >= max_pages:
            print(f"  [crawl] Reached max pages ({max_pages})")
            break

        page_url = to_visit.pop(0)
        if page_url in visited_pages:
            continue
        visited_pages.add(page_url)

        print(f"  [page {len(visited_pages)}] {page_url}")
        md = _fetch_with_retry(page_url, label=f"page {len(visited_pages)}")
        if not md:
            continue

        new_quizzes = 0
        for url in extract_quiz_urls(md):
            qid = extract_quiz_id(url)
            if qid and qid not in quiz_urls:
                quiz_urls[qid] = url
                new_quizzes += 1

        if new_quizzes > 0:
            print(f"         -> {new_quizzes} new quizzes (total: {len(quiz_urls)})")
        else:
            print(f"         -> no new quizzes")

        if max_quizzes > 0 and len(quiz_urls) >= max_quizzes:
            print(f"  [crawl] Reached max quizzes ({max_quizzes})")
            break

        # Extract subcategory links and queue them
        subcats = extract_subcategory_urls(md, page_url)
        for sc in subcats:
            if sc not in visited_pages and sc not in to_visit:
                to_visit.append(sc)

        time.sleep(random.uniform(0.5, 1.5))

    print(f"\n  [crawl] Found {len(quiz_urls)} unique quizzes across {len(visited_pages)} pages")
    return list(quiz_urls.values())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Parse arguments
    crawl_mode = False
    max_pages = 0
    max_quizzes = 0
    args = sys.argv[1:]

    if '--crawl' in args:
        crawl_mode = True
        args.remove('--crawl')

    if '--max-pages' in args:
        idx = args.index('--max-pages')
        try:
            max_pages = int(args[idx + 1])
            del args[idx:idx + 2]
        except (ValueError, IndexError):
            print("[!] --max-pages requires a number")
            sys.exit(1)

    if '--max-quizzes' in args:
        idx = args.index('--max-quizzes')
        try:
            max_quizzes = int(args[idx + 1])
            del args[idx:idx + 2]
        except (ValueError, IndexError):
            print("[!] --max-quizzes requires a number")
            sys.exit(1)

    urls = args if args else [
        "https://www.funtrivia.com/trivia-quiz/Hobbies/Basics-of-Magic-The-Gathering-318343.html",
    ]

    if crawl_mode and not urls:
        print("[!] --crawl requires a URL")
        print("  python scrape_funtrivia.py --crawl CATEGORY_URL")
        sys.exit(1)

    connect_mongo()

    if crawl_mode:
        all_quiz_urls = []
        for start in urls:
            found = crawl_quiz_urls(start, max_pages=max_pages, max_quizzes=max_quizzes)
            all_quiz_urls.extend(found)
        if not all_quiz_urls:
            print("[!] No quizzes found")
            return
        print(f"\n[*] Scraping {len(all_quiz_urls)} quizzes...")
        scrape_targets = all_quiz_urls
    else:
        scrape_targets = urls

    success, failed = 0, []
    results = []
    for i, url in enumerate(scrape_targets, 1):
        print(f"\n--- [{i}/{len(scrape_targets)}] ---")
        quiz = scrape_quiz(url)
        if quiz is None:
            failed.append(url)
            continue

        doc = quiz_to_doc(quiz)
        results.append(doc)

        if collection is not None:
            collection.update_one(
                {"quiz_id": quiz.quiz_id},
                {"$set": doc},
                upsert=True,
            )
            print(f"  [+] Saved to MongoDB '{collection.full_name}' (incremental)")

        success += 1

        q_types = {}
        for q in quiz.questions:
            t = "mc" if q.qtype >= 1 else "fitb"
            q_types[t] = q_types.get(t, 0) + 1

        dest = f"MongoDB '{collection.full_name}'" if collection is not None else "JSON output"
        print(f"  ✓ '{quiz.title}' by {quiz.author} — "
              f"{len(quiz.questions)} questions "
              f"({q_types.get('mc', 0)} MC, {q_types.get('fitb', 0)} FITB) "
              f"→ {dest}")

        if len(scrape_targets) > 1:
            delay = random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)
            print(f"  [~] Waiting {delay:.1f}s before next ...")
            time.sleep(delay)

    if collection is None and results:
        out_file = "funtrivia_quizzes.jsonl"
        with open(out_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[*] MongoDB unavailable — saved {len(results)} quizzes to {out_file}")

    print(f"\n[+] Done: {success} scraped, {len(failed)} failed")
    if failed:
        print(f"    Failed URLs: {failed}")


if __name__ == "__main__":
    main()
