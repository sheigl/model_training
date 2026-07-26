# Discovery Index

## Milestone: Foundation (Stories 1-3) — Ported to TrainForge

| # | Story | File | Priority | Dependencies | Status |
|---|-------|------|----------|--------------|--------|
| 1 | Shared Base Generator Class | story-001-shared-base-generator.md | High | None | ✅ Complete (old CLI + TrainForge) |
| 2 | Unified Data Access Layer | story-002-unified-data-access-layer.md | High | None | ⚠️ Partial (old CLI complete; TrainForge needs enriched methods) |
| 3 | Extended Data Models | story-003-extended-data-models.md | High | None | ⚠️ Partial (old CLI complete; TrainForge domain models need porting) |

## Milestone: Phase 1 Generators (Stories 4-10) — Ported to TrainForge

| # | Story | File | Priority | Dependencies | Status |
|---|-------|------|----------|--------------|--------|
| 4 | GenerateCardSearchQueries Enhancement | story-004-generate-card-search-queries.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |
| 5 | GenerateComparisonQuestions Enhancement | story-005-generate-comparison-questions.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |
| 6 | GenerateReverseLookupQuestions Enhancement | story-006-generate-reverse-lookup-questions.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |
| 7 | GenerateSynergyQuestions Enhancement | story-007-generate-synergy-questions.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |
| 8 | GenerateBudgetAlternatives Enhancement | story-008-generate-budget-alternatives.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |
| 9 | GenerateColorIdentityQuestions Enhancement | story-009-generate-color-identity-questions.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |
| 10 | GenerateQuickGuidelines Enhancement | story-010-generate-quick-guidelines.md | High | 1, 2, 3 | ⚠️ Partial (old CLI complete; TrainForge generator stub only) |

## New: TrainForge Porting Stories

| # | Story | File | Priority | Dependencies | Status |
|---|-------|------|----------|--------------|--------|
| 11 | Enrich TrainForge MTGDataAccess with typed joins | story-011-tf-enrich-data-access.md | High | 1, 2, 3 | ⏳ Not Started |
| 12 | Port MTG domain models to TrainForge domain plugin | story-012-tf-domain-models.md | High | 11 | ⏳ Not Started |
| 13 | Port GenerateCardSearchQueries to TrainForge | story-013-tf-card-search.md | High | 11, 12 | ⏳ Not Started |
| 14 | Port GenerateComparisonQuestions to TrainForge | story-014-tf-comparison.md | High | 11, 12 | ⏳ Not Started |
| 15 | Port GenerateReverseLookupQuestions to TrainForge | story-015-tf-reverse-lookup.md | High | 11, 12 | ⏳ Not Started |
| 16 | Port GenerateSynergyQuestions to TrainForge | story-016-tf-synergy.md | High | 11, 12 | ⏳ Not Started |
| 17 | Port GenerateBudgetAlternatives to TrainForge | story-017-tf-budget.md | High | 11, 12 | ⏳ Not Started |
| 18 | Port GenerateColorIdentityQuestions to TrainForge | story-018-tf-color-identity.md | High | 11, 12 | ⏳ Not Started |
| 19 | Port GenerateQuickGuidelines to TrainForge | story-019-tf-guidelines.md | High | 11, 12 | ⏳ Not Started |
| 20 | Port GenerateComboQueries to TrainForge | story-020-tf-combo-queries.md | High | 11, 12 | ⏳ Not Started |
| 21 | Port GenerateCommanderKnowledge to TrainForge | story-021-tf-commander-knowledge.md | High | 12 | ✅ Complete |
| 22 | Port GenerateMultiCardUsage to TrainForge | story-022-tf-multi-card-usage.md | High | 11, 12 | ✅ Complete |
| 23 | Port GenerateTerminologyQuestions to TrainForge | story-023-tf-terminology.md | High | 12 | ✅ Complete |
| 24 | Port GenerateDeckbuildingTheory to TrainForge | story-024-tf-deckbuilding-theory.md | High | 12 | ✅ Complete |
| 25 | Port GenerateCommanderBuilding to TrainForge | story-025-tf-commander-building.md | High | 11, 12 | ⏳ Not Started |
| 26 | Port GenerateRulesScenarios to TrainForge | story-026-tf-rules-scenarios.md | High | 12 | ✅ Complete |
| 27 | Port GenerateArchetypes to TrainForge | story-027-tf-archetypes.md | High | 12 | ✅ Complete |
| 28 | Port GenerateGameTheory to TrainForge | story-028-tf-game-theory.md | High | 12 | ✅ Complete |
| 29 | Port GenerateMetaKnowledge to TrainForge | story-029-tf-meta-knowledge.md | High | 12 | ✅ Complete |
| 30 | Port GenerateRuleExplanations to TrainForge | story-030-tf-rule-explanations.md | High | 11, 12 | ✅ Complete |
| 31 | Port GenerateRuleInteractions to TrainForge | story-031-tf-rule-interactions.md | High | 11, 12 | ✅ Complete |
| 32 | Port GenerateGlossaryWithExamples to TrainForge | story-032-tf-glossary-examples.md | High | 11, 12 | ✅ Complete |
| 33 | Port GenerateRuleEdgeCases to TrainForge | story-033-tf-rule-edge-cases.md | High | 11, 12 | ✅ Complete |
| 34 | Port GenerateRuleWhyQuestions to TrainForge | story-034-tf-rule-why.md | High | 11, 12 | ✅ Complete |
| 35 | Port GenerateArticleQa to TrainForge | story-035-tf-article-qa.md | High | 11, 12 | ✅ Complete |
| 36 | Port GenerateGuideQa to TrainForge | story-036-tf-guide-qa.md | High | 11, 12 | ✅ Complete |
| 37 | Port GenerateStapleAnalysis to TrainForge | story-037-tf-staple-analysis.md | High | 11, 12 | ✅ Complete |
| 38 | Port GenerateColorStaples to TrainForge | story-038-tf-color-staples.md | High | 11, 12 | ✅ Complete |
| 39 | Port GenerateSaltQuestions to TrainForge | story-039-tf-salt-questions.md | High | 11, 12 | ✅ Complete |

## Story Count
- Total: 39
- Complete: 19 (Stories 1, 21-24, 26-39)
- Partial: 9 (Stories 2-10 — old CLI complete, TrainForge pending)
- Not Started: 11 (Stories 11-20, 25 — TrainForge porting)

## Dependencies Map

### Foundation & Enablers
- Story 1: No dependencies (Foundation — already complete in both codebases)
- Story 2: No dependencies — old CLI complete; TrainForge port depends on data source ABC
- Story 3: No dependencies — old CLI complete; TrainForge port depends on models.py
- Stories 4-10: Depend on Stories 1, 2, 3 — old CLI implementations use all three
- Story 11: Dependencies on Story 2 (enrich the TrainForge data source)
- Story 12: Dependencies on Story 3 (port domain models to TrainForge plugin)

### Need Both Story 11 AND Story 12 (use MTGDataAccess):
- Stories 13-20, 22, 25, 30-39: Dependencies on Stories 11 and 12

### Need Only Story 12 (no data access — hardcoded topics/terms):
- Stories 21, 23, 24, 26, 27, 28, 29: Dependencies on Story 12 only

## Recommendation
Start with **Story 11 (Enrich TrainForge MTGDataAccess)** since it's the critical path for the majority of porting work (18 generators depend on it). Story 12 (domain models) should be second — all 29 remaining stories depend on it.

**Completed generators (16 total):**
- Stories 21, 23, 24, 26, 27, 28, 29 (7 topic-based) — ported earlier ✅
- Stories 22, 30-39 (9 data-driven: MultiCardUsage, RuleExplanations, RuleInteractions, GlossaryWithExamples, RuleEdgeCases, RuleWhyQuestions, ArticleQa, GuideQa, StapleAnalysis, ColorStaples, SaltQuestions) — ported ✅

**Remaining work:**
- 11 generators still to port: CardSearch, Comparison, ReverseLookup, Synergy, BudgetAlternatives, ColorIdentity, QuickGuidelines, ComboQueries (Stories 13-20), and CommanderBuilding (Story 25)
- Stories 13-20 need both 11 and 12 (both done) — independent of each other and can be parallelized.

## Audit History
- **Date**: 2026-07-23
- **Auditor**: Discovery Agent (trainforge framework launch audit)
- **Finding**: All 10 original stories were implemented in the old CLI tool (`training_data/generate_synthetic_data/`). The new TrainForge framework has generic abstractions but needs MTG-specific porting. Stories 1-10 updated to reflect actual status. Stories 11-19 added for the TrainForge porting work.
- **Date**: 2026-07-24
- **Auditor**: Discovery Agent (generator inventory)
- **Finding**: 20 additional generators discovered in old CLI that were not in original stories. These are all non-overlapping with stories 13-19. Stories 20-39 added covering all remaining Phase 1-4 generators (combo_queries, commander_knowledge, multi_card_usage, terminology, deckbuilding_theory, commander_building, rules_scenarios, archetypes, game_theory, meta_knowledge, rule_explanations, rule_interactions, glossary_with_examples, rule_edge_cases, rule_why_questions, article_qa, guide_qa, staple_analysis, color_staples, salt_questions).
