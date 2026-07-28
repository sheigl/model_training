# Technical Plan: CLI Cleanup — Remove MongoDB/Version Flags, Add YAML Path Flag

## Overview
Strip all version-related CLI flags from `main.py`, add a single `--templates-dir` flag, and wire the YAML loader into generator construction.

## Architecture Decisions

### Decision 1: Keep source-data MongoDB flags
`--mongo-uri`, `--mongo-user`, `--mongo-pass` remain — they're still needed for fetching card data and writing output. Only template-store-specific MongoDB connection is removed.

### Decision 2: Default templates-dir to package-relative path
Default: `training_data/generate_synthetic_data/templates/` (resolved relative to the package root). This allows users to override with an absolute or relative path via CLI.

### Decision 3: Remove GENERATOR_FLAGS dest-based version flag generation
The current code uses a loop over `GENERATOR_FLAGS` to generate both template-version and validator-template-version flags dynamically. After cleanup, this loop is replaced with explicit flag additions only for the new `--templates-dir` flag.

## Files to Modify

### Modified files
- `training_data/generate_synthetic_data/main.py` — parser setup, generator instantiation blocks

### Removed/replaced files
- `tests/test_cli_version_flags.py` → replace with `test_cli_templates_dir.py`

## Task Breakdown

### Task 1: Add `--templates-dir` flag to argument parser
In the template configuration section of `add_parser_arguments()`:
```python
parser.add_argument(
    "--templates-dir",
    default=None,
    help="Path to directory containing YAML template files (default: package templates/)",
)
```

Resolve default in code: if None, use `pathlib.Path(__file__).parent / "templates"`.

### Task 2: Remove version-related flag generation loop
Delete the loop that generates per-generator `--<slug>-template-version` and `--<slug>-validator-template-version` flags. This is approximately lines ~100-160 in main.py (the entire GENERATOR_FLAGS iteration block).

Remove:
- `--template-versions JSON` flag
- `--list-template-versions` flag

### Task 3: Remove TemplateStore construction and init_scaffolding() call
In `main()` function, replace:
```python
store = TemplateStore(mongo_uri=args.mongo_uri, ...)
init_scaffolding(store)
```
with:
```python
templates_dir = args.templates_dir or (Path(__file__).parent / "templates")
yaml_loader = YamlTemplateLoader(templates_dir)
```

### Task 4: Update generator instantiation blocks
In each of the ~5 generator instantiation sections in `main.py`, replace:
```python
generator = GeneratorClass(
    mongo_uri=args.mongo_uri,
    template_store=store,
    template_version_override=...,
    validator_template_version_override=...,
    ...
)
```
with:
```python
generator = GeneratorClass(
    mongo_uri=args.mongo_uri,
    yaml_loader=yaml_loader,
    ...
)
```

There are approximately 5 blocks (combo queries, commander deck, etc.) each instantiating multiple generators.

### Task 5: Simplify dry-run output
Remove the version resolution printing from dry-run mode. Replace with a simple message like:
```
Dry run complete. Templates loaded from: {templates_dir}
```

### Task 6: Update tests
Replace `test_cli_version_flags.py` with `test_cli_templates_dir.py`:
- Test that `--templates-dir` sets the correct path
- Test that version flags are no longer recognized (argparse error)
- Test default templates-dir resolves to package-relative path

## Testing Strategy
- Run `pytest training_data/generate_synthetic_data/test_cli_templates_dir.py -v`
- Run full suite: `pytest training_data/generate_synthetic_data/ -v` — verify no new failures
- Manual CLI test: `python -m training_data.generate_synthetic_data.main --help` should show only `--templates-dir` (no version flags)

## Risk Assessment
- **Medium risk**: The generator instantiation blocks in main.py are repetitive but numerous (~5 blocks, ~27 generators). Each must be updated consistently. A search-and-replace for `template_store=store` → `yaml_loader=yaml_loader` and removal of version override kwargs should handle most cases.
- **Low risk**: Flag removal is straightforward argparse changes with no logic impact.
