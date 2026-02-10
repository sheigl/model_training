from typing import Collection
import requests
import json
import time
from pymongo import MongoClient
from datetime import datetime
from pyedhrec import EDHRec
from custom_pyedhrec import Custom_EDHRec

custom_edhrec = Custom_EDHRec()

# TODO get other items from EDHRec
#edhrec = EDHRec()

# Initialize MongoDB connection
client = MongoClient('mongodb://root:whatever@localhost:27017/')  # Adjust connection string as needed
db = client['edhrec']

def get_guides():
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

def get_first_pages():
    article_collection = db['articles']
    guides_collection = db['guides']
    
    page1_articles, articles_status = custom_edhrec.get_next_data("https://edhrec.com/articles")
    page1_guides, guides_status = custom_edhrec.get_next_data("https://edhrec.com/guides")
    
    if articles_status == 200:
        articles = page1_articles.get("props", {}).get("pageProps", {}).get("posts", [])
        print(f"Got {len(articles)} articles from the first page")
        save(articles, article_collection)
    
    if guides_status == 200:
        guides = page1_guides.get("props", {}).get("pageProps", {}).get("posts", [])
        print(f"Got {len(guides)} guides from the first page")
        save(guides, guides_collection)


def get_articles():
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

get_first_pages()      
get_guides()
get_articles()