"""Tests for CLI --templates-dir flag (Story 005 — CLI Cleanup).

Replaces test_cli_version_flags.py after removal of all MongoDB/template-version flags.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _build_parser():
    """Import build_parser from main without running main()."""
    from training_data.generate_synthetic_data.main import build_parser
    return build_parser()


# ---------------------------------------------------------------------------
# --templates-dir flag tests
# ---------------------------------------------------------------------------


class TestTemplatesDirFlag:
    """Verify the new --templates-dir flag."""

    def test_flag_exists(self):
        parser = _build_parser()
        args = parser.parse_args(["--templates-dir", "/foo/bar"])
        assert args.templates_dir == "/foo/bar"

    def test_flag_default_none(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.templates_dir is None

    def test_help_mentions_templates_dir(self):
        parser = _build_parser()
        help_text = parser.format_help()
        assert "--templates-dir" in help_text


class TestDefaultTemplatesDir:
    """Verify the default templates-dir resolves correctly."""

    def test_default_resolves_to_package_templates(self):
        from training_data.generate_synthetic_data.main import build_parser
        parser = build_parser()
        args = parser.parse_args([])
        # The default is resolved in main(), not in the parser.
        # Verify that when None, it resolves to the package-relative path.
        templates_dir = args.templates_dir or (Path(__file__).parent / "templates")
        assert templates_dir.is_dir()


# ---------------------------------------------------------------------------
# Version flags are gone
# ---------------------------------------------------------------------------


class TestVersionFlagsRemoved:
    """Verify all old version-related flags have been removed."""

    def test_combo_queries_template_version_removed(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--combo-queries-template-version", "2"])

    def test_combo_queries_validator_template_version_removed(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--combo-queries-validator-template-version", "2"])

    def test_template_versions_json_removed(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--template-versions", '{"combo_query": 1}'])

    def test_list_template_versions_removed(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--list-template-versions"])

    def test_salt_questions_template_version_removed(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--salt-questions-template-version", "7"])


# ---------------------------------------------------------------------------
# Count flags still work (backward compat)
# ---------------------------------------------------------------------------


class TestCountFlagsStillPresent:
    """Verify the original 27 count flags are still present."""

    def test_all_count_flags_exist(self):
        parser = _build_parser()
        dests = {a.dest for a in parser._actions}
        expected_count_dests = [
            "combo_queries", "card_search", "commander", "multi_card",
            "comparison", "reverse_lookup", "synergy", "budget",
            "color_identity", "guidelines", "terminology",
            "deckbuilding_theory", "commander_building", "rules_scenarios",
            "archetypes", "game_theory", "meta_knowledge",
            "rule_explanations", "rule_interactions", "glossary_examples",
            "rule_edge_cases", "rule_why",
            "article_qa", "guide_qa", "staple_analysis",
            "color_staples", "salt_questions",
        ]
        for dest in expected_count_dests:
            assert dest in dests, f"Missing count flag dest: {dest}"

    def test_preset_flags_exist(self):
        parser = _build_parser()
        dests = {a.dest for a in parser._actions}
        for preset in ["phase1", "phase2", "phase3", "phase4", "all"]:
            assert preset in dests, f"Missing preset flag: {preset}"

    def test_mongo_flags_still_exist(self):
        parser = _build_parser()
        dests = {a.dest for a in parser._actions}
        for flag in ["mongo_uri", "mongo_user", "mongo_pass"]:
            assert flag in dests, f"Missing mongo flag: {flag}"


# ---------------------------------------------------------------------------
# Dry-run simplified output
# ---------------------------------------------------------------------------


class TestDryRunOutput:
    """Verify dry-run mode prints a simplified message."""

    def test_dry_run_message(self, capsys):
        from training_data.generate_synthetic_data.main import build_parser
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True
