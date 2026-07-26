"""Settings and configuration page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from trainforge.config import AppConfig, get_config
from trainforge.data_source import MongoDataSource


def _get_config_dir() -> Path:
    """Get the config directory path.

    Resolves to trainforge/config/ (project root is 5 levels up from this file).
    Fallbacks check common locations if running from different working directories.
    """
    # This file is at src/trainforge/ui/pages/05_Settings.py
    # Project root: pages → ui → trainforge(pkg) → src → trainforge(project) = 5 parents up
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "config",  # project root/config/
        Path.cwd() / "config",                                                    # current working directory
    ]
    for candidate in candidates:
        if (candidate / "app.yaml").exists():
            return candidate
    # Return the most likely default even if file doesn't exist yet (for creation flow)
    return candidates[0]


def _load_app_yaml() -> dict:
    """Load current app.yaml contents."""
    config_path = _get_config_dir() / "app.yaml"
    if not config_path.exists():
        st.error(f"Config file not found: {config_path}")
        return {}

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def _save_app_yaml(data: dict) -> bool:
    """Save updated data to app.yaml. Returns success status."""
    config_path = _get_config_dir() / "app.yaml"
    try:
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        st.error(f"Failed to save config: {e}")
        return False


def _load_domains_yaml() -> dict:
    """Load current domains.yaml contents."""
    config_path = _get_config_dir() / "domains.yaml"
    if not config_path.exists():
        return {"domains": {}}

    with open(config_path) as f:
        return yaml.safe_load(f) or {"domains": {}}


def _save_domains_yaml(data: dict) -> bool:
    """Save updated data to domains.yaml."""
    config_path = _get_config_dir() / "domains.yaml"
    try:
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        st.error(f"Failed to save domains config: {e}")
        return False


def _test_mongodb_connection(uri: str, username: str, password: str, auth_source: str) -> bool:
    """Test MongoDB connection with given credentials."""

    try:
        ds = MongoDataSource(
            uri=uri,
            username=username,
            password=password,
            auth_source=auth_source,
        )
        ds.connect()
        ds.close()
        return True
    except Exception as e:
        st.error(f"Connection failed: {e}")
        return False


def _render_mongodb_section(app_data: dict) -> None:
    """Render MongoDB connection settings."""

    st.subheader("MongoDB Connection")

    mongo = app_data.get("mongodb", {})

    col1, col2 = st.columns(2)
    with col1:
        uri = st.text_input(
            "Connection URI",
            value=mongo.get("uri", "mongodb://localhost:27017/"),
            key="mongo_uri",
        )
        username = st.text_input(
            "Username", value=mongo.get("username", "root"), key="mongo_user"
        )
    with col2:
        password = st.text_input(
            "Password", type="password", value="", key="mongo_pass"
        )
        auth_source = st.text_input(
            "Auth Source", value=mongo.get("auth_source", "admin"), key="mongo_auth"
        )

    if st.button("🔗 Test Connection"):
        with st.spinner("Testing connection..."):
            success = _test_mongodb_connection(uri, username, password or mongo.get("password", ""), auth_source)
            if success:
                st.success("MongoDB connection successful!")
                # Update session state
                app_data["mongodb"] = {
                    "uri": uri,
                    "username": username,
                    "password": password or mongo.get("password", ""),
                    "auth_source": auth_source,
                }


def _render_model_section(app_data: dict) -> None:
    """Render model configuration settings."""

    st.subheader("Model Configuration")

    models = app_data.get("models", {})
    defaults = app_data.get("defaults", {})

    col1, col2 = st.columns(2)
    with col1:
        ollama_url = st.text_input(
            "Ollama Base URL",
            value=models.get("ollama_base_url", "http://127.0.0.1:11434"),
            key="ollama_url",
        )
        gen_model = st.text_input(
            "Default Generation Model",
            value=defaults.get("generation_model", "qwen2.5:14b"),
            key="gen_model",
        )
    with col2:
        val_model = st.text_input(
            "Default Validation Model",
            value=defaults.get("validation_model", "qwen2.5:14b"),
            key="val_model",
        )
        validation_pct = st.slider(
            "Validation Percentage", min_value=0.0, max_value=1.0,
            value=float(defaults.get("validation_pct", 1.0)), step=0.1,
            key="val_pct",
        )

    # API Keys
    st.markdown("**API Keys**")
    api_col1, api_col2 = st.columns(2)
    with api_col1:
        anthropic_key = st.text_input(
            "Anthropic API Key", type="password", value="", key="anthropic_key"
        )
    with api_col2:
        openai_key = st.text_input(
            "OpenAI API Key", type="password", value="", key="openai_key"
        )

    # Update config dict (keys are stored empty in YAML, read from env)
    app_data["models"] = {
        "ollama_base_url": ollama_url,
        "anthropic_key": "${ANTHROPIC_KEY:}",
        "openai_key": "${OPENAI_API_KEY:}",
    }
    # Store actual keys in session state for runtime use
    if anthropic_key:
        st.session_state._anthropic_key = anthropic_key
    if openai_key:
        st.session_state._openai_key = openai_key

    app_data["defaults"] = {
        "generation_model": gen_model,
        "validation_model": val_model,
        "validation_pct": validation_pct,
    }


def _render_domain_section() -> None:
    """Render domain management settings."""

    st.subheader("Domain Management")

    domains_data = _load_domains_yaml()
    domains = domains_data.get("domains", {})

    if not domains:
        st.info("No domains configured. Add domains to config/domains.yaml manually.")
        return

    for name, info in domains.items():
        if not isinstance(info, dict):
            continue

        enabled = info.get("enabled", True)
        display_name = info.get("display_name", name.title())
        module_path = info.get("module_path", "")

        with st.expander(f"{display_name} (`{name}`)", expanded=enabled):
            new_enabled = st.toggle(
                "Enabled", value=enabled, key=f"domain_toggle_{name}"
            )
            st.text_input(
                "Display Name", value=display_name, key=f"domain_display_{name}",
                disabled=True,  # Read-only in UI
            )
            st.caption(f"Module: `{module_path}`")

            if new_enabled != enabled:
                domains[name]["enabled"] = new_enabled

    # Save domain changes
    if st.button("💾 Save Domain Settings"):
        _save_domains_yaml({"domains": domains})
        # Reload config into session state
        config = get_config()
        config.load()
        st.session_state.config = config
        st.success("Domain settings saved!")


def _render_paths_section(app_data: dict) -> None:
    """Render output paths configuration."""

    st.subheader("Output Paths")

    paths = app_data.get("paths", {})

    col1, col2 = st.columns(2)
    with col1:
        outputs_dir = st.text_input(
            "Outputs Directory", value=paths.get("outputs", "outputs/"), key="path_outputs"
        )
        jsonl_dir = st.text_input(
            "JSONL Directory", value=paths.get("jsonl_dir", "outputs/jsonl/"), key="path_jsonl"
        )
    with col2:
        checkpoints_dir = st.text_input(
            "Checkpoints Directory",
            value=paths.get("checkpoints_dir", "outputs/checkpoints/"),
            key="path_checkpoints",
        )

    app_data["paths"] = {
        "outputs": outputs_dir,
        "jsonl_dir": jsonl_dir,
        "checkpoints_dir": checkpoints_dir,
    }


def _render_danger_zone() -> None:
    """Render the danger zone with destructive operations."""

    st.markdown("---")
    st.subheader("⚠️ Danger Zone")

    ds = st.session_state.get("data_source")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🗑️ Clear All Generated Data", type="secondary"):
            if ds and st.session_state.get("mongo_connected"):
                try:
                    deleted = ds.delete_records("synthetic_queries.queries", {})
                    st.success(f"Cleared {deleted} records from generated_qa")
                except Exception as e:
                    st.error(f"Failed to clear data: {e}")
            else:
                st.warning("Not connected to MongoDB")

    with col2:
        if st.button("🔄 Reset All Metrics", type="secondary"):
            if ds and st.session_state.get("mongo_connected"):
                try:
                    deleted = ds.delete_records("synthetic_metrics.validation_metrics", {})
                    traces_deleted = ds.delete_records("synthetic_metrics.generation_traces", {})
                    st.success(f"Reset metrics ({deleted} metrics, {traces_deleted} traces)")
                except Exception as e:
                    st.error(f"Failed to reset metrics: {e}")
            else:
                st.warning("Not connected to MongoDB")


def main() -> None:
    """Render the Settings page."""

    from trainforge.ui.components.sidebar import ensure_session_init, render_sidebar

    st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
    ensure_session_init()
    render_sidebar()

    st.title("⚙️ Settings & Configuration")
    st.markdown("---")

    # Load current config
    app_data = _load_app_yaml()

    # --- MongoDB Section ---
    _render_mongodb_section(app_data)

    st.markdown("---")

    # --- Model Configuration ---
    _render_model_section(app_data)

    st.markdown("---")

    # --- Output Paths ---
    _render_paths_section(app_data)

    st.markdown("---")

    # --- Domain Management ---
    _render_domain_section()

    st.markdown("---")

    # --- Save Settings Button ---
    if st.button("💾 Save All Settings", type="primary", use_container_width=True):
        success = _save_app_yaml(app_data)
        if success:
            # Reload config into session state
            try:
                config = AppConfig(str(_get_config_dir()))
                config.load()
                st.session_state.config = config
                st.session_state.app_config = config.app_config
                st.session_state.domains_config = config.domains_config
                st.session_state.defaults = config.defaults
                st.session_state.models = config.models
                st.session_state.paths = config.paths
            except Exception as e:
                st.warning(f"Settings saved but config reload failed: {e}")

            st.success("All settings saved successfully!")

    # --- Danger Zone ---
    _render_danger_zone()


if __name__ == "__main__":
    main()
