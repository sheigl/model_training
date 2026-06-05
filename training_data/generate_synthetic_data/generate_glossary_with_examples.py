import random
import pymongo
from rich.console import Console
from rich.status import Status
from query_model import QueryModel
import json
from common import build_glossary_with_examples_prompt, validate_and_loop_with_suggested_fix
from typing import Any, Callable
from models import Model, ModelType, QuestionAnswer, QuestionAnswerEnhanced, ValidationMetrics
from logger import print

DEFAULT = 1500
console = Console()

class GenerateGlossaryWithExamples:
    def __init__(
        self,
        glossary_collection: pymongo.collection.Collection,  # type: ignore
        save_item: Callable[[QuestionAnswerEnhanced], None],
        models: dict[ModelType, Model],
        validation_pct: int,
        target_count: int = DEFAULT,
        metrics: ValidationMetrics | None = None,
    ) -> None:
        self.glossary_collection = glossary_collection
        self.save_item = save_item
        self.models = models
        self.validation_pct = validation_pct
        self.target_count = target_count
        self.metrics = metrics

    def generate_glossary_with_examples(self) -> None:
        print(f"\n=== GENERATING {self.target_count:,} GLOSSARY WITH EXAMPLES QUESTIONS ===")

        terms: list[dict] = []
        with console.status("[bold green]Extracting glossary terms...") as status:
            all_terms = list(
                self.glossary_collection.find(
                    {"word": {"$exists": True}, "definition": {"$exists": True, "$ne": ""}},
                    {"word": 1, "definition": 1},
                )
            )
            meaningful_terms = [t for t in all_terms if len(t.get("definition", "")) > 30]
            random.shuffle(meaningful_terms)
            terms = meaningful_terms[: self.target_count + int(self.target_count * 0.25)]
            status.update(f"[bold green]Extracted {len(terms):,} glossary terms")

        print(f"  → Processing {len(terms):,} glossary terms...")

        i: int = 0
        for term_doc in terms:
            if i >= self.target_count:
                break

            term = term_doc.get("word", "")
            definition = term_doc.get("definition", "")
            if not term or not definition:
                continue

            if (i + 1) % 100 == 0:
                print(f"    Generated {i:,}/{self.target_count:,}...")

            prompt = build_glossary_with_examples_prompt(term, definition)

            try:
                query_model = QueryModel()
                response = query_model.query(self.models[ModelType.GENERATION], prompt)
                qa_pairs = list(
                    map(
                        lambda qa: QuestionAnswer(qa["question"], qa["answer"]),
                        json.loads(response),
                    )
                )

                qa_context = f"Term: {term}\nDefinition: {definition}"

                is_valid, doc = validate_and_loop_with_suggested_fix(
                    query_model=query_model,
                    models=self.models,
                    qa_pairs=qa_pairs,
                    validation_pct=self.validation_pct,
                    enable_extra_validation=False,
                    build_context=lambda: qa_context,
                    source_category="glossary_with_examples",
                    source_data=[f"glossary_{term}"],
                    source_template=None,
                    metrics=self.metrics,
                )

                if is_valid and doc:
                    self.save_item(doc)

            except Exception as e:
                print(f"  ✗ Error for term '{term}': {type(e).__name__}: {e}")
                continue

            i = i + 1
