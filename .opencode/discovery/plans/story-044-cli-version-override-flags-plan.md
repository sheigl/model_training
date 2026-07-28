# Technical Plan: Story 044 — CLI Per-Generator Template Version Override Flags

## 1. Architecture & Design Decisions

### Per-generator flags + JSON alias
**Decision**: Add **both**:
- 27 per-generator `--<slug>-template-version` flags for discoverability (the user explicitly requested these).
- A single `--template-versions` JSON flag for scripting: `--template-versions '{"combo_query": 2, "rule_explanation": 3}'`.

When both are provided, the per-generator flag wins for that generator; the JSON applies to the rest.

### Validator version flags
**Decision**: Add `--<slug>-validator-template-version` flags too (27 more), since the plumbing is identical and the user's requirement #4 mentions validator overrides. Total: 54 new flags + 1 JSON flag + 1 `--list-template-versions` flag.

### Slug derivation
Derive from the existing **count flag** name (not `get_source_category()`) to avoid ambiguity. The count flag is what the operator already knows. The template-version flag appends `-template-version` to the count flag slug.

## 2. Slug → Flag Mapping Table

| Count flag | Category (`get_source_category()`) | Template-version flag | Validator-version flag | argparse dest (template) | argparse dest (validator) |
|------------|-------------------------------------|----------------------|------------------------|--------------------------|----------------------------|
| `--combo-queries` | `combo_query` | `--combo-queries-template-version` | `--combo-queries-validator-template-version` | `combo_queries_template_version` | `combo_queries_validator_template_version` |
| `--card-search` | `card_search` | `--card-search-template-version` | `--card-search-validator-template-version` | `card_search_template_version` | `card_search_validator_template_version` |
| `--commander` | `commander_knowledge` | `--commander-template-version` | `--commander-validator-template-version` | `commander_template_version` | `commander_validator_template_version` |
| `--multi-card` | `multi_card_usage` | `--multi-card-template-version` | `--multi-card-validator-template-version` | `multi_card_template_version` | `multi_card_validator_template_version` |
| `--comparison` | `comparison` | `--comparison-template-version` | `--comparison-validator-template-version` | `comparison_template_version` | `comparison_validator_template_version` |
| `--reverse-lookup` | `reverse_lookup` | `--reverse-lookup-template-version` | `--reverse-lookup-validator-template-version` | `reverse_lookup_template_version` | `reverse_lookup_validator_template_version` |
| `--synergy` | `synergy` | `--synergy-template-version` | `--synergy-validator-template-version` | `synergy_template_version` | `synergy_validator_template_version` |
| `--budget` | `budget` | `--budget-template-version` | `--budget-validator-template-version` | `budget_template_version` | `budget_validator_template_version` |
| `--color-identity` | `color_identity` | `--color-identity-template-version` | `--color-identity-validator-template-version` | `color_identity_template_version` | `color_identity_validator_template_version` |
| `--guidelines` | `quick_guideline` | `--guidelines-template-version` | `--guidelines-validator-template-version` | `guidelines_template_version` | `guidelines_validator_template_version` |
| `--terminology` | `terminology` | `--terminology-template-version` | `--terminology-validator-template-version` | `terminology_template_version` | `terminology_validator_template_version` |
| `--deckbuilding-theory` | `deckbuilding_theory` | `--deckbuilding-theory-template-version` | `--deckbuilding-theory-validator-template-version` | `deckbuilding_theory_template_version` | `deckbuilding_theory_validator_template_version` |
| `--commander-building` | `commander_building` | `--commander-building-template-version` | `--commander-building-validator-template-version` | `commander_building_template_version` | `commander_building_validator_template_version` |
| `--rules-scenarios` | `rules_scenario` | `--rules-scenarios-template-version` | `--rules-scenarios-validator-template-version` | `rules_scenarios_template_version` | `rules_scenarios_validator_template_version` |
| `--archetypes` | `archetype` | `--archetypes-template-version` | `--archetypes-validator-template-version` | `archetypes_template_version` | `archetypes_validator_template_version` |
| `--game-theory` | `game_theory` | `--game-theory-template-version` | `--game-theory-validator-template-version` | `game_theory_template_version` | `game_theory_validator_template_version` |
| `--meta-knowledge` | `meta_knowledge` | `--meta-knowledge-template-version` | `--meta-knowledge-validator-template-version` | `meta_knowledge_template_version` | `meta_knowledge_validator_template_version` |
| `--rule-explanations` | `rule_explanation` | `--rule-explanations-template-version` | `--rule-explanations-validator-template-version` | `rule_explanations_template_version` | `rule_explanations_validator_template_version` |
| `--rule-interactions` | `rule_interaction` | `--rule-interactions-template-version` | `--rule-interactions-validator-template-version` | `rule_interactions_template_version` | `rule_interactions_validator_template_version` |
| `--glossary-examples` | `glossary_with_examples` | `--glossary-examples-template-version` | `--glossary-examples-validator-template-version` | `glossary_examples_template_version` | `glossary_examples_validator_template_version` |
| `--rule-edge-cases` | `rule_edge_case` | `--rule-edge-cases-template-version` | `--rule-edge-cases-validator-template-version` | `rule_edge_cases_template_version` | `rule_edge_cases_validator_template_version` |
| `--rule-why` | `rule_why` | `--rule-why-template-version` | `--rule-why-validator-template-version` | `rule_why_template_version` | `rule_why_validator_template_version` |
| `--article-qa` | `article_qa` | `--article-qa-template-version` | `--article-qa-validator-template-version` | `article_qa_template_version` | `article_qa_validator_template_version` |
| `--guide-qa` | `guide_qa` | `--guide-qa-template-version` | `--guide-qa-validator-template-version` | `guide_qa_template_version` | `guide_qa_validator_template_version` |
| `--staple-analysis` | `staple_analysis` | `--staple-analysis-template-version` | `--staple-analysis-validator-template-version` | `staple_analysis_template_version` | `staple_analysis_validator_template_version` |
| `--color-staples` | `color_staples` | `--color-staples-template-version` | `--color-staples-validator-template-version` | `color_staples_template_version` | `color_staples_validator_template_version` |
| `--salt-questions` | `salt_analysis` | `--salt-questions-template-version` | `--salt-questions-validator-template-version` | `salt_questions_template_version` | `salt_questions_validator_template_version` |

## 3. argparse Changes

### Generator registry for loop-based flag addition
```python
# main.py
GENERATOR_FLAGS = [
    # (count_flag, category, generator_class, constructor_kwargs_keys)
    ("combo-queries", "combo_query", GenerateComboQueries, "combo_queries"),
    ("card-search", "card_search", GenerateCardSearchQueries, "card_search"),
    ("commander", "commander_knowledge", GenerateCommanderKnowledge, "commander"),
    ("multi-card", "multi_card_usage", GenerateMultiCardUsage, "multi_card"),
    ("comparison", "comparison", GenerateComparisonQuestions, "comparison"),
    ("reverse-lookup", "reverse_lookup", GenerateReverseLookupQuestions, "reverse_lookup"),
    ("synergy", "synergy", GenerateSynergyQuestions, "synergy"),
    ("budget", "budget", GenerateBudgetAlternatives, "budget"),
    ("color-identity", "color_identity", GenerateColorIdentityQuestions, "color_identity"),
    ("guidelines", "quick_guideline", GenerateQuickGuidelines, "guidelines"),
    ("terminology", "terminology", GenerateTerminologyQuestions, "terminology"),
    ("deckbuilding-theory", "deckbuilding_theory", GenerateDeckbuildingTheory, "deckbuilding_theory"),
    ("commander-building", "commander_building", GenerateCommanderBuilding, "commander_building"),
    ("rules-scenarios", "rules_scenario", RulesScenariosGenerator, "rules_scenarios"),
    ("archetypes", "archetype", ArchetypesGenerator, "archetypes"),
    ("game-theory", "game_theory", GameTheoryGenerator, "game_theory"),
    ("meta-knowledge", "meta_knowledge", MetaKnowledgeGenerator, "meta_knowledge"),
    ("rule-explanations", "rule_explanation", GenerateRuleExplanations, "rule_explanations"),
    ("rule-interactions", "rule_interaction", GenerateRuleInteractions, "rule_interactions"),
    ("glossary-examples", "glossary_with_examples", GenerateGlossaryWithExamples, "glossary_examples"),
    ("rule-edge-cases", "rule_edge_case", GenerateRuleEdgeCases, "rule_edge_cases"),
    ("rule-why", "rule_why", GenerateRuleWhyQuestions, "rule_why"),
    ("article-qa", "article_qa", GenerateArticleQa, "article_qa"),
    ("guide-qa", "guide_qa", GenerateGuideQa, "guide_qa"),
    ("staple-analysis", "staple_analysis", GenerateStapleAnalysis, "staple_analysis"),
    ("color-staples", "color_staples", GenerateColorStaples, "color_staples"),
    ("salt-questions", "salt_analysis", GenerateSaltQuestions, "salt_questions"),
]

# Add flags in a loop (replaces the 27 individual add_argument calls for counts too)
version_group = parser.add_argument_group("template versions", "Per-generator template version overrides")
for slug, category, cls, dest in GENERATOR_FLAGS:
    parser.add_argument(f"--{slug}", type=int, default=0)  # count flag
    version_group.add_argument(f"--{slug}-template-version", type=int, default=None,
                               help=f"Pin {category} generation templates to version N")
    version_group.add_argument(f"--{slug}-validator-template-version", type=int, default=None,
                               help=f"Pin {category} validator template to version N")

parser.add_argument("--template-versions", type=str, default=None,
                    help='JSON dict of {category: version} for generation templates')
parser.add_argument("--list-template-versions", action="store_true",
                    help="List all template versions in the store and exit")
```

## 4. Threading to Generators

```python
# Parse JSON template-versions if provided
import json
json_versions = json.loads(args.template_versions) if args.template_versions else {}

for slug, category, cls, dest in GENERATOR_FLAGS:
    count = getattr(args, dest.replace("-", "_"))
    if count <= 0:
        continue
    # Resolve version override: per-generator flag wins, then JSON, then None
    tv = getattr(args, f"{dest}_template_version") or json_versions.get(category)
    vv = getattr(args, f"{dest}_validator_template_version")

    gen = cls(
        data_access=data_access,
        models=models,
        validation_pct=args.validation_pct,
        target_count=count,
        save_item=save_fn,
        metrics=metrics,
        dry_run=args.dry_run,
        template_store=template_store,
        template_version_override=tv,
        validator_template_version_override=vv,
    )
    gen.generate()
```

## 5. Fallback Behavior

```python
# In BaseGenerator._load_templates_from_store (from Story 042):
if self._template_version_override is not None:
    doc = self._template_store.get_version(category, tid, "generation", self._template_version_override)
    if doc is None:
        logger.warning(
            "Template version %s not found for %s/%s — falling back to latest",
            self._template_version_override, category, tid)
        doc = self._template_store.get_latest(category, tid, "generation")
# If template_store is None and override set:
if self._template_store is None and self._template_version_override is not None:
    logger.warning(
        "Template version override %s ignored for %s — no template store configured",
        self._template_version_override, category)
```

## 6. `--list-template-versions` Implementation

```python
if args.list_template_versions:
    if template_store is None:
        print("No template store configured (MongoDB unavailable).")
        sys.exit(0)
    docs = template_store._coll.find({}).sort(
        [("generator", 1), ("template_id", 1), ("version", 1)])
    print(f"{'Generator':<25} {'Template ID':<30} {'Type':<12} {'Ver':<5} {'Latest':<7}")
    print("-" * 80)
    for d in docs:
        print(f"{d['generator']:<25} {d['template_id']:<30} {d['template_type']:<12} "
              f"{d['version']:<5} {'*' if d['is_latest'] else ''}")
    sys.exit(0)
```

## 7. `--dry-run` Interaction

```python
if args.dry_run:
    print("=== DRY RUN — resolved template versions ===")
    for slug, category, cls, dest in GENERATOR_FLAGS:
        count = getattr(args, dest.replace("-", "_"))
        if count <= 0:
            continue
        tv = getattr(args, f"{dest}_template_version") or json_versions.get(category)
        vv = getattr(args, f"{dest}_validator_template_version")
        print(f"  {category}: count={count} gen_version={tv or 'latest'} val_version={vv or 'latest'}")
    # Still proceed to construct generators with dry_run=True (no saves)
```

## 8. Files to Modify

| File | Change |
|------|--------|
| `training_data/generate_synthetic_data/main.py` | Add `GENERATOR_FLAGS` registry, loop-based flag addition, version threading, `--list-template-versions`, `--template-versions` JSON flag |

## 9. Task Breakdown
1. Build `GENERATOR_FLAGS` registry (27 entries with exact slug/category/class/dest).
2. Replace 27 individual `--<slug>` count `add_argument` calls with a loop (also adds version flags).
3. Add `--template-versions` JSON flag + `--list-template-versions` action.
4. Implement `--list-template-versions` handler (query store, print table, exit).
5. Implement JSON version parsing + per-generator flag precedence.
6. Update each generator instantiation block to pass `template_version_override` + `validator_template_version_override`.
7. Implement `--dry-run` version resolution print.
8. Write unit tests.

## 10. Test Approach
**File**: `training_data/generate_synthetic_data/tests/test_cli_version_flags.py`

**Test cases**:
- `test_flag_parsing_combo_query` — `--combo-queries-template-version 2` parses to `args.combo_queries_template_version == 2`.
- `test_flag_default_none` — no flag → `args.combo_queries_template_version is None`.
- `test_json_versions_flag` — `--template-versions '{"combo_query": 3}'` parses.
- `test_per_generator_wins_over_json` — both set, per-generator wins.
- `test_list_template_versions` — mock store, verify table output + exit.
- `test_dry_run_prints_versions` — `--dry-run` + override, verify print.
- `test_fallback_version_missing` — mock store returns None for get_version, verify latest used + warning.
- `test_fallback_store_absent` — `template_store=None`, override set, verify warning + class constant used.
- `test_all_27_flags_present` — verify argparse has all 27 template-version + 27 validator-version flags.

## 11. Risks & Open Questions
- **Flag explosion**: 54 new flags. The `argparse` argument group keeps `--help` organized. The JSON alias mitigates scripting pain. **Open**: is 54 flags acceptable, or should we drop validator-version flags to 27?
- **Slug collision**: `--commander` is a count flag for `commander_knowledge` category. The template-version flag is `--commander-template-version` (not `--commander-knowledge-template-version`). This matches the count flag the operator knows. Documented in the mapping table.
- **argparse dest naming**: dashes → underscores automatically. `--combo-queries-template-version` → `args.combo_queries_template_version`. Verified.
- **`GENERATOR_FLAGS` drift**: If a new generator is added, the registry must be updated. A unit test asserts the registry matches the actual generator classes imported in `main.py`.