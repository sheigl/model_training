"""
EDHRec article scraper for MTG training data
Gets strategic content about cards, archetypes, and gameplay
"""

import argparse
import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime

CACHE_FILE = os.path.join(os.path.dirname(__file__), 'edhrec_articles_cache.json')


def load_cache():
    """Load previously scraped articles from cache file."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        print(f"Loaded {len(data)} articles from cache")
        return data
    return []


def save_cache(articles_data):
    """Save scraped articles to cache file."""
    with open(CACHE_FILE, 'w') as f:
        json.dump(articles_data, f, indent=2)
    print(f"Saved {len(articles_data)} articles to cache ({CACHE_FILE})")


def scrape_edhrec_articles(max_articles=100):
    """
    Scrape EDHRec articles and convert to training format.
    Resumes from cache so already-scraped articles are skipped.
    """
    cached = load_cache()
    cached_urls = {a['url'] for a in cached}
    articles_data = list(cached)

    base_url = "https://edhrec.com/articles"

    print(f"Scraping EDHRec articles (max {max_articles}, {len(cached)} already cached)...")

    if len(articles_data) >= max_articles:
        print(f"Cache already has {len(articles_data)} articles (>= {max_articles}), nothing to scrape.")
        return articles_data[:max_articles]

    try:
        # Get article listing page
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find article links
        article_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/articles/' in href and href not in article_links:
                if not href.startswith('http'):
                    href = 'https://edhrec.com' + href
                article_links.append(href)

        print(f"Found {len(article_links)} article links")

        # Scrape each article, skipping cached ones
        new_count = 0
        for i, article_url in enumerate(article_links):
            if len(articles_data) >= max_articles:
                break

            if article_url in cached_urls:
                continue

            if new_count % 10 == 0 and new_count > 0:
                print(f"Scraped {new_count} new articles so far ({len(articles_data)} total)...")

            try:
                time.sleep(5)  # Be polite
                article_response = requests.get(article_url, timeout=10)
                article_soup = BeautifulSoup(article_response.content, 'html.parser')

                # Extract title
                title_tag = article_soup.find('h2')
                if not title_tag:
                    continue
                title = title_tag.get_text().strip()

                # Extract content paragraphs
                content_divs = article_soup.find_all(['p', 'h2', 'h3'])
                paragraphs = [p.get_text().strip() for p in content_divs if len(p.get_text().strip()) > 50]

                if len(paragraphs) < 3:
                    continue

                article_entry = {
                    'url': article_url,
                    'title': title,
                    'paragraphs': paragraphs
                }
                
                if article_entry in articles_data:
                    continue
                
                articles_data.append(article_entry)
                new_count += 1

                save_cache(articles_data)

            except Exception as e:
                print(f"Error processing {article_url}: {e}")
                continue

        # Final cache save
        if new_count > 0:
            save_cache(articles_data)
            print(f"Scraped {new_count} new articles")

    except Exception as e:
        print(f"Error fetching article list: {e}")
        # Save whatever we have so far
        if len(articles_data) > len(cached):
            save_cache(articles_data)

    return articles_data[:max_articles]

def convert_to_training_format(articles_data):
    """
    Convert scraped articles into Q&A training format
    """
    training_examples = []
    
    for article in articles_data:
        title = article['title']
        paragraphs = article['paragraphs']
        
        # Create various Q&A pairs from the article
        full_text = ' '.join(paragraphs[:5])  # First 5 paragraphs
        
        # Generate questions based on title
        if 'commander' in title.lower() or 'edh' in title.lower():
            questions = [
                f"Tell me about {title}",
                f"What should I know about {title}?",
            ]
        elif 'deck' in title.lower():
            questions = [
                f"How do I build {title}?",
                f"What are some tips for {title}?",
            ]
        elif 'card' in title.lower() or any(word in title.lower() for word in ['best', 'top', 'staple']):
            questions = [
                f"What are {title}?",
                f"Tell me about {title}",
            ]
        else:
            questions = [f"Explain {title}"]
        
        for question in questions:
            training_examples.append({
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": full_text[:1000]}  # Limit length
                ]
            })
    
    return training_examples

def main():
    parser = argparse.ArgumentParser(description="EDHRec Article Scraper for MTG Training Data")
    parser.add_argument('--max-articles', type=int, default=200,
                        help='Maximum number of articles to scrape (default: 200)')
    parser.add_argument('--no-cache', action='store_true',
                        help='Ignore existing cache and scrape from scratch')
    args = parser.parse_args()

    print("EDHRec Article Scraper for MTG Training Data")
    print("=" * 60)

    if args.no_cache and os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print("Cleared existing cache.")

    # Scrape articles
    articles = scrape_edhrec_articles(max_articles=args.max_articles)
    print(f"\nScraped {len(articles)} articles successfully")

    if not articles:
        print("No articles scraped. Check your internet connection or the website structure may have changed.")
        return

    # Convert to training format
    training_data = convert_to_training_format(articles)
    print(f"Generated {len(training_data)} training examples")

    # Save to JSONL
    output_file = 'edhrec_training_data.jsonl'
    with open(output_file, 'w') as f:
        for example in training_data:
            f.write(json.dumps(example) + '\n')

    print(f"\nSaved to {output_file}")
    print(f"Preview of first example:")
    print(json.dumps(training_data[0], indent=2))

if __name__ == "__main__":
    main()
