#!/usr/bin/env python3
"""
Deduplication script for synthetic_queries.queries collection.

Finds all duplicate (question, answer) pairs and removes all but the
oldest copy of each, preserving the original insertion order.

Run once to clean up, then the updated generate_synthetic_to_mongo.py
will prevent future duplicates via upsert logic.
"""

from pymongo import MongoClient
from bson import ObjectId
import argparse


def dedup_synthetic_queries(uri, username, password, dry_run=False):
    client = MongoClient(uri, username=username, password=password, authSource='admin')
    collection = client['synthetic_queries']['queries']

    print("="*60)
    print("SYNTHETIC QUERIES DEDUPLICATION")
    print("="*60)

    total_before = collection.count_documents({})
    print(f"\nTotal documents before: {total_before:,}")

    # Find duplicate (question, answer) pairs
    # Keep the first inserted (_id sorts ascending by default in ObjectId)
    print("\nFinding duplicates...")

    pipeline = [
        {'$group': {
            '_id': {'question': '$question', 'answer': '$answer'},
            'ids': {'$push': '$_id'},
            'count': {'$sum': 1},
            'first_id': {'$min': '$_id'}   # ObjectId is time-ordered — keep oldest
        }},
        {'$match': {'count': {'$gt': 1}}}
    ]

    duplicates = list(collection.aggregate(pipeline, allowDiskUse=True))
    print(f"Found {len(duplicates):,} question/answer pairs with duplicates")

    if not duplicates:
        print("\n✅ No duplicates found — collection is clean!")
        return

    # Collect IDs to delete (all except the first/oldest for each group)
    ids_to_delete = []
    total_dupes = 0
    for group in duplicates:
        keep_id = group['first_id']
        remove_ids = [id_ for id_ in group['ids'] if id_ != keep_id]
        ids_to_delete.extend(remove_ids)
        total_dupes += len(remove_ids)

    print(f"Duplicate documents to remove: {total_dupes:,}")
    print(f"Documents to keep:             {total_before - total_dupes:,}")

    # Category breakdown of what will be removed
    print("\nDuplicates by category:")
    cat_pipeline = [
        {'$match': {'_id': {'$in': ids_to_delete}}},
        {'$group': {'_id': '$category', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    cat_breakdown = list(collection.aggregate(cat_pipeline))
    for cat in cat_breakdown:
        print(f"  {cat['_id'] or 'unknown':35s}: {cat['count']:,}")

    if dry_run:
        print(f"\n[DRY RUN] Would delete {total_dupes:,} documents. Rerun without --dry-run to proceed.")
        return

    # Delete in batches to avoid hitting document size limits
    print(f"\nDeleting {total_dupes:,} duplicate documents...")
    batch_size = 1000
    deleted_total = 0

    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i:i + batch_size]
        result = collection.delete_many({'_id': {'$in': batch}})
        deleted_total += result.deleted_count
        print(f"  → Deleted {deleted_total:,}/{total_dupes:,}...")

    total_after = collection.count_documents({})
    print(f"\n{'='*60}")
    print(f"✅ DEDUPLICATION COMPLETE")
    print(f"{'='*60}")
    print(f"Before: {total_before:,}")
    print(f"After:  {total_after:,}")
    print(f"Removed: {total_before - total_after:,} duplicates")


def main():
    parser = argparse.ArgumentParser(description='Deduplicate synthetic_queries.queries collection')
    parser.add_argument('--mongo-uri', default='mongodb://server.home:27017/')
    parser.add_argument('--mongo-user', default='root')
    parser.add_argument('--mongo-pass', default='whatever')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be deleted without deleting')
    args = parser.parse_args()

    dedup_synthetic_queries(args.mongo_uri, args.mongo_user, args.mongo_pass, args.dry_run)


if __name__ == "__main__":
    main()
