import random
import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import build_guide_qa_prompt, clean_html, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 2000
console = Console()

class GenerateGuideQa:
    def __init__(
        self,
        guides_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = DEFAULT,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.guides_collection = guides_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_guide_qa(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} GUIDE Q&A ===")

        guides: list[dict] = []
        with console.status("[bold green]Extracting guide data...") as status:
            all_guides = list(
                self.guides_collection.find(
                    {"title": {"$exists": True}, "content": {"$exists": True, "$ne": ""}},
                    {"title": 1, "content": 1},
                )
            )
            good_guides = [g for g in all_guides if len(clean_html(g.get("content", ""))) > 300]
            random.shuffle(good_guides)
            guides = good_guides[: self.target_count + int(self.target_count * 0.25)]
            status.update(f"[bold green]Extracted {len(guides):,} guides")

        print(f"  → Processing {len(guides):,} guides...")

        i: int = 0
        for guide in guides:
            if i >= self.target_count:
                break

            title = guide.get("title", "")
            content = clean_html(guide.get("content", ""))[:2000]

            if not title or not content:
                continue

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{self.target_count:,}...")

            prompt = build_guide_qa_prompt(title, content)

            try:
                query_model = QueryModel()
                response = query_model.query(self.models[ModelType.GENERATION], prompt, max_tokens=8192)
                qa_pairs = list(
                    map(
                        lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                        json.loads(response),
                    )
                )

                qa_context = f"Guide: {title}\n{content[:500]}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=self.models,
                    qa_pairs=qa_pairs,
                    validation_pct=self.validation_pct,
                    enable_extra_validation=True,
                    build_context=lambda: qa_context,
                    source_category="guide_qa",
                    source_data=[title],
                    source_template=None,
                    metrics=self.metrics,
                )

                if is_valid and doc:
                    self.save_item(doc)

            except Exception as e:
                print(f"  ✗ Error for guide '{title[:50]}': {type(e).__name__}: {e}")
                continue

            i = i + 1
