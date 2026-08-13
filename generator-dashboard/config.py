"""Registry of the 27 MTG synthetic-data generators exposed by the dashboard.

Each entry maps a tab slug to the controlling shell script (``run_<slug>.sh``),
the CLI flag it passes to ``main.py``, the metrics category, and the generator
class name used as ``generator_name`` in ``synthetic_metrics.generator_runs``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GEN_SYNTH_DIR = BASE_DIR / "training_data" / "generate_synthetic_data"
SCRAPERS_DIR = BASE_DIR / "training_data"
LOGS_DIR = Path(__file__).resolve().parent / "logs"

DEFAULT_MODEL = "https://server.tailc63ae8.ts.net:4444/v1,openai,gemma4:31b,$LITELLM_API_KEY"
DEFAULT_VALIDATION_MODEL = "https://server.tailc63ae8.ts.net:4444/v1,openai,glm-5.2,$LITELLM_API_KEY"
DEFAULT_OBSERVER_MODEL = DEFAULT_VALIDATION_MODEL
# Shadow validation is opt-in (Story 049) — off by default, trace-only output.
DEFAULT_SHADOW_VALIDATION_MODEL = ""

MONGO_URI = "mongodb://localhost:27017/"
MONGO_USER = "root"
MONGO_PASS = "whatever"


@dataclass(frozen=True)
class GeneratorSpec:
    slug: str
    flag: str
    category: str
    class_name: str
    default_count: int

    @property
    def script(self) -> Path:
        return GEN_SYNTH_DIR / f"run_{self.slug}.sh"

    @property
    def log_path(self) -> Path:
        return LOGS_DIR / f"{self.slug}.log"

    @property
    def pid_path(self) -> Path:
        return LOGS_DIR / f"{self.slug}.pid"


GENERATORS: list[GeneratorSpec] = [
    GeneratorSpec("combos", "--combo-queries", "combo_query", "GenerateComboQueries", 5000),
    GeneratorSpec("card_search", "--card-search", "card_search", "GenerateCardSearchQueries", 3000),
    GeneratorSpec("commander", "--commander", "commander_rules", "GenerateCommanderKnowledge", 200),
    GeneratorSpec("multi_card", "--multi-card", "multi_card_usage", "GenerateMultiCardUsage", 2000),
    GeneratorSpec("comparison", "--comparison", "comparison", "GenerateComparisonQuestions", 2000),
    GeneratorSpec("reverse_lookup", "--reverse-lookup", "reverse_lookup", "GenerateReverseLookupQuestions", 3000),
    GeneratorSpec("synergy", "--synergy", "synergy", "GenerateSynergyQuestions", 4000),
    GeneratorSpec("budget", "--budget", "budget_alternative", "GenerateBudgetAlternatives", 2000),
    GeneratorSpec("color_identity", "--color-identity", "color_identity", "GenerateColorIdentityQuestions", 2000),
    GeneratorSpec("guidelines", "--guidelines", "quick_guideline", "GenerateQuickGuidelines", 3000),
    GeneratorSpec("terminology", "--terminology", "terminology", "GenerateTerminologyQuestions", 1000),
    GeneratorSpec("deckbuilding_theory", "--deckbuilding-theory", "deckbuilding_theory", "GenerateDeckbuildingTheory", 2000),
    GeneratorSpec("commander_building", "--commander-building", "commander_building", "GenerateCommanderBuilding", 3000),
    GeneratorSpec("rules_scenarios", "--rules-scenarios", "rules_scenario", "GenerateRulesScenarios", 3000),
    GeneratorSpec("archetypes", "--archetypes", "archetype", "GenerateArchetypes", 1500),
    GeneratorSpec("game_theory", "--game-theory", "game_theory", "GenerateGameTheory", 1500),
    GeneratorSpec("meta_knowledge", "--meta-knowledge", "meta_knowledge", "GenerateMetaKnowledge", 1000),
    GeneratorSpec("rule_explanations", "--rule-explanations", "rule_explanation", "GenerateRuleExplanations", 2000),
    GeneratorSpec("rule_interactions", "--rule-interactions", "rule_interaction", "GenerateRuleInteractions", 2000),
    GeneratorSpec("glossary_examples", "--glossary-examples", "glossary_with_examples", "GenerateGlossaryWithExamples", 1500),
    GeneratorSpec("rule_edge_cases", "--rule-edge-cases", "rule_edge_case", "GenerateRuleEdgeCases", 1500),
    GeneratorSpec("rule_why", "--rule-why", "rule_why", "GenerateRuleWhyQuestions", 1000),
    GeneratorSpec("article_qa", "--article-qa", "article_qa", "GenerateArticleQa", 2000),
    GeneratorSpec("guide_qa", "--guide-qa", "guide_qa", "GenerateGuideQa", 2000),
    GeneratorSpec("staple_analysis", "--staple-analysis", "staple_analysis", "GenerateStapleAnalysis", 2000),
    GeneratorSpec("color_staples", "--color-staples", "color_staples", "GenerateColorStaples", 2000),
    GeneratorSpec("salt_questions", "--salt-questions", "salt_analysis", "GenerateSaltQuestions", 1000),
]

GENERATOR_BY_SLUG: dict[str, GeneratorSpec] = {g.slug: g for g in GENERATORS}


@dataclass(frozen=True)
class ScraperSpec:
    """A single scraper job exposed by the dashboard.

    Each item maps a tab slug to the controlling shell script
    (``run_<slug>.sh`` in ``training_data/``), which invokes a python scraper
    with the job's default CLI arguments. ``default_args`` are editable from
    the dashboard (shown in the "Extra args" field).
    """

    slug: str
    name: str
    description: str
    python_script: str
    default_args: tuple[str, ...] = ()

    @property
    def script(self) -> Path:
        return SCRAPERS_DIR / f"run_{self.slug}.sh"

    @property
    def log_path(self) -> Path:
        return LOGS_DIR / f"{self.slug}.log"

    @property
    def pid_path(self) -> Path:
        return LOGS_DIR / f"{self.slug}.pid"

    @property
    def default_args_str(self) -> str:
        return " ".join(self.default_args)


_FUNTRIVIA_DEFAULT_URL = (
    "https://www.funtrivia.com/trivia-quiz/Hobbies/"
    "Basics-of-Magic-The-Gathering-318343.html"
)

SCRAPERS: list[ScraperSpec] = [
    ScraperSpec(
        "edhrec_guides",
        "EDHREC — Guides",
        "Scrape guide posts from EDHREC into edhrec.guides",
        "scrape_edhrec.py",
        ("--guides",),
    ),
    ScraperSpec(
        "edhrec_articles",
        "EDHREC — Articles",
        "Scrape article posts from EDHREC into edhrec.articles",
        "scrape_edhrec.py",
        ("--articles",),
    ),
    ScraperSpec(
        "edhrec_commanders",
        "EDHREC — Top Commanders",
        "Scrape top commanders from EDHREC into edhrec.commanders",
        "scrape_edhrec.py",
        ("--commanders",),
    ),
    ScraperSpec(
        "edhrec_game_changers",
        "EDHREC — Game Changers",
        "Scrape game changers from EDHREC into edhrec.game-changers",
        "scrape_edhrec.py",
        ("--game-changers",),
    ),
    ScraperSpec(
        "edhrec_top_color",
        "EDHREC — Top by Color",
        "Scrape top cards by color identity into edhrec.top-<color>",
        "scrape_edhrec.py",
        ("--top-by-color", "blue"),
    ),
    ScraperSpec(
        "edhrec_top_type",
        "EDHREC — Top by Type",
        "Scrape top cards by card type into edhrec.top-<type>",
        "scrape_edhrec.py",
        ("--top-by-type", "creatures"),
    ),
    ScraperSpec(
        "funtrivia",
        "FunTrivia Quizzes",
        "Scrape MTG quizzes from FunTrivia into funtrivia.quizzes",
        "scrape_funtrivia.py",
        (_FUNTRIVIA_DEFAULT_URL,),
    ),
    ScraperSpec(
        "commander_spellbook",
        "Commander Spellbook Variants",
        "Scrape combo variants from Commander Spellbook into commander_spellbook.variants",
        "scrape_commander_spellbook.py",
    ),
    ScraperSpec(
        "mtg_archetypes",
        "MTG Wiki Archetypes",
        "Scrape deck archetype pages from the MTG Fandom Wiki into mtg_archetypes.archetypes",
        "scrape_mtg_archytypes.py",
    ),
]

SCRAPER_BY_SLUG: dict[str, ScraperSpec] = {s.slug: s for s in SCRAPERS}


_SCRIPT_DEFAULT_RE = re.compile(r'^\s*DEFAULT_(MODEL|VALIDATION_MODEL)="([^"]*)"\s*$')
_SCRIPT_MODEL_DEFAULTS_CACHE: dict[str, tuple[str | None, str | None, str | None, str | None]] = {}


def script_model_defaults(spec: GeneratorSpec) -> tuple[str | None, str | None, str | None, str | None]:
    """Return the ``DEFAULT_MODEL``/``DEFAULT_VALIDATION_MODEL`` values from ``run_<slug>.sh``.

    The run scripts define their model defaults as overridable variables
    (``DEFAULT_MODEL=`` / ``DEFAULT_VALIDATION_MODEL=``) rather than positional
    ``$N`` slots, so the dashboard reads them by name (Story 049). Observer and
    shadow validation have no script-level default and are always ``None``.
    Returns ``(model, validation_model, observer_model, shadow_validation_model)``
    or ``(None, None, None, None)`` if the script is missing or does not define
    the defaults.
    """
    if spec.slug in _SCRIPT_MODEL_DEFAULTS_CACHE:
        return _SCRIPT_MODEL_DEFAULTS_CACHE[spec.slug]
    model: str | None = None
    validation_model: str | None = None
    if spec.script.exists():
        for line in spec.script.read_text().splitlines():
            m = _SCRIPT_DEFAULT_RE.match(line)
            if m:
                var, default = m.groups()
                if var == "MODEL":
                    model = default
                elif var == "VALIDATION_MODEL":
                    validation_model = default
    result = (model, validation_model, None, None)
    _SCRIPT_MODEL_DEFAULTS_CACHE[spec.slug] = result
    return result
