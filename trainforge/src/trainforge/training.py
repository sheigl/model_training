"""JSONL export for LoRA fine-tuning — per-domain and cross-domain mixing."""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from pathlib import Path
from typing import Any

from .data_source import DataSource

logger = logging.getLogger(__name__)

# Minimum target dataset size for ratio-based sampling
MIN_TARGET_SIZE: int = 1000


class TrainingExporter:
    """Export validated Q&A pairs from MongoDB to JSONL for LoRA training.

    Supports per-domain exports with category ratio control, and cross-domain
    mixing where multiple domains contribute to a single training file.
    """

    def __init__(self, data_source: DataSource, output_dir: str | Path):
        self.data_source = data_source
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # PER-DOMAIN EXPORT
    # ------------------------------------------------------------------

    def export_per_domain(
        self,
        domain_name: str,
        categories: list[str],
        ratios: dict[str, float] | None = None,
        min_score: int = 7,
        output_file: str | Path | None = None,
    ) -> Path:
        """Export Q&A for a single domain with category ratio control.

        Args:
            domain_name: Domain identifier (e.g., 'mtg')
            categories: List of category names to include
            ratios: Dict mapping category -> target percentage (must sum to 1.0).
                    If None, uses equal distribution.
            min_score: Minimum validation score threshold
            output_file: Output filename (default: {domain_name}_training.jsonl)

        Returns:
            Path to the written JSONL file
        """
        if not categories:
            raise ValueError("categories must not be empty")

        # Default to equal distribution
        if ratios is None:
            ratios = {cat: 1.0 / len(categories) for cat in categories}

        # Normalize ratios to sum to 1.0
        total_ratio = sum(ratios.values())
        if total_ratio > 0:
            ratios = {k: v / total_ratio for k, v in ratios.items()}

        logger.info(
            "Exporting domain '%s' with categories %s (ratios: %s)",
            domain_name, categories, ratios
        )

        # Query all matching records first
        collection = f"synthetic_queries.queries"
        filter_doc = {
            "domain": domain_name,
            "category": {"$in": categories},
            "validation_score": {"$gte": min_score},
        }
        all_records = self.data_source.get_records(
            collection, filters=filter_doc, limit=0
        )

        # Group by category
        by_category: dict[str, list[dict]] = {cat: [] for cat in categories}
        for record in all_records:
            cat = record.get("category", "")
            if cat in by_category:
                by_category[cat].append(record)

        logger.info(
            "Found %d total records across categories: %s",
            len(all_records),
            {k: len(v) for k, v in by_category.items()},
        )

        # Sample to target ratios
        total_target = max(len(all_records), MIN_TARGET_SIZE)
        examples: list[dict] = []
        for cat in categories:
            ratio = ratios.get(cat, 0)
            target_count = int(total_target * ratio)
            available = by_category[cat]
            sampled = random.sample(available, min(target_count, len(available)))
            examples.extend(sampled)

        # Shuffle to interleave categories
        random.shuffle(examples)

        return self._write_jsonl(examples, output_file or f"{domain_name}_training.jsonl")

    # ------------------------------------------------------------------
    # CROSS-DOMAIN EXPORT
    # ------------------------------------------------------------------

    def export_cross_domain(
        self,
        domain_configs: list[dict[str, Any]],
        min_score: int = 7,
        output_file: str | Path | None = None,
    ) -> Path:
        """Mix Q&A from multiple domains into a single training file.

        Args:
            domain_configs: List of dicts with keys:
                - domain (str): domain name
                - categories (list[str]): categories to include
                - ratio (float): target percentage of final dataset
                - max_count (int, optional): hard cap on records from this domain
            min_score: Minimum validation score threshold
            output_file: Output filename

        Returns:
            Path to the written JSONL file
        """
        all_examples: list[dict] = []

        for config in domain_configs:
            domain_name = config["domain"]
            categories = config.get("categories", [])
            ratio = config.get("ratio", 1.0 / len(domain_configs))
            max_count = config.get("max_count", 0)

            collection = "synthetic_queries.queries"
            filter_doc = {
                "domain": domain_name,
                "validation_score": {"$gte": min_score},
            }
            if categories:
                filter_doc["category"] = {"$in": categories}

            records = self.data_source.get_records(
                collection, filters=filter_doc, limit=max_count or 0
            )

            # Sample to ratio proportion
            target = int(len(records) * min(ratio * len(domain_configs), 1.0))
            if target < len(records):
                records = random.sample(records, target)

            all_examples.extend(records)
            logger.info(
                "Domain '%s': %d records (ratio %.0f%%)", domain_name, len(records), ratio * 100
            )

        # Shuffle across domains
        random.shuffle(all_examples)

        filename = output_file or "cross_domain_training.jsonl"
        return self._write_jsonl(all_examples, filename)

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    def _format_example(self, record: dict) -> dict:
        """Convert a MongoDB record to Unsloth SFTTrainer format."""
        question = record.get("question", "")
        answer = record.get("answer", "")
        if not question or not answer:
            return None

        return {
            "messages": [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        }

    def _write_jsonl(self, records: list[dict], filename: str | Path) -> Path:
        """Write formatted examples to JSONL file."""
        output_path = self.output_dir / str(filename)

        # Filter out invalid records and format
        valid_count = 0
        skipped_count = 0
        category_breakdown: Counter = Counter()

        with open(output_path, "w", encoding="utf-8") as f:
            for record in records:
                example = self._format_example(record)
                if example is None:
                    skipped_count += 1
                    continue

                cat = record.get("category", "unknown")
                category_breakdown[cat] += 1
                valid_count += 1

                f.write(json.dumps(example, ensure_ascii=False) + "\n")

        logger.info(
            "Wrote %d examples to %s (%d skipped)",
            valid_count, output_path, skipped_count
        )
        if category_breakdown:
            logger.info("Category breakdown: %s", dict(category_breakdown))

        return output_path

    # ------------------------------------------------------------------
    # QUERY HELPERS
    # ------------------------------------------------------------------

    def get_available_categories(self, domain_name: str) -> list[str]:
        """List available categories for a domain."""
        collection = "synthetic_queries.queries"
        filter_doc = {"domain": domain_name}
        records = self.data_source.get_records(collection, filters=filter_doc, limit=10000)

        categories: set[str] = set()
        for record in records:
            cat = record.get("category")
            if cat:
                categories.add(cat)
        return sorted(categories)

    def get_record_counts(
        self, domain_name: str, min_score: int = 7
    ) -> dict[str, int]:
        """Get record counts per category for a domain."""
        collection = "synthetic_queries.queries"
        filter_doc = {
            "domain": domain_name,
            "validation_score": {"$gte": min_score},
        }
        records = self.data_source.get_records(collection, filters=filter_doc, limit=10000)

        counts: Counter = Counter()
        for record in records:
            cat = record.get("category", "unknown")
            counts[cat] += 1
        return dict(counts)
