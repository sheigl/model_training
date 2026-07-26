"""Tests for TrainForge UI app initialization and session state."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestAppInit:
    """Test the main app.py module initialization functions."""

    @pytest.fixture(autouse=True)
    def _mock_streamlit(self):
        """Mock Streamlit for all tests in this class."""
        mock_st = MagicMock()
        mock_st.session_state = MagicMock()
        mock_st.session_state.__contains__ = MagicMock(return_value=False)
        mock_st.session_state.get = MagicMock(return_value=None)

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            yield mock_st

    @pytest.fixture(autouse=True)
    def _mock_trainforge(self):
        """Mock trainforge modules."""
        mock_config = MagicMock()
        mock_config.get_config.return_value.app_config = {
            "mongodb": {},
            "models": {},
            "defaults": {},
            "paths": {},
        }
        mock_config.get_config.return_value.domains_config = {"domains": {}}

        with patch.dict(sys.modules, {"trainforge.config": mock_config}):
            yield mock_config

    def test_init_session_state_sets_initialized_flag(self, _mock_streamlit):
        """_init_session_state should set the initialized flag."""
        from trainforge.ui.app import _init_session_state

        mock_ss = _mock_streamlit.session_state
        mock_ss.__contains__.return_value = False

        _init_session_state()

        assert "initialized" in [call[0][0] for call in mock_ss.__setitem__.call_args_list] or \
            mock_ss.initialized is True

    def test_init_session_state_loads_config(self, _mock_streamlit, _mock_trainforge):
        """_init_session_state should load configuration."""
        from trainforge.ui.app import _init_session_state

        mock_ss = _mock_streamlit.session_state
        mock_ss.__contains__.return_value = False

        _init_session_state()

        # Config should have been loaded
        assert _mock_trainforge.get_config.called

    def test_init_session_state_handles_config_error(self, _mock_streamlit, _mock_trainforge):
        """_init_session_state should handle config loading errors gracefully."""
        from trainforge.ui.app import _init_session_state

        mock_ss = _mock_streamlit.session_state
        mock_ss.__contains__.return_value = False
        _mock_trainforge.get_config.side_effect = Exception("Config error")

        # Should not raise, but call st.stop()
        with patch.object(_mock_streamlit, "error"), \
             patch.object(_mock_streamlit, "stop"):
            _init_session_state()
            _mock_streamlit.error.assert_called_once()
            _mock_streamlit.stop.assert_called_once()

    def test_init_session_state_skips_if_already_initialized(self, _mock_streamlit):
        """_init_session_state should be a no-op if already initialized."""
        from trainforge.ui.app import _init_session_state

        mock_ss = _mock_streamlit.session_state
        mock_ss.__contains__.return_value = True  # "initialized" is in state

        with patch("trainforge.config.get_config") as mock_get:
            _init_session_state()
            mock_get.assert_not_called()


class TestMongoDBConnection:
    """Test MongoDB connection logic."""

    @pytest.fixture(autouse=True)
    def _mock_streamlit(self):
        mock_st = MagicMock()
        mock_st.session_state = MagicMock()
        mock_st.session_state.get = MagicMock(side_effect=lambda k, d=None: {
            "app_config": {
                "mongodb": {
                    "uri": "mongodb://localhost:27017/",
                    "username": "root",
                    "password": "testpass",
                    "auth_source": "admin",
                },
            },
        }.get(k, d))

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            yield mock_st

    def test_connect_mongodb_success(self, _mock_streamlit):
        """_connect_mongodb should set mongo_connected=True on success."""
        from trainforge.ui.app import _connect_mongodb

        with patch("trainforge.ui.app.MongoDataSource") as MockDS:
            mock_ds = MagicMock()
            MockDS.return_value = mock_ds

            result = _connect_mongodb()

            assert result is True
            assert _mock_streamlit.session_state.mongo_connected is True
            assert _mock_streamlit.session_state.data_source == mock_ds

    def test_connect_mongodb_failure(self, _mock_streamlit):
        """_connect_mongodb should set mongo_connected=False on failure."""
        from trainforge.ui.app import _connect_mongodb

        with patch("trainforge.ui.app.MongoDataSource") as MockDS:
            MockDS.return_value.connect.side_effect = Exception("Connection refused")

            result = _connect_mongodb()

            assert result is False
            assert _mock_streamlit.session_state.mongo_connected is False


class TestDomainLoading:
    """Test domain loading from config."""

    @pytest.fixture(autouse=True)
    def _mock_streamlit(self):
        mock_st = MagicMock()
        mock_st.session_state = MagicMock()
        mock_st.session_state.domains_config = {
            "domains": {
                "mtg": {"display_name": "Magic: The Gathering", "enabled": True},
                "cooking": {"display_name": "Cooking", "enabled": False},
                "coding": {"display_name": "Coding", "enabled": True},
            }
        }

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            yield mock_st

    def test_load_domains_filters_enabled(self, _mock_streamlit):
        """_load_domains should only include enabled domains."""
        from trainforge.ui.app import _load_domains

        _load_domains()

        names = _mock_streamlit.session_state.domain_names
        assert "mtg" in names
        assert "coding" in names
        assert "cooking" not in names  # disabled

    def test_load_domains_sets_display_names(self, _mock_streamlit):
        """_load_domains should populate display name mapping."""
        from trainforge.ui.app import _load_domains

        _load_domains()

        display = _mock_streamlit.session_state.domain_display_names
        assert display.get("mtg") == "Magic: The Gathering"
        assert display.get("coding") == "Coding"


class TestRefreshStats:
    """Test stats refresh from MongoDB."""

    @pytest.fixture(autouse=True)
    def _mock_streamlit(self):
        mock_st = MagicMock()
        mock_st.session_state = MagicMock()
        mock_st.session_state.mongo_connected = True

        with patch.dict(sys.modules, {"streamlit": mock_st}):
            yield mock_st

    def test_refresh_stats_updates_total_records(self, _mock_streamlit):
        """_refresh_stats should update total_records from DB."""
        from trainforge.ui.app import _refresh_stats

        mock_ds = MagicMock()
        mock_ds.count.return_value = 42
        _mock_streamlit.session_state.get.return_value = mock_ds

        _refresh_stats()

        assert _mock_streamlit.session_state.total_records == 42

    def test_refresh_stats_skips_when_disconnected(self, _mock_streamlit):
        """_refresh_stats should be a no-op when not connected."""
        from trainforge.ui.app import _refresh_stats

        _mock_streamlit.session_state.mongo_connected = False

        with patch("trainforge.ui.app.MongoDataSource") as MockDS:
            _refresh_stats()
            MockDS.assert_not_called()


class TestMainFunction:
    """Test the main entry point function."""

    def test_main_sets_page_config(self):
        """main() should set Streamlit page config."""
        with patch.dict(sys.modules, {"streamlit": MagicMock()}):
            import streamlit as st_mock

            # Patch all dependencies
            with patch("trainforge.ui.app._init_session_state"), \
                 patch("trainforge.ui.app.render_sidebar"), \
                 patch("trainforge.ui.app._connect_mongodb"), \
                 patch("trainforge.ui.app._load_domains"), \
                 patch("trainforge.ui.app._refresh_stats"), \
                 patch("trainforge.ui.app._render_home"):

                from trainforge.ui import app
                app.main()

            st_mock.set_page_config.assert_called_once()
            call_kwargs = st_mock.set_page_config.call_args[1]
            assert call_kwargs["page_title"] == "TrainForge"
            assert call_kwargs["layout"] == "wide"
