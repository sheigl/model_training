from enum import Enum
from datetime import datetime
import json
import uuid


class QuestionAnswer:
    def __init__(self, question: str, answer: str):
        self.question = question
        self.answer = answer
        
class QuestionAnswerEnhanced(QuestionAnswer):
    def __init__(self, question: str, answer: str):
        super().__init__(question, answer)
        
        self.category: str | None = None
        self.source_data: list | None = None
        self.validated: bool = False
        self.validation_score: float | None = None
        self.needs_review: bool = True
        self.suggested_fix: str | None = None
        self.content_hash: str | None = None
        self.generated_at: datetime | None = None
        self.version: int = 0
        self.source_template : str | None = None
        

class ValidationMetrics:
    """Collects success/failure metrics for Q&A pair validation.

    Supports concurrent usage: each instance gets a unique document _id.
    Multiple instances can share a run_id for easy aggregation.
    """

    def __init__(
        self,
        output_path: str | None = None,
        metrics_collection=None,
        run_id: str | None = None,
        generator_name: str | None = None,
    ):
        self.output_path = output_path
        self.metrics_collection = metrics_collection
        self.run_id = run_id or str(uuid.uuid4())
        self.generator_name = generator_name or "unknown"
        self._id = str(uuid.uuid4())
        self.total_candidates = 0
        self.total_validated = 0
        self.total_skipped = 0
        self.total_passed = 0
        self.total_failed = 0
        self.total_fix_attempts = 0
        self.total_first_attempt_passes = 0
        self.total_pass_after_fix = 0
        self.total_failed_first_attempt = 0
        self.total_failed_after_fixes = 0
        self.category_stats: dict[str, dict] = {}
        self.template_stats: dict[str, dict] = {}
        self._last_flush_candidates = 0

    def record_candidate(self, category: str, template: str | None = None):
        self.total_candidates += 1
        self._ensure_category(category)
        self.category_stats[category]["candidates"] += 1
        if template:
            self._ensure_template(template)
            self.template_stats[template]["candidates"] += 1

    def record_validation_attempt(self, category: str, template: str | None = None):
        self.total_validated += 1
        self._ensure_category(category)
        self.category_stats[category]["validated"] += 1
        if template:
            self._ensure_template(template)
            self.template_stats[template]["validated"] += 1

    def record_skip(self, category: str, template: str | None = None):
        self.total_skipped += 1
        self._ensure_category(category)
        self.category_stats[category]["skipped"] += 1
        if template:
            self._ensure_template(template)
            self.template_stats[template]["skipped"] += 1

    def record_first_attempt_pass(self, score: float | None, category: str, template: str | None = None):
        self.total_passed += 1
        self.total_first_attempt_passes += 1
        self._ensure_category(category)
        self.category_stats[category]["passed"] += 1
        self.category_stats[category]["first_attempt_passes"] += 1
        if score is not None:
            self.category_stats[category]["scores"].append(score)
        if template:
            self._ensure_template(template)
            self.template_stats[template]["passed"] += 1
            self.template_stats[template]["first_attempt_passes"] += 1
            if score is not None:
                self.template_stats[template]["scores"].append(score)

    def record_pass_after_fix(self, score: float | None, category: str, template: str | None = None):
        self.total_passed += 1
        self.total_pass_after_fix += 1
        self._ensure_category(category)
        self.category_stats[category]["passed"] += 1
        self.category_stats[category]["pass_after_fix"] += 1
        if score is not None:
            self.category_stats[category]["scores"].append(score)
        if template:
            self._ensure_template(template)
            self.template_stats[template]["passed"] += 1
            self.template_stats[template]["pass_after_fix"] += 1
            if score is not None:
                self.template_stats[template]["scores"].append(score)

    def record_failed_first_attempt(self, category: str, template: str | None = None):
        self.total_failed += 1
        self.total_failed_first_attempt += 1
        self._ensure_category(category)
        self.category_stats[category]["failed"] += 1
        self.category_stats[category]["failed_first_attempt"] += 1
        if template:
            self._ensure_template(template)
            self.template_stats[template]["failed"] += 1
            self.template_stats[template]["failed_first_attempt"] += 1

    def record_failed_after_fixes(self, category: str, template: str | None = None):
        self.total_failed += 1
        self.total_failed_after_fixes += 1
        self._ensure_category(category)
        self.category_stats[category]["failed"] += 1
        self.category_stats[category]["failed_after_fixes"] += 1
        if template:
            self._ensure_template(template)
            self.template_stats[template]["failed"] += 1
            self.template_stats[template]["failed_after_fixes"] += 1

    def record_fix_attempt(self, category: str, template: str | None = None):
        self.total_fix_attempts += 1
        self._ensure_category(category)
        self.category_stats[category]["fix_attempts"] += 1
        if template:
            self._ensure_template(template)
            self.template_stats[template]["fix_attempts"] += 1

    def _ensure_category(self, category: str):
        if category not in self.category_stats:
            self.category_stats[category] = {
                "candidates": 0,
                "validated": 0,
                "skipped": 0,
                "passed": 0,
                "failed": 0,
                "fix_attempts": 0,
                "first_attempt_passes": 0,
                "pass_after_fix": 0,
                "failed_first_attempt": 0,
                "failed_after_fixes": 0,
                "scores": [],
            }

    def _ensure_template(self, template: str):
        if template not in self.template_stats:
            self.template_stats[template] = {
                "candidates": 0,
                "validated": 0,
                "skipped": 0,
                "passed": 0,
                "failed": 0,
                "fix_attempts": 0,
                "first_attempt_passes": 0,
                "pass_after_fix": 0,
                "failed_first_attempt": 0,
                "failed_after_fixes": 0,
                "scores": [],
            }

    def flush(self):
        """Write current metrics to MongoDB (if configured) and/or local file."""
        if self.metrics_collection is not None:
            self.save_to_mongo(self.metrics_collection)
        if self.output_path:
            self.write_to_file(self.output_path)

    def save_to_mongo(self, collection):
        """Upsert this metrics instance into the given MongoDB collection."""
        now = datetime.utcnow().isoformat() + "Z"
        doc = {
            "_id": self._id,
            "run_id": self.run_id,
            "generator_name": self.generator_name,
            "updated_at": now,
            "metrics": self.summary(),
        }
        collection.update_one(
            {"_id": self._id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def print_rolling_summary(self, interval: int = 10):
        """Print a compact rolling summary every `interval` candidates."""
        if self.total_candidates - self._last_flush_candidates >= interval:
            self._last_flush_candidates = self.total_candidates
            total_val = self.total_validated
            if total_val == 0:
                return
            pass_rate = round(self.total_passed / total_val * 100, 1)
            fail_rate = round(self.total_failed / total_val * 100, 1)
            first_pass_rate = round(self.total_first_attempt_passes / total_val * 100, 1) if total_val > 0 else 0
            fix_recovered = self.total_pass_after_fix
            fix_failed = self.total_failed_after_fixes
            print(f"[Metrics] candidates={self.total_candidates} validated={total_val} first_pass={self.total_first_attempt_passes} pass_after_fix={fix_recovered} fail_first={self.total_failed_first_attempt} fail_after_fix={fix_failed} pass_rate={pass_rate}% first_pass_rate={first_pass_rate}%")

    def summary(self) -> dict:
        def _avg(scores: list[float]) -> float | None:
            return round(sum(scores) / len(scores), 2) if scores else None

        def _build_substats(stats: dict[str, dict]) -> dict[str, dict]:
            return {
                k: {
                    "candidates": v["candidates"],
                    "validated": v["validated"],
                    "skipped": v["skipped"],
                    "passed": v["passed"],
                    "failed": v["failed"],
                    "fix_attempts": v["fix_attempts"],
                    "first_attempt_passes": v["first_attempt_passes"],
                    "pass_after_fix": v["pass_after_fix"],
                    "failed_first_attempt": v["failed_first_attempt"],
                    "failed_after_fixes": v["failed_after_fixes"],
                    "avg_score": _avg(v["scores"]),
                    "pass_rate": round(v["passed"] / v["validated"] * 100, 1) if v["validated"] > 0 else 0,
                    "first_attempt_pass_rate": round(v["first_attempt_passes"] / v["validated"] * 100, 1) if v["validated"] > 0 else 0,
                    "fix_recovery_rate": round(v["pass_after_fix"] / (v["pass_after_fix"] + v["failed_after_fixes"]) * 100, 1) if (v["pass_after_fix"] + v["failed_after_fixes"]) > 0 else None,
                }
                for k, v in stats.items()
            }

        total_validated_or_skipped = self.total_validated + self.total_skipped
        total_with_fixes = self.total_pass_after_fix + self.total_failed_after_fixes
        return {
            "total_candidates": self.total_candidates,
            "total_validated": self.total_validated,
            "total_skipped": self.total_skipped,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "total_fix_attempts": self.total_fix_attempts,
            "total_first_attempt_passes": self.total_first_attempt_passes,
            "total_pass_after_fix": self.total_pass_after_fix,
            "total_failed_first_attempt": self.total_failed_first_attempt,
            "total_failed_after_fixes": self.total_failed_after_fixes,
            "overall_pass_rate": round(self.total_passed / self.total_validated * 100, 1) if self.total_validated > 0 else 0,
            "overall_fail_rate": round(self.total_failed / self.total_validated * 100, 1) if self.total_validated > 0 else 0,
            "overall_skip_rate": round(self.total_skipped / total_validated_or_skipped * 100, 1) if total_validated_or_skipped > 0 else 0,
            "first_attempt_pass_rate": round(self.total_first_attempt_passes / self.total_validated * 100, 1) if self.total_validated > 0 else 0,
            "fix_recovery_rate": round(self.total_pass_after_fix / total_with_fixes * 100, 1) if total_with_fixes > 0 else None,
            "fix_involvement_rate": round(total_with_fixes / self.total_validated * 100, 1) if self.total_validated > 0 else 0,
            "by_category": _build_substats(self.category_stats),
            "by_template": _build_substats(self.template_stats),
        }

    def write_to_file(self, filepath: str):
        import json
        from datetime import datetime
        data = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "metrics": self.summary(),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)


class ModelType(Enum):
    GENERATION = "generation"
    VALIDATION = "validation"

class ModelProvider(Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"

class Model:
    def __init__(self, name: str, type: ModelType, api_key: str | None = None):
        self.name = self._parse_model_name(name)
        self.type = type
        self.provider = self._parse_provider(name)
        self.provider_url = self._parse_provider_host(name)
        self.api_key = api_key or self._parse_api_key(name)
    
    def _parse_provider(self, model_name: str) -> ModelProvider:
        if "anthropic" in model_name:
            return ModelProvider.ANTHROPIC
        elif "openai" in model_name:
            return ModelProvider.OPENAI
        else:
            return ModelProvider.OLLAMA
    
    def _parse_model_name(self, model_name: str):
        if "," not in model_name:
            return model_name
        parts = model_name.split(',')
        # host,model -> parts[1]
        # host,provider_hint,model -> parts[2]
        # host,provider_hint,model,api_key -> parts[2]
        return parts[2] if len(parts) >= 3 else parts[1]
        
    def _parse_provider_host(self, model_name: str) -> str | None:
        if "," in model_name:
            parts = model_name.split(',')
            return parts[0]
        else:
            return "http://127.0.0.1:11434"

    def _parse_api_key(self, model_name: str) -> str | None:
        if "," in model_name:
            parts = model_name.split(',')
            if len(parts) >= 4:
                return parts[3]
        return None
        
class Requirement:
    def __init__(self, name: str, scryfall_query: str, zone_locations: list[str]):
        self.name = name
        self.scryfall_query = scryfall_query
        self.zone_locations = zone_locations

    def toDict(self):
        dictionary = self.__dict__
        return dictionary

class Card:
    def __init__(self, 
                 name: str, 
                 type: str, 
                 mana_cost: str, 
                 text: str, 
                 subtypes: list[str], 
                 supertypes: list[str], 
                 color_identity: list[str], 
                 zone_locations: list[str]):
        self.name = name
        self.type = type
        self.mana_cost = mana_cost
        self.text = text
        self.subtypes = subtypes
        self.supertypes = supertypes
        self.color_identity = color_identity
        self.zone_locations = zone_locations

    def toDict(self):
        dictionary = self.__dict__
        return dictionary

class ProjectedCombo:
    def __init__(self, 
                 name: str, 
                 description: str, 
                 cards_in_combo: list[Card], 
                 features: list[str], 
                 requirements: list[Requirement], 
                 notes: str):
        self.name = name
        self.description = description
        self.cards_in_combo = cards_in_combo
        self.features = features
        self.requirements = requirements
        self.notes = notes

    def toDict(self):
        dictionary = self.__dict__
        dictionary["cards_in_combo"] = list(map(lambda c: c.toDict(), self.cards_in_combo))
        dictionary["requirements"] = list(map(lambda r: r.toDict(), self.requirements))
        return dictionary