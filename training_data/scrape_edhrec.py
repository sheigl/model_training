from typing import Collection
import requests
import json
import time
from pymongo import MongoClient
from datetime import datetime
from edhrec import EDHRec
from custom_pyedhrec import Custom_EDHRec
import argparse

custom_edhrec = Custom_EDHRec()
edhrec = EDHRec()

# Initialize MongoDB connection
client = MongoClient('mongodb://root:whatever@server.home:27017/')  # Adjust connection string as needed
db = client['edhrec']


def get_guides_first_page():
    guides_collection = db['guides']
    
    page1_guides, guides_status = custom_edhrec.get_next_data("https://edhrec.com/guides")
    
    if guides_status == 200:
        guides = page1_guides.get("props", {}).get("pageProps", {}).get("posts", [])
        print(f"Got {len(guides)} guides from the first page")
        save(guides, guides_collection)

def get_articles_first_page():
    article_collection = db['articles']
    page1_articles, articles_status = custom_edhrec.get_next_data("https://edhrec.com/articles")

    if articles_status == 200:
        articles = page1_articles.get("props", {}).get("pageProps", {}).get("posts", [])
        print(f"Got {len(articles)} articles from the first page")
        save(articles, article_collection)

def get_top_first_page(uri: str, top_card_type: str = "commanders"):
    collection = db[top_card_type]
    page1_data, status_code = custom_edhrec.get_next_data(uri)
    
    if status_code == 200:
        card_lists = page1_data.get("props", {}).get("pageProps", {}).get("data", {}).get("container", {}).get("json_dict", {}).get("cardlists", [])
        
        for card_list in card_lists:
            first_page_cards = card_list.get("cardviews", [])
            print(f"Got {len(first_page_cards)} {card_list.get('header')} cards from the first page")
            
            for first_page_card in first_page_cards:
                if collection.find_one({"sanitized": first_page_card.get("sanitized")}):
                    print(f"{first_page_card.get('name')} already exists in the {top_card_type}, skipping.")
                    continue
                
                card_data, card_status_code = custom_edhrec.get(f"https://json.edhrec.com/cards/{first_page_card.get('sanitized')}")
                
                if card_status_code != 200:
                    continue
                
                print(f"[{card_list.get('header') or top_card_type}] Saving card: {first_page_card.get('name')}")
                
                card_to_save = {
                    "rank": first_page_card.get("rank"),
                    "name": first_page_card.get("name"),
                    "sanitized": first_page_card.get("sanitized"),
                    "color_identity": card_data.get("color_identity"),
                    "game_changer": card_data.get("game_changer"),
                    "num_decks": first_page_card.get("num_decks"),
                    "banned": card_data.get("banned"),
                    "inclusion": first_page_card.get("inclusion"),
                    "oracle_id": card_data.get("oracle_id"),
                    "oracle_text": card_data.get("oracle_text"),
                    "mana_cost": card_data.get("mana_cost"),
                    "power": card_data.get("power"),
                    "toughness": card_data.get("toughness"),
                    "type": card_data.get("type"),
                    "primary_type": card_data.get("primary_type"),
                    "tags": card_data.get("tags"),
                    "rarity": card_data.get("rarity"),
                    "salt": card_data.get("salt"),
                    "subtypes": card_data.get("subtypes"),
                    "types": card_data.get("types")
                }
                
                collection.insert_one(card_to_save)
                
                time.sleep(1)  # Sleep to avoid hitting rate limits
        
def get_top_cards(uri_template: str, card_type: str = "commanders"):
    count = 1   
    
    while True:
        print(f"Fetching cards from page {count}...")
        uri = uri_template.format(page=count)
        status_code = get_card_details_from_uri(uri, card_type)
        
        if status_code != 200:
            print(f"No more cards found at page {count}, stopping.")
            break
    
        print(f"Got cards from page {count}")
        count += 1
        
        time.sleep(1)  # Sleep to avoid hitting rate limits    
    
def get_card_details_from_uri(uri: str, card_type: str) -> int:
    uri_data, status_code = custom_edhrec.get(uri)
    collection = db[card_type]
    
    if status_code != 200:
        print(f"Failed to fetch card data: {status_code}")
        return status_code
    
    data = uri_data.get("cardviews", [])
    
    for card in data:
        if collection.find_one({"sanitized": card.get("sanitized")}):
            print(f"Card {card.get('name')} already exists in the database, skipping.")
            continue
        
        print(f"Saving: {card.get('name')}")
        card_detail_data, card_status_code = custom_edhrec.get(f"https://json.edhrec.com/cards/{card.get('sanitized')}")
            
        if card_status_code != 200:
            continue
        
        collection.insert_one({
                "rank": card.get("rank"),
                "name": card.get("name"),
                "sanitized": card.get("sanitized"),
                "color_identity": card_detail_data.get("color_identity"),
                "game_changer": card_detail_data.get("game_changer"),
                "num_decks": card.get("num_decks"),
                "banned": card_detail_data.get("banned"),
                "inclusion": card.get("inclusion"),
                "oracle_id": card_detail_data.get("oracle_id"),
                "oracle_text": card_detail_data.get("oracle_text"),
                "mana_cost": card_detail_data.get("mana_cost"),
                "power": card_detail_data.get("power"),
                "toughness": card_detail_data.get("toughness"),
                "type": card_detail_data.get("type"),
                "primary_type": card_detail_data.get("primary_type"),
                "tags": card_detail_data.get("tags"),
                "rarity": card_detail_data.get("rarity"),
                "salt": card_detail_data.get("salt"),
                "subtypes": card_detail_data.get("subtypes"),
                "types": card_detail_data.get("types")
            })
        
        time.sleep(1)  # Sleep to avoid hitting rate limits
    
    return status_code
    

def get_guides():
    get_guides_first_page()
    collection = db['guides']
    current_page = 2
    results = []
    while True:
        articles, status_code = custom_edhrec.get_guides(page_number=current_page)    

        # Check if the request was successful
        if status_code != 200:
            print(f"Failed to fetch data: {status_code}")
            break

        # Add the current page results to our list
        page_results = articles
        
        results_len = len(page_results)  # Check the number of results in the current page
        print(f"Fetched {results_len} results from page {current_page} of guides")
        
        save(page_results=page_results, collection=collection)

        # Check if there are more pages
        if results_len == 0:
            break
        
        current_page += 1
        
        time.sleep(5)  # Sleep to avoid hitting rate limits
        
def get_articles():
    get_articles_first_page()
    collection = db['articles']
    current_page = 2
    results = []
    while True:
        articles, status_code = custom_edhrec.get_articles(page_number=current_page, tag="commander")    

        # Check if the request was successful
        if status_code != 200:
            print(f"Failed to fetch data: {status_code}")
            break

        # Add the current page results to our list
        page_results = articles
        
        results_len = len(page_results)  # Check the number of results in the current page
        print(f"Fetched {results_len} results from page {current_page} of articles")
        
        save(page_results=page_results, collection=collection)
        
        # Check if there are more pages
        if results_len == 0:
            break
        
        current_page += 1
        
        time.sleep(5)  # Sleep to avoid hitting rate limits
        
def save(page_results: dict, collection: Collection):
    # Check for duplicates before inserting
    if page_results:
        # Create a set of existing IDs to check against
        existing_ids = set()
        for doc in collection.find({}, {"databaseId": 1}):
            existing_ids.add(doc.get("databaseId"))
        
        # Filter out duplicates
        unique_results = [result for result in page_results if result.get("databaseId") not in existing_ids]
        
        if unique_results:
            # Insert unique documents
            collection.insert_many(unique_results)
            print(f"Inserted {len(unique_results)} new documents")
        else:
            print("No new documents to insert")

def main():
    parser = argparse.ArgumentParser(description="Scrape EDHREC data and store it in MongoDB")
    parser.add_argument("--guides", action="store_true", help="Scrape guides from EDHREC")
    parser.add_argument("--articles", action="store_true", help="Scrape articles from EDHREC")
    parser.add_argument("--commanders", action="store_true", help="Scrape top commanders from EDHREC")
    parser.add_argument("--game-changers", action="store_true", help="Scrape game changers from EDHREC")
    parser.add_argument("--top-by-color", default=None, help="Scrape top cards by color identity from EDHREC (e.g. --top-by-color blue)")
    parser.add_argument("--top-by-type", default=None, help="Scrape top cards by card type from EDHREC (e.g. --top-by-type creatures)")

    args = parser.parse_args()

    if args.guides:
        get_guides()
    
    if args.articles:
        get_articles()
        
    if args.commanders:
        get_top_first_page(f"https://edhrec.com/commanders", "commanders")
        get_top_cards("https://json.edhrec.com/pages/commanders/year-past2years-{page}.json", "commanders")
    
    if args.game_changers:
        get_top_first_page(f"https://edhrec.com/top/game-changers", "game-changers")
        
    if args.top_by_color:
        color = args.top_by_color.lower()
        get_top_first_page(f"https://edhrec.com/top/{color}", f"top-{color}")
        get_top_cards(f"https://json.edhrec.com/pages/top/{color}-year-past2years-{{page}}.json", f"top-{color}")
        
    if args.top_by_type:
        card_type = args.top_by_type.lower()
        get_top_first_page(f"https://edhrec.com/top/{card_type}", f"top-{card_type}")
        get_top_cards(f"https://json.edhrec.com/pages/top/{card_type}-top{card_type}-{{page}}.json", f"top-{card_type}")
    
if __name__ == "__main__":
    main()