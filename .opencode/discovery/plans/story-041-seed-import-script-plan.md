# Technical Plan: Story 041 — Seed/Import Script

## 1. Architecture & Approach

**Decision**: Use **introspection** of the live generator modules (import them, read `TEMPLATES` class var) rather than parsing source files. This reuses the live `TemplateConfig` objects and avoids drift between the script and the actual templates.

**Validator prompt extraction**: `query_model.py`'s `__build_qa_validation_prompt` and `__build_card_validation_prompt` are name-mangled private methods. The seed script will **add two public helper functions** to `query_model.py` that return the prompt template text without executing an LLM call:
- `build_qa_validation_prompt_template()` → returns the f-string template with `{question}`, `{answer}`, `{context}`, `{category}` placeholders.
- `build_card_validation_prompt_template()` → returns the card-comparison validator template.

These helpers are additive (no behavior change to existing private methods). The seed script calls them.

**Reconciliation**: Legacy is the source of truth (active system per CHANGELOG). The script extracts legacy first, then walks TrainForge `templates.yaml` and adds any `(generator, template_id)` pairs the legacy extraction missed. Conflicts (same key in both) keep the legacy content; the script logs the conflict.

## 2. Extraction Map

### Shared scaffolding blocks (generator="__shared__")

| template_id | template_type | Source |
|-------------|---------------|--------|
| `system_message` | generation | `constants.SYSTEM_MESSAGE` |
| `notation_legend` | generation | `constants.MTG_NOTATION_LEGEND` |
| `requirements_base` | generation | `constants.REQUIREMENTS_BASE` (list → YAML list) |
| `output_format` | generation | `constants.OUTPUT_FORMAT` |
| `card_comparison_instructions` | generation | `constants.CARD_COMPARISON_INSTRUCTIONS` |
| `validation_checklist` | validator | `constants.VALIDATION_CHECKLIST` |
| `validation_scoring_guide` | validator | `constants.VALIDATION_SCORING_GUIDE` |
| `qa_validation` | validator | `query_model.build_qa_validation_prompt_template()` (NEW helper) |

### Per-generator templates (template_type="generation")

For each of the 27 generator files, import the class and read `TEMPLATES`:

| Generator file | Class | Category (generator) | template_ids |
|----------------|-------|---------------------|-------------|
| `generate_combo_queries.py` | `GenerateComboQueries` | `combo_query` | how_does_it_work, what_do_i_need, why_does_this_work, what_is_the_result |
| `generate_article_qa.py` | `GenerateArticleQa` | `article_qa` | article_qa |
| `generate_card_search_queries.py` | `GenerateCardSearchQueries` | `card_search` | competitive, budget, commander_specific, thematic, beginner |
| `generate_comparison_questions.py` | `GenerateComparisonQuestions` | `comparison` | power_level, mana_efficiency, commander_suitability, synergy_potential |
| `generate_reverse_lookup_questions.py` | `GenerateReverseLookupQuestions` | `reverse_lookup` | (introspect) |
| `generate_synergy_questions.py` | `GenerateSynergyQuestions` | `synergy` | (introspect) |
| `generate_budget_alternatives.py` | `GenerateBudgetAlternatives` | `budget` | (introspect) |
| `generate_color_identity_questions.py` | `GenerateColorIdentityQuestions` | `color_identity` | mono_color, two_color, three_color, five_color |
| `generate_quick_guidelines.py` | `GenerateQuickGuidelines` | `quick_guideline` | land_count, ramp_package, removal_suite, card_advantage, win_con_density |
| `generate_terminology_questions.py` | `GenerateTerminologyQuestions` | `terminology` | definition_focused, practical_application |
| `generate_deckbuilding_theory.py` | `GenerateDeckbuildingTheory` | `deckbuilding_theory` | general_advice, example_driven |
| `generate_commander_building.py` | `GenerateCommanderBuilding` | `commander_building` | general_advice, example_driven |
| `generate_rules_scenarios.py` | `RulesScenariosGenerator` | `rules_scenario` | general_advice, example_driven |
| `generate_archetypes.py` | `ArchetypesGenerator` | `archetype` | general_advice, example_driven |
| `generate_game_theory.py` | `GameTheoryGenerator` | `game_theory` | general_advice, scenario_walkthrough |
| `generate_meta_knowledge.py` | `MetaKnowledgeGenerator` | `meta_knowledge` | general_advice, meta_deep_dive |
| `generate_commander_knowledge.py` | `GenerateCommanderKnowledge` | `commander_knowledge` | general_advice, example_driven |
| `generate_rule_explanations.py` | `GenerateRuleExplanations` | `rule_explanation` | plain_english, in_game_scenario, edge_case |
| `generate_rule_interactions.py` | `GenerateRuleInteractions` | `rule_interaction` | plain_english, in_game_scenario, edge_case |
| `generate_glossary_with_examples.py` | `GenerateGlossaryWithExamples` | `glossary_with_examples` | (introspect) |
| `generate_rule_edge_cases.py` | `GenerateRuleEdgeCases` | `rule_edge_case` | (introspect) |
| `generate_rule_why_questions.py` | `GenerateRuleWhyQuestions` | `rule_why` | (introspect) |
| `generate_guide_qa.py` | `GenerateGuideQa` | `guide_qa` | (introspect) |
| `generate_staple_analysis.py` | `GenerateStapleAnalysis` | `staple_analysis` | (introspect) |
| `generate_color_staples.py` | `GenerateColorStaples` | `color_staples` | (introspect) |
| `generate_salt_questions.py` | `GenerateSaltQuestions` | `salt_analysis` | (introspect) |
| `generate_multi_card_usage.py` | `GenerateMultiCardUsage` | `multi_card_usage` | (introspect) |

The script introspects each class's `TEMPLATES` and `get_source_category()` (calling the method is not possible without full construction; instead read the category from a registry — see §6).

### Validator templates (template_type="validator")

| generator | template_id | Source |
|-----------|-------------|--------|
| `__shared__` | `qa_validation` | `query_model.build_qa_validation_prompt_template()` |
| `comparison` | `card_validation` | `query_model.build_card_validation_prompt_template()` |

## 3. `yaml_content` Schema

```yaml
# generation template
instruction: |
  Generate exactly 3 Q&A pairs explaining HOW this combo works...
weight: 1.0
validation_rules:
  - "Answer must explain each card's role in the combo"
  - "All card names and effects must be accurate"
min_answer_length: 80
max_answer_length: 2000
```

```yaml
# shared scaffolding (text block)
content: |
  <system>
  You are an expert Magic: The Gathering rules advisor...
  </system>
```

```yaml
# shared scaffolding (list — REQUIREMENTS_BASE)
content:
  - "At least one question MUST come from..."
  - "Questions must be varied..."
```

```yaml
# validator template
instruction: |
  You are a quality validator...
verification_block: |
  <rules>...</rules>
scoring_guide: |
  9-10: Excellent...
```

## 4. Idempotency Mechanism

`seed()` checks for an existing `(generator, template_id, template_type, version=1)` doc before inserting. If it exists, skip. This makes re-runs safe. The script does NOT use `upsert()` (which would bump versions) — it only inserts version 1 if missing.

## 5. Reconciliation Logic

```python
# Pseudocode
legacy_templates = extract_legacy()      # list of dicts
tf_templates = extract_trainforge_yaml() # list of dicts

seen = set()
final = []
conflicts = []

for t in legacy_templates:
    key = (t["generator"], t["template_id"], t["template_type"])
    seen.add(key)
    final.append(t)

for t in tf_templates:
    key = (t["generator"], t["template_id"], t["template_type"])
    if key in seen:
        conflicts.append(key)  # legacy wins, log conflict
        continue
    final.append(t)

store.seed(final)
print_conflicts(conflicts)
```

## 6. CLI Surface

```python
# training_data/generate_synthetic_data/seed_templates.py

import argparse
from .template_store import TemplateStore

# Generator registry: (class, category) for all 27
GENERATOR_REGISTRY = [
    ("generate_combo_queries", "GenerateComboQueries", "combo_query"),
    ("generate_article_qa", "GenerateArticleQa", "article_qa"),
    # ... all 27
]

def extract_legacy() -> list[dict]: ...
def extract_trainforge_yaml() -> list[dict]: ...
def extract_shared_blocks() -> list[dict]: ...
def extract_validators() -> list[dict]: ...

def main():
    parser = argparse.ArgumentParser(description="Seed MongoDB template store from hardcoded sources")
    parser.add_argument("--mongo-uri", default="mongodb://server.home:27017/")
    parser.add_argument("--mongo-user", default="root")
    parser.add_argument("--mongo-pass", default="whatever")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    templates = (extract_shared_blocks() + extract_legacy() +
                 extract_validators() + extract_trainforge_yaml())

    if args.dry_run:
        for t in templates:
            print(f"  WOULD INSERT: {t['generator']}/{t['template_id']} ({t['template_type']})")
        print(f"\nTotal: {len(templates)} docs would be inserted")
        return

    store = TemplateStore.from_uri(args.mongo_uri, args.mongo_user, args.mongo_pass)
    result = store.seed(templates)
    print(f"Inserted: {result['inserted']}, Skipped (already existed): {result['skipped']}")

if __name__ == "__main__":
    main()
```

## 7. Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `training_data/generate_synthetic_data/seed_templates.py` | **NEW** | Seed script |
| `training_data/generate_synthetic_data/query_model.py` | **MODIFY** (additive) | Add `build_qa_validation_prompt_template()` + `build_card_validation_prompt_template()` public helpers |

## 8. Task Breakdown
1. Add `build_qa_validation_prompt_template()` and `build_card_validation_prompt_template()` to `query_model.py` (return the prompt template strings, refactoring the private methods to use them).
2. Create `seed_templates.py` with `GENERATOR_REGISTRY`.
3. Implement `extract_shared_blocks()` — read constants, build dicts.
4. Implement `extract_legacy()` — import each generator class, read `TEMPLATES`, build dicts.
5. Implement `extract_validators()` — call the new public helpers.
6. Implement `extract_trainforge_yaml()` — load `templates.yaml`, parse categories.
7. Implement reconciliation (legacy wins, log conflicts).
8. Implement `main()` with argparse + dry-run.
9. Write unit tests for extraction logic (mock imports, verify key sets).

## 9. Test Approach
**File**: `training_data/generate_synthetic_data/tests/test_seed_templates.py`

**Test cases**:
- `test_extract_shared_blocks` — returns 8 shared docs with correct template_ids.
- `test_extract_legacy_covers_all_27` — 27 generators present, no duplicate (generator, template_id) keys.
- `test_extract_validators` — returns qa_validation + card_validation.
- `test_extract_trainforge_yaml` — parses all 27 categories.
- `test_reconciliation_legacy_wins` — conflict keys logged, legacy content kept.
- `test_idempotent_seed` — call seed twice, second run skips all.
- `test_dry_run` — no MongoDB writes.

## 10. Risks & Open Questions
- **Importing generator modules**: Some generators may have import-time side effects or heavy dependencies. The script should import lazily inside `extract_legacy()` and handle `ImportError` gracefully.
- **`get_source_category()` is an instance method**: Can't call without constructing. Use the `GENERATOR_REGISTRY` hardcoded category mapping instead. **Risk**: registry drift if a generator's category changes. Mitigation: a unit test asserts `GENERATOR_REGISTRY` categories match each class's `get_source_category()` by constructing with mocks.
- **`REQUIREMENTS_BASE` list serialization**: Store as YAML list under `content:` key. The integration story (042) reads it back and joins with `\n`.
- **`validation_rules` normalization**: Legacy stores as multi-line strings split by `\n`; TrainForge as YAML lists. The seed normalizes to YAML lists in `yaml_content`.