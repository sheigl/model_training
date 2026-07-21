#!/usr/bin/env python3
"""
Batch post-hoc validator for synthetic queries.

Reads unvalidated documents from MongoDB (validated=false, needs_review=true),
runs them through the validator, and updates or deletes based on score.

Usage:
    cd /home/sheigl/code/model_training/training_data/generate_synthetic_data
    ../../.venv/bin/python batch_validate.py --category combo_query --min-score 7 --delete-failures

    # Dry-run to see what would be validated
    ../../.venv/bin/python batch_validate.py --category combo_query --dry-run

    # Validate all unvalidated docs regardless of category
    ../../.venv/bin/python batch_validate.py --min-score 7
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

# Add the generator package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymongo import MongoClient
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from query_model import QueryModel
from common import build_context
from models import Model, ModelType, ModelProvider

console = Console()


def get_unvalidated_docs(collection, category=None, limit=0):
    """Fetch unvalidated docs that need review."""
    query = {"validated": False, "needs_review": True}
    if category:
        query["category"] = category

    cursor = collection.find(query)
    if limit > 0:
        cursor = cursor.limit(limit)

    return list(cursor)


def parse_model_string(model_str: str) -> Model:
    """Parse model connection string: url,provider,name"""
    parts = model_str.split(",")
    if len(parts) == 3:
        url, provider, name = parts
    elif len(parts) == 2:
        url, name = parts
        provider = "ollama"
    else:
        url = "http://localhost:11434"
        provider = "ollama"
        name = model_str

    provider_enum = ModelProvider(provider.lower())
    return Model(name=name, type=ModelType.VALIDATION, provider=provider_enum, provider_url=url)


def update_doc(collection, doc, is_valid, score, reason, suggested_fix, validation_model=None):
    """Update MongoDB document with validation results."""
    update_fields = {
        "validated": is_valid,
        "needs_review": False,
        "validation_score": score if score is not None else 0,
        "validation_reason": reason if reason else None,
        "suggested_fix": suggested_fix if suggested_fix and not is_valid else None,
        "validation_model": validation_model,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    collection.update_one({"_id": doc["_id"]}, {"$set": update_fields})


def delete_doc(collection, doc):
    """Remove failed document from collection."""
    collection.delete_one({"_id": doc["_id"]})


def main():
    parser = argparse.ArgumentParser(description="Batch validate synthetic queries")
    parser.add_argument("--category", type=str, default=None, help="Filter by category (e.g., combo_query)")
    parser.add_argument("--min-score", type=int, default=7, help="Minimum validator score to accept (default: 7)")
    parser.add_argument("--limit", type=int, default=0, help="Max docs to process (0 = unlimited)")
    parser.add_argument("--delete-failures", action="store_true", help="Delete docs that fail validation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without validating")
    parser.add_argument("--model", type=str, default="http://localhost:8080/v1,openai,qwen3.6:27b",
                        help="Validation model connection string")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://admin:password@localhost:27017/",
                        help="MongoDB connection URI")
    parser.add_argument("--db", type=str, default="synthetic_data", help="MongoDB database name")
    parser.add_argument("--collection", type=str, default="queries", help="MongoDB collection name")
    args = parser.parse_args()

    # Connect to MongoDB
    console.print(f"[bold blue]Connecting to MongoDB...[/bold blue]")
    client = MongoClient(args.mongo_uri, authSource="admin")
    db = client[args.db]
    collection = db[args.collection]

    # Fetch candidates
    docs = get_unvalidated_docs(collection, category=args.category, limit=args.limit)
    total = len(docs)

    if total == 0:
        console.print("[green]✓ No unvalidated documents found. Nothing to do.[/green]")
        return

    console.print(f"[bold yellow]→ Found {total:,} unvalidated documents[/bold yellow]"
                  f"{' (category: ' + args.category + ')' if args.category else ''}")

    if args.dry_run:
        # Show sample
        for doc in docs[:5]:
            q = doc.get("question", "")[:80]
            cat = doc.get("category", "unknown")
            console.print(f"  [dim]{cat:20s} | {q}...[/dim]")
        if total > 5:
            console.print(f"  [dim]... and {total - 5:,} more[/dim]")
        console.print(f"\n[bold cyan]Dry run — would validate {total:,} documents[/bold cyan]")
        return

    # Setup validator
    console.print(f"[bold blue]Loading validation model: {args.model}[/bold blue]")
    validation_model = parse_model_string(args.model)
    query_model = QueryModel()

    # Stats
    stats = {"passed": 0, "failed": 0, "deleted": 0, "errors": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Validating...", total=total)

        for doc in docs:
            question = doc.get("question", "")
            answer = doc.get("answer", "")
            category = doc.get("category", "")
            doc_id = doc["_id"]

            if not question or not answer:
                console.print(f"[dim]  ⚠ Skipping empty doc {doc_id}[/dim]")
                stats["errors"] += 1
                progress.advance(task)
                continue

            try:
                # Post-hoc validation: no generation context available
                context = ""

                is_valid, reason, score, suggested_fix = query_model.validate_qa(
                    validation_model=validation_model,
                    question=question,
                    answer=answer,
                    context=context,
                    category=category,
                    enable_extra_validation=True,
                )

                accepted = is_valid and score is not None and score >= args.min_score

                if accepted:
                    update_doc(collection, doc, True, score, reason, None, validation_model.name)
                    stats["passed"] += 1
                    progress.update(task, description=f"[green]✓ {score}/10[/green] {question[:50]}...")
                else:
                    if args.delete_failures:
                        delete_doc(collection, doc)
                        stats["deleted"] += 1
                        progress.update(task, description=f"[red]✗ DELETED[/red] {question[:50]}...")
                    else:
                        update_doc(collection, doc, False, score, reason, suggested_fix, validation_model.name)
                        stats["failed"] += 1
                        progress.update(task, description=f"[red]✗ {score}/10[/red] {question[:50]}...")

            except Exception as e:
                console.print(f"[red]  ✗ Error validating {doc_id}: {e}[/red]")
                stats["errors"] += 1

            progress.advance(task)
            time.sleep(0.5)  # Rate limit courtesy

    # Summary
    console.print("\n" + "=" * 60)
    console.print("[bold green]VALIDATION COMPLETE[/bold green]")
    console.print(f"  Total processed:  {total:,}")
    console.print(f"  [green]Passed:[/green]         {stats['passed']:,}")
    console.print(f"  [red]Failed:[/red]         {stats['failed']:,}")
    if args.delete_failures:
        console.print(f"  [red]Deleted:[/red]        {stats['deleted']:,}")
    console.print(f"  [yellow]Errors:[/yellow]         {stats['errors']:,}")
    console.print("=" * 60)

    # Show remaining unvalidated count
    remaining = collection.count_documents({"validated": False, "needs_review": True})
    console.print(f"\n[dim]Unvalidated docs remaining: {remaining:,}[/dim]")


if __name__ == "__main__":
    main()
