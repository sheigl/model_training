"""
MongoDB Inspector - Explore your MTG database structure
This tool helps understand what data you have and how it's structured
"""

from collections import defaultdict
from pymongo import MongoClient
import json
from pprint import pprint


def connect_to_mongo(connection_string='mongodb://server.home:27017/', db_name='mtg_database'):
    """Connect to MongoDB"""
    client = MongoClient(connection_string)
    db = client[db_name]
    return db

def list_collections(db):
    """List all collections in the database"""
    collections = db.list_collection_names()
    print(f"\n{'='*70}")
    print(f"Collections in database '{db.name}':")
    print(f"{'='*70}")
    for i, coll in enumerate(collections, 1):
        count = db[coll].count_documents({})
        print(f"{i}. {coll:30s} - {count:,} documents")
    return collections

def inspect_collection(db, collection_name, num_samples=3):
    """Inspect a collection's structure and data"""
    collection = db[collection_name]
    
    print(f"\n{'='*70}")
    print(f"Collection: {collection_name}")
    print(f"{'='*70}")
    
    # Count
    count = collection.count_documents({})
    print(f"Total documents: {count:,}")
    
    # Get sample documents
    print(f"\n--- Sample Documents ({num_samples}) ---\n")
    samples = list(collection.find().limit(num_samples))
    
    for i, doc in enumerate(samples, 1):
        print(f"\nDocument {i}:")
        print("-" * 70)
        # Pretty print with proper formatting
        print(json.dumps(doc, indent=2, default=str))
    
    # Analyze schema (get all unique keys across documents)
    print(f"\n--- Schema Analysis ---")
    print("Analyzing first 1000 documents for schema...")
    
    all_keys = set()
    key_types = defaultdict(set)
    key_examples = {}
    
    for doc in collection.find().limit(1000):
        for key, value in doc.items():
            all_keys.add(key)
            key_types[key].add(type(value).__name__)
            if key not in key_examples and value is not None:
                # Store a sample value
                if isinstance(value, (str, int, float, bool)):
                    key_examples[key] = value
                elif isinstance(value, list) and len(value) > 0:
                    key_examples[key] = f"[{type(value[0]).__name__}] (length: {len(value)})"
                elif isinstance(value, dict):
                    key_examples[key] = f"{{dict with {len(value)} keys}}"
    
    print(f"\nFound {len(all_keys)} unique fields:\n")
    for key in sorted(all_keys):
        types = ', '.join(sorted(key_types[key]))
        example = key_examples.get(key, 'N/A')
        print(f"  {key:30s} : {types:20s} | Example: {example}")
    
    return samples

def search_collection(db, collection_name, query, limit=5):
    """Search a collection with a query"""
    collection = db[collection_name]
    
    print(f"\n{'='*70}")
    print(f"Search Results: {collection_name}")
    print(f"Query: {query}")
    print(f"{'='*70}")
    
    results = list(collection.find(query).limit(limit))
    print(f"Found {len(results)} results (showing up to {limit})")
    
    for i, doc in enumerate(results, 1):
        print(f"\nResult {i}:")
        print("-" * 70)
        print(json.dumps(doc, indent=2, default=str))
    
    return results

def interactive_mode(db):
    """Interactive exploration mode"""
    print(f"\n{'='*70}")
    print("Interactive MongoDB Explorer")
    print(f"{'='*70}")
    print("\nCommands:")
    print("  list                  - List all collections")
    print("  inspect <collection>  - Inspect a collection's structure")
    print("  sample <collection> <n> - Show n random samples")
    print("  count <collection>    - Count documents")
    print("  search <collection> <field> <value> - Search for documents")
    print("  quit                  - Exit")
    
    while True:
        try:
            command = input("\n> ").strip().split()
            
            if not command:
                continue
            
            cmd = command[0].lower()
            
            if cmd == 'quit':
                break
            
            elif cmd == 'list':
                list_collections(db)
            
            elif cmd == 'inspect' and len(command) >= 2:
                collection_name = command[1]
                num_samples = int(command[2]) if len(command) > 2 else 3
                inspect_collection(db, collection_name, num_samples)
            
            elif cmd == 'sample' and len(command) >= 2:
                collection_name = command[1]
                n = int(command[2]) if len(command) > 2 else 5
                samples = list(db[collection_name].aggregate([{'$sample': {'size': n}}]))
                for i, doc in enumerate(samples, 1):
                    print(f"\nSample {i}:")
                    print(json.dumps(doc, indent=2, default=str))
            
            elif cmd == 'count' and len(command) >= 2:
                collection_name = command[1]
                count = db[collection_name].count_documents({})
                print(f"{collection_name}: {count:,} documents")
            
            elif cmd == 'search' and len(command) >= 4:
                collection_name = command[1]
                field = command[2]
                value = ' '.join(command[3:])
                
                # Try to parse as number if possible
                try:
                    value = int(value)
                except:
                    try:
                        value = float(value)
                    except:
                        pass  # Keep as string
                
                query = {field: value}
                search_collection(db, collection_name, query, limit=5)
            
            else:
                print("Unknown command or missing arguments")
        
        except Exception as e:
            print(f"Error: {e}")

def generate_summary_report(db):
    """Generate a comprehensive summary of the database"""
    print(f"\n{'='*70}")
    print(f"DATABASE SUMMARY REPORT")
    print(f"{'='*70}")
    
    collections = db.list_collection_names()
    
    for coll_name in collections:
        collection = db[coll_name]
        count = collection.count_documents({})
        
        print(f"\n{coll_name}:")
        print(f"  Total documents: {count:,}")
        
        # Get a sample to understand structure
        sample = collection.find_one()
        if sample:
            keys = list(sample.keys())
            print(f"  Fields ({len(keys)}): {', '.join(keys[:10])}")
            if len(keys) > 10:
                print(f"    ... and {len(keys) - 10} more")

def main():
    print("MongoDB Database Inspector for MTG Training Data")
    print("=" * 70)
    
    # Get connection details
    connection_string = input("MongoDB connection string [mongodb://server.home:27017/]: ").strip()
    if not connection_string:
        connection_string = 'mongodb://root:whatever@server.home:27017/'
    
    db_name = input("Database name [mtg_database]: ").strip()
    if not db_name:
        db_name = 'mtg_database'
    
    try:
        db = connect_to_mongo(connection_string, db_name)
        print(f"\n✓ Connected to database: {db_name}")
        
        # Show summary
        generate_summary_report(db)
        
        # Enter interactive mode
        print("\nEntering interactive mode...")
        interactive_mode(db)
        
    except Exception as e:
        print(f"\n✗ Error connecting to MongoDB: {e}")
        print("\nTroubleshooting:")
        print("  1. Is MongoDB running? (systemctl status mongodb)")
        print("  2. Is the connection string correct?")
        print("  3. Does the database exist?")

if __name__ == "__main__":
    main()