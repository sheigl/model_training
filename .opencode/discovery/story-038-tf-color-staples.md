# Story: Port GenerateColorStaples to TrainForge

## User Story
As a **TrainForge user**, I want **the color staples generator available in the TrainForge UI**, so that **I can generate color-based staple card Q&A data through the web interface**.

## Context
The `GenerateColorStaples` generator is implemented in the old CLI (39 lines) with 1 template. It generates Q&A about the top cards for each color in Commander. It uses `MTGDataAccess.get_top_cards_by_color()` to fetch top cards for 6 colors (black, blue, colorless, green, red, white) and splits them into subsets of 10.

## Acceptance Criteria
- [ ] Create `trainforge/domains/mtg/generators/color_staples.py`
- [ ] Generator class extends `BaseGenerator[tuple[str, list[dict]]]` (TrainForge version) — color name + card dicts
- [ ] Template ported: color_staples (1 template)
- [ ] All 6 COLORS ported: black, blue, colorless, green, red, white
- [ ] Uses `MTGDataAccess.get_top_cards_by_color()` with color and limit=30
- [ ] Splits 30 cards into 3 subsets of 10 for more granular generation
- [ ] `build_prompt()` delegates to `build_color_staples_prompt()` from common.py
- [ ] Templates defined in `templates.yaml` under `color_staples` category
- [ ] Generator registered in `MTGDomain.get_generators()`
- [ ] Generator appears in TrainForge UI generation page
- [ ] Tests written for the generator

## Dependencies
- Story 011: Enrich TrainForge MTGDataAccess with typed joins
- Story 012: Port MTG domain models to TrainForge domain plugin

## Priority: High

## Notes
- Part of Phase 4 in the old CLI (2,000 examples in phase4 mode)
- The `build_color_staples_prompt()` helper in common.py also needs porting
- Category is "color_staples"
- Data type is `tuple[str, list[dict]]` — color name paired with card dicts
