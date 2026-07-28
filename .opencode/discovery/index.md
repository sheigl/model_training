# Discovery Index — model_training (Legacy CLI)

TrainForge-specific stories have been moved to the `trainforge` repository (`../trainforge/.opencode/discovery/`). This index covers only the legacy CLI and shared infrastructure work.

## Milestone: Foundation (Stories 1-3)

| # | Story | File | Priority | Dependencies | Status |
|---|-------|------|----------|--------------|--------|
| 1 | Shared Base Generator Class | story-001-shared-base-generator.md | High | None | ✅ Complete |
| 2 | Unified Data Access Layer | story-002-unified-data-access-layer.md | High | None | ✅ Complete |
| 3 | Extended Data Models | story-003-extended-data-models.md | High | None | ✅ Complete |

## Milestone: Phase 1 Generators (Stories 4-10)

| # | Story | File | Priority | Dependencies | Status |
|---|-------|------|----------|--------------|--------|
| 4 | GenerateCardSearchQueries Enhancement | story-004-generate-card-search-queries.md | High | 1, 2, 3 | ✅ Complete (old CLI) |
| 5 | GenerateComparisonQuestions Enhancement | story-005-generate-comparison-questions.md | High | 1, 2, 3 | ✅ Complete (old CLI) |
| 6 | GenerateReverseLookupQuestions Enhancement | story-006-generate-reverse-lookup-questions.md | High | 1, 2, 3 | ✅ Complete (old CLI) |
| 7 | GenerateSynergyQuestions Enhancement | story-007-generate-synergy-questions.md | High | 1, 2, 3 | ✅ Complete (old CLI) |
| 8 | GenerateBudgetAlternatives Enhancement | story-008-generate-budget-alternatives.md | High | 1, 2, 3 | ✅ Complete (old CLI) |
| 9 | GenerateColorIdentityQuestions Enhancement | story-009-generate-color-identity-questions.md | High | 1, 2, 3 | ✅ Complete (old CLI) |
| 10 | GenerateQuickGuidelines Enhancement | story-010-generate-quick-guidelines.md | High | 1, 2, 3 | ✅ Complete (old CLI) |

## Milestone: Data-Driven Versioned Templates (Stories 40-45)

Unify template storage in MongoDB so both the legacy CLI and TrainForge load
generation/validator templates from a single versioned store.

| # | Story | File | Plan | Priority | Dependencies | Status |
|---|-------|------|------|----------|--------------|--------|
| 40 | MongoDB Versioned Template Store | story-040-mongodb-template-store.md | plans/story-040-mongodb-template-store-plan.md | High | none | ✅ Complete |
| 41 | Seed/Import Script for Template Store | story-041-seed-import-script.md | plans/story-041-seed-import-script-plan.md | High | 40 | ✅ Complete |
| 42 | Legacy CLI Template Loading Integration | story-042-legacy-cli-template-loading.md | plans/story-042-legacy-cli-template-loading-plan.md | High | 40, 41 | ✅ Complete |
| 44 | CLI Per-Generator Template Version Override Flags | story-044-cli-version-override-flags.md | plans/story-044-cli-version-override-flags-plan.md | Medium | 40, 42 | ✅ Complete |
| 45 | Metrics + Trace Template-Version Recording | story-045-metrics-trace-template-version.md | plans/story-045-metrics-trace-template-version-plan.md | Medium | 40, 42 | ✅ Complete |

> **Note:** Story 043 (TrainForge Template Loading) was moved to the `trainforge` repo.

## Story Count
- Total in this repo: 22 stories (15 legacy + 7 YAML migration)
- Complete: 22
- In progress: 0

## Moved Stories
Stories 11-39 and 43 have been moved to the TrainForge repository (`../trainforge/.opencode/discovery/`). They cover:
- **Story 11**: Enrich TrainForge MTGDataAccess with typed joins (✅ Complete)
- **Story 12**: Port MTG domain models to TrainForge domain plugin (✅ Complete)
- **Stories 13-39**: Individual generator ports to TrainForge (various statuses)
- **Story 43**: TrainForge Template Loading Integration (✅ Complete)

## Milestone: YAML Template Migration (Stories 001-007)

Replace the MongoDB-based template store with local YAML files. The MongoDB `templates` collection is empty — nothing has been seeded — so this is a forward-looking migration that simplifies the system by removing the database dependency for templates.

| # | Story | File | Plan | Priority | Dependencies | Status |
|---|-------|------|------|----------|--------------|--------|
| 1 | YAML Template Structure & Loader Module | story-001-yaml-template-structure.md | plans/story-001-yaml-template-structure-plan.md | High | none | ✅ Complete |
| 2 | Template Loading from YAML Replacing MongoDB | story-002-yaml-template-loading.md | plans/story-002-yaml-template-loading-plan.md | High | 1 | ✅ Complete |
| 3 | Scaffolding Block Migration to YAML | story-003-scaffolding-migration.md | plans/story-003-scaffolding-migration-plan.md | Medium | 1, 2 | ✅ Complete |
| 4 | Validator Template Migration to YAML | story-004-validator-yaml-migration.md | plans/story-004-validator-yaml-migration-plan.md | High | 1, 3 | ✅ Complete |
| 5 | CLI Cleanup — Remove Version Flags, Add --templates-dir | story-005-cli-cleanup.md | plans/story-005-cli-cleanup-plan.md | High | 2, 3, 4 | ✅ Complete |
| 6 | Seed Script Removal & Migration Helper | story-006-seed-script-removal.md | plans/story-006-seed-script-removal-plan.md | Medium | 1 | ✅ Complete |
| 7 | Test Suite Updates for YAML System | story-007-test-updates.md | plans/story-007-test-updates-plan.md | High | 1, 2, 5 | ✅ Complete |

## Audit History
- **Date**: 2026-07-23
- **Auditor**: Discovery Agent (trainforge framework launch audit)
- **Finding**: All 10 original stories were implemented in the old CLI tool. Stories updated to reflect actual status.
- **Date**: 2026-07-24
- **Auditor**: Discovery Agent (generator inventory)
- **Finding**: 20 additional generators discovered in old CLI. Stories 20-39 added covering all remaining Phase 1-4 generators.
- **Date**: 2026-07-26
- **Change**: TrainForge-specific stories (11-39, 43) moved to `../trainforge/.opencode/discovery/` during repo split (Story 046).
- **Date**: 2026-07-27
- **Change**: YAML template migration (Stories 001-007) completed. Replaced MongoDB-based template store with local YAML files in `templates/`. Removed 54 version override CLI flags, added `--templates-dir`. Seed script repurposed with `--to-yaml` mode.
