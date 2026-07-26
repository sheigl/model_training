"""Shared sidebar component for TrainForge Streamlit UI."""

from __future__ import annotations

import streamlit as st


def ensure_session_init() -> None:
    """Initialize session state if not already done (handles direct page navigation)."""
    if st.session_state.get("initialized"):
        return
    from trainforge.config import get_config
    try:
        config = get_config()
        st.session_state.config = config
        st.session_state.app_config = config.app_config
        st.session_state.domains_config = config.domains_config
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        st.stop()

    st.session_state.domain_names = []
    st.session_state.domain_display_names = {}
    st.session_state.domain_generators = {}
    st.session_state.mongo_connected = False
    st.session_state.data_source = None
    st.session_state.generation_in_progress = False
    st.session_state.generation_results = []
    st.session_state.total_records = 0
    st.session_state.last_generation_time = "Never"
    st.session_state.current_domain = None
    st.session_state.initialized = True

    # Import domain plugins to trigger auto-registration
    import trainforge.domains.mtg  # noqa: F401

    # Load domains from config
    load_domain_list()


def load_domain_list() -> None:
    """Load domain names from session state config."""
    domains_cfg = st.session_state.get("domains_config", {}).get("domains", {})
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
        generators_map[name] = []
    st.session_state.domain_names = names
    st.session_state.domain_display_names = display_names
    st.session_state.domain_generators = generators_map


def render_sidebar() -> None:
    """Render the navigation sidebar with connection status and quick stats.

    This sidebar is shared across all pages and provides:
    - Navigation menu with icons
    - MongoDB connection indicator
    - Current domain display
    - Quick generation stats
    """

    st.sidebar.title("TrainForge")
    st.sidebar.markdown("---")

    # --- Connection Status ---
    mongo_connected = st.session_state.get("mongo_connected", False)
    status_color = "🟢" if mongo_connected else "🔴"
    status_text = "Connected" if mongo_connected else "Disconnected"
    st.sidebar.markdown(f"**{status_color} MongoDB:** {status_text}")

    # --- Navigation Menu ---
    nav_items = [
        ("Dashboard", "01_Dashboard.py"),
        ("Generate", "02_Generate.py"),
        ("Browse Data", "03_Browse_Data.py"),
        ("Export Training", "04_Export_Training.py"),
        ("Settings", "05_Settings.py"),
    ]

    for label, page_path in nav_items:
        st.sidebar.page_link(f"pages/{page_path}", label=label)

    st.sidebar.markdown("---")

    # --- Current Domain ---
    current_domain = st.session_state.get("current_domain", None)
    if current_domain:
        domain_display = st.session_state.get("domain_display_names", {}).get(
            current_domain, current_domain
        )
        st.sidebar.markdown(f"**Active Domain:** {domain_display}")

    # --- Quick Stats ---
    st.sidebar.subheader("Quick Stats")

    total_records = st.session_state.get("total_records", 0)
    last_gen_time = st.session_state.get("last_generation_time", "Never")

    st.sidebar.metric("Total Records", f"{total_records:,}")
    st.sidebar.caption(f"Last generation: {last_gen_time}")
