"""TrainForge — Main Streamlit application entry point.

Redirects to Dashboard on first load.
"""

from __future__ import annotations

import streamlit as st

from trainforge.config import get_config
from trainforge.data_source import MongoDataSource

# Import domain plugins to trigger auto-registration
import trainforge.domains.mtg  # noqa: F401


def _init_session_state() -> None:
    """Initialize session state variables on first load."""

    if "initialized" in st.session_state:
        return

    # Load config
    try:
        config = get_config()
        st.session_state.config = config
        st.session_state.app_config = config.app_config
        st.session_state.domains_config = config.domains_config
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        st.stop()

    # MongoDB connection state
    st.session_state.mongo_connected = False
    st.session_state.data_source: MongoDataSource | None = None

    # Domain registry state (populated when domains are loaded)
    st.session_state.domain_names: list[str] = []
    st.session_state.domain_display_names: dict[str, str] = {}
    st.session_state.domain_generators: dict[str, list[str]] = {}
    st.session_state.current_domain: str | None = None

    # Generation state
    st.session_state.generation_in_progress = False
    st.session_state.generation_results: list[dict] = []
    st.session_state.generation_metrics: dict | None = None

    # Quick stats (refreshed from DB on demand)
    st.session_state.total_records = 0
    st.session_state.last_generation_time = "Never"

    st.session_state.initialized = True


def _connect_mongodb() -> bool:
    """Attempt to connect to MongoDB using config. Returns success status."""

    if not st.session_state.get("app_config"):
        return False

    mongo_cfg = st.session_state.app_config.get("mongodb", {})
    uri = mongo_cfg.get("uri", "mongodb://localhost:27017/")
    username = mongo_cfg.get("username", "root")
    password = mongo_cfg.get("password", "whatever")
    auth_source = mongo_cfg.get("auth_source", "admin")

    try:
        ds = MongoDataSource(
            uri=uri,
            username=username,
            password=password,
            auth_source=auth_source,
        )
        ds.connect()
        st.session_state.data_source = ds
        st.session_state.mongo_connected = True
        return True
    except Exception:
        st.session_state.data_source = None
        st.session_state.mongo_connected = False
        return False


def _load_domains() -> None:
    """Load domain list from config and populate session state."""

    domains_cfg = st.session_state.domains_config.get("domains", {})
    names = []
    display_names = {}
    generators_map = {}

    for name, info in domains_cfg.items():
        if not isinstance(info, dict):
            continue
        if not info.get("enabled", True):
            continue
        names.append(name)
        display_names[name] = info.get("display_name", name.title())
        # Generator list will be populated when domain is selected for generation
        generators_map[name] = []

    st.session_state.domain_names = names
    st.session_state.domain_display_names = display_names
    st.session_state.domain_generators = generators_map


def _refresh_stats() -> None:
    """Refresh quick stats from MongoDB."""

    ds = st.session_state.get("data_source")
    if not ds or not st.session_state.mongo_connected:
        return

    try:
        total = ds.count("synthetic_queries.queries")
        st.session_state.total_records = total
    except Exception:
        pass


def main() -> None:
    """Main entry point — initializes state then redirects to Dashboard."""

    st.set_page_config(
        page_title="TrainForge",
        page_icon="🔥",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize session state
    _init_session_state()

    # Try to connect to MongoDB (non-blocking for UI)
    if not st.session_state.mongo_connected:
        _connect_mongodb()

    # Load domains from config
    _load_domains()

    # Refresh stats periodically
    _refresh_stats()

    # Redirect to Dashboard
    st.switch_page("pages/01_Dashboard.py")


if __name__ == "__main__":
    main()
