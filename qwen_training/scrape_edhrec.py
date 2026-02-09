import requests
import json
import time
from pymongo import MongoClient
from datetime import datetime

# Initialize MongoDB connection
client = MongoClient('mongodb://root:whatever@localhost:27017/')  # Adjust connection string as needed
db = client['edhrec']
collection = db['articles']

# Initialize variables
current_page = 2
url = f"https://edhrec.com/_next/data/IG8IvLWsm-Ef5QjOAu2gN/articles/tag/commander/{current_page}.json?tag=commander&page={current_page}"
results = []

while True:
    # Make the API request
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code}")
        break

    # Parse the JSON response
    data = response.json()

    # Add the current page results to our list
    page_results = data.get("pageProps", {}).get("posts", [])
    
    results_len = len(page_results)  # Check the number of results in the current page
    print(f"Fetched {results_len} results from page {current_page}")
    
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
    
    # Check if there are more pages
    if results_len == 0:
        break
    
    current_page += 1
    url = f"https://edhrec.com/_next/data/IG8IvLWsm-Ef5QjOAu2gN/articles/tag/commander/{current_page}.json?tag=commander&page={current_page}"
    
    time.sleep(5)  # Sleep to avoid hitting rate limits