# Architecture

## Project Structure

```
trainforge/
├── src/trainforge/
│   ├── domains/mtg/generators/    # Data-driven MTG Q&A generators (25 total)
│   │   ├── article_qa.py          # EDHREC article Q&A (NEW)
│   │   ├── rule_interactions.py   # Two-rule interaction Q&A (NEW)
│   │   ├── staple_analysis.py     # Game-changer card analysis
│   │   ├── salt_questions.py      # Salty/controversial card questions
│   │   ├── color_staples.py       # Color identity staple cards
│   │   ├── multi_card_usage.py    # Combo card interaction explanations
│   │   ├── guide_qa.py            # EDHREC strategy guide questions
│   │   ├── glossary_with_examples.py
│   │   ├── rule_edge_cases.py
│   │   ├── rule_explanations.py
│   │   ├── rule_why_questions.py
│   │   └── ... (other generators)
│   ├── generator.py               # BaseGenerator abstract class
│   └── domains/mtg/models.py      # Pydantic domain models
└── tests/domains/mtg/             # Unit tests mirroring generators/
    ├── test_article_qa.py         # 13 tests (NEW)
    ├── test_rule_interactions.py  # 16 tests (NEW)
    ├── test_staple_analysis.py
    ├── test_salt_questions.py
    ├── test_color_staples.py
    ├── test_multi_card_usage.py
    ├── test_guide_qa.py
    └── ... (other test files)
```

## Patterns

- All generators extend `BaseGenerator[T]` with three abstract methods:
  `get_source_category()`, `get_data_batches()`, `build_prompt()`.
- `build_context()` is optional (overrides base class default).
- Data access is via `self.domain.get_data_source()` which returns a
  mockable interface.
- Tests use `unittest.mock.patch` / `MagicMock` to avoid real MongoDB.
- Test modules have fixtures for `mock_domain`, `generator`, and `template`.
