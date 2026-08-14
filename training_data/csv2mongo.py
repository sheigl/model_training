from pymongo import MongoClient
import os
import csv
import json

# Initialize MongoDB connection
client = MongoClient('mongodb://root:whatever@server.home:27017/')  # Adjust connection string as needed
db = client['mtg_json']

csvFiles = os.listdir('/home/sheigl/code/model_training/training_data/AllPrintingsCSVFiles')  # List files in the data directory
csvFiles = [f for f in csvFiles if f.endswith('.csv')]  # Filter for CSV files

for csvFile in csvFiles:
    print(f"Processing file: {csvFile}")
    collection = db[csvFile.replace('.csv', '')]  # Use the filename (without .csv) as the collection name
    with open(f'/home/sheigl/code/model_training/training_data/AllPrintingsCSVFiles/{csvFile}', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert the row to a JSON document
            json_doc = json.loads(json.dumps(row))  # Convert to JSON and back to ensure proper formatting
            # Insert the document into MongoDB
            print(f"Inserting document {json_doc}")
            collection.insert_one(json_doc)