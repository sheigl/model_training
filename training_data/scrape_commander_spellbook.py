import requests
import json
import time
from pymongo import MongoClient
from datetime import datetime

# Initialize MongoDB connection
client = MongoClient('mongodb://root:whatever@server.home:27017/')  # Adjust connection string as needed
db = client['commander_spellbook']
collection = db['variants']

# Initialize variables
url = "https://backend.commanderspellbook.com/variants"
results = []
next_url = url

# Loop through all pages of results
while next_url:
    # Make the API request
    response = requests.get(next_url)

    # Check if the request was successful
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code}")
        break

    # Parse the JSON response
    data = response.json()

    # Add the current page results to our list
    page_results = data.get("results", [])
    
    results_len = len(page_results)  # Check the number of results in the current page
    print(f"Fetched {results_len} results from {next_url}")
    
    # Check for duplicates before inserting
    if page_results:
        # Create a set of existing IDs to check against
        existing_ids = set()
        for doc in collection.find({}, {"id": 1}):
            existing_ids.add(doc.get("id"))
        
        # Filter out duplicates
        unique_results = [result for result in page_results if result.get("id") not in existing_ids]
        
        if unique_results:
            # Insert unique documents
            collection.insert_many(unique_results)
            print(f"Inserted {len(unique_results)} new documents")
        else:
            print("No new documents to insert")
    
    # Update next_url for pagination
    next_url = data.get("next")
    
    time.sleep(5)  # Sleep to avoid hitting rate limits

# Get total count from MongoDB
total_count = collection.count_documents({})
print(f"Scraping complete. Total documents in MongoDB: {total_count}")
