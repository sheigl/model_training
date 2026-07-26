"""Generation control page — Interactive synthetic data generation."""

from __future__ import annotations

import threading
import time
import uuid

import streamlit as st

from trainforge.data_source import MongoDataSource
from trainforge.domain import DomainPlugin, get_registry
from trainforge.generator import create_generator
from trainforge.models import Model, ModelProvider, ValidationMetrics


def _get_data_source() -> MongoDataSource | None:
    """Get the connected data source from session state."""
    ds = st.session_state.get("data_source")
    if isinstance(ds, MongoDataSource) and st.session_state.get("mongo_connected"):
        return ds
    return None


def _build_model(name: str, provider_url: str | None, api_key: str | None) -> Model:
    """Build a Model instance from user inputs."""

    # Auto-detect provider based on name/url patterns
    if "anthropic" in (name or "").lower():
        provider = ModelProvider.ANTHROPIC
    elif "openai" in (name or "").lower() or (provider_url and not provider_url.startswith("http://127")):
        provider = ModelProvider.OPENAI
    else:
        provider = ModelProvider.OLLAMA

    return Model(
        name=name,
        type="generation",
        provider=provider,
        provider_url=provider_url or None,
        api_key=api_key or None,
    )


def _get_domain_plugin(domain_name: str) -> DomainPlugin | None:
    """Get a domain plugin instance from the registry."""

    # Check session state cache first
    cached = st.session_state.get("_domain_plugins", {})
    if domain_name in cached:
        return cached[domain_name]

    # Try to get from registry
    registry = get_registry()
    plugin = registry.get(domain_name)

    # Cache it
    if "_domain_plugins" not in st.session_state:
        st.session_state._domain_plugins = {}
    if plugin:
        st.session_state._domain_plugins[domain_name] = plugin

    return plugin


def _get_generator_classes(domain_plugin: DomainPlugin) -> list[str]:
    """Get generator class names from a domain plugin."""

    try:
        gen_classes = domain_plugin.get_generators()
        return [gc.__name__ for gc in gen_classes]
    except Exception as e:
        st.warning(f"Could not load generators for domain: {e}")
        return []


def _run_generation(
    domain_name: str,
    generator_name: str,
    gen_model_name: str,
    val_model_name: str,
    provider_url: str | None,
    api_key: str | None,
    max_items: int,
    enable_validation: bool,
    log_traces: bool,
) -> dict:
    """Run the generation pipeline in a background thread.

    Returns a summary dict with results and metrics.
    """
    result = {
        "success": False,
        "generated": 0,
        "metrics_summary": {},
        "errors": [],
        "items": [],
    }

    try:
        # Get domain plugin
        domain_plugin = _get_domain_plugin(domain_name)
        if not domain_plugin:
            result["errors"].append(f"Domain '{domain_name}' not found in registry")
            return result

        # Build models
        gen_model = _build_model(gen_model_name, provider_url, api_key)
        val_model = _build_model(val_model_name, provider_url, api_key)
        val_model.type = "validation"

        # Get data source for output
        ds = _get_data_source()

        # Create shared metrics
        run_id = str(uuid.uuid4())[:8]
        metrics = ValidationMetrics(
            generator_name=generator_name,
            generation_model=gen_model.name,
            validation_model=val_model.name,
            run_id=run_id,
        )

        # Find the generator class by name
        gen_classes = domain_plugin.get_generators()
        target_class = None
        for gc in gen_classes:
            if gc.__name__ == generator_name:
                target_class = gc
                break

        if not target_class:
            result["errors"].append(f"Generator '{generator_name}' not found")
            return result

        # Trace callback to update progress info
        def trace_callback(trace):
            st.session_state.generation_progress_trace = {
                "total_rounds": trace.total_rounds,
                "outcome": trace.final_outcome,
                "score": trace.final_score,
            }

        # Create generator instance
        gen = create_generator(
            domain=domain_plugin,
            generator_class=target_class,
            generation_model=gen_model,
            validation_model=val_model,
            output_ds=ds if enable_validation else None,
            run_id=run_id,
            max_items=max_items if max_items > 0 else 0,
            trace_callback=trace_callback if log_traces else None,
            metrics=metrics,
        )

        # Run generation
        results = gen.generate()

        result["success"] = True
        result["generated"] = len(results)
        result["metrics_summary"] = metrics.summary()
        result["items"] = [item.model_dump(exclude_none=True) for item in results[:50]]
        result["run_id"] = run_id

    except Exception as e:
        import traceback
        result["errors"].append(f"{type(e).__name__}: {e}")
        result["errors"].append(traceback.format_exc()[-500:])

    return result


def _render_generation_form() -> dict | None:
    """Render the generation configuration form. Returns config or None."""

    # Domain selector
    domain_names = st.session_state.get("domain_names", [])
    if not domain_names:
        st.warning("No domains configured. Go to Settings to configure domains.")
        return None

    display_map = st.session_state.get("domain_display_names", {})
    domain_options = [display_map.get(d, d) for d in domain_names]

    selected_display = st.selectbox(
        "Domain", options=domain_options, help="Select the knowledge domain"
    )
    selected_domain = None
    for d in domain_names:
        if display_map.get(d, d) == selected_display:
            selected_domain = d
            break

    # Generator selector (populated when domain is selected)
    generator_options = st.session_state.domain_generators.get(selected_domain or "", [])
    if not generator_options and selected_domain:
        # Try to load generators from the plugin
        plugin = _get_domain_plugin(selected_domain)
        if plugin:
            generator_options = _get_generator_classes(plugin)
            st.session_state.domain_generators[selected_domain] = generator_options

    if not generator_options:
        st.warning("No generators found for this domain.")
        return None

    selected_gen = st.selectbox(
        "Generator", options=generator_options, help="Select a specific generator"
    )

    # Model configuration
    col1, col2 = st.columns(2)
    with col1:
        defaults = st.session_state.get("defaults", {})
        gen_model_name = st.text_input(
            "Generation Model",
            value=defaults.get("generation_model", "qwen2.5:14b"),
            help="LLM model name for generating Q&A pairs",
        )
    with col2:
        val_model_name = st.text_input(
            "Validation Model",
            value=defaults.get("validation_model", "qwen2.5:14b"),
            help="LLM model name for validating output",
        )

    # Provider URL and API key
    models_cfg = st.session_state.get("models", {})
    provider_url = st.text_input(
        "Provider URL (Ollama base URL)",
        value=models_cfg.get("ollama_base_url", "http://127.0.0.1:11434"),
        help="Base URL for the LLM provider",
    )

    api_key = st.text_input(
        "API Key (for Anthropic/OpenAI)",
        type="password",
        value="",
        help="API key if using Anthropic or OpenAI providers",
    )

    # Generation controls
    col3, col4 = st.columns(2)
    with col3:
        max_items = st.number_input(
            "Max Items per Generator",
            min_value=0, value=0, step=10,
            help="0 = unlimited. Limits items generated by this generator.",
        )
    with col4:
        enable_validation = st.toggle("Enable Validation", value=True)

    log_traces = st.toggle("Log Generation Traces", value=True)

    return {
        "domain": selected_domain,
        "generator": selected_gen,
        "gen_model_name": gen_model_name,
        "val_model_name": val_model_name,
        "provider_url": provider_url if provider_url else None,
        "api_key": api_key if api_key else None,
        "max_items": max_items,
        "enable_validation": enable_validation,
        "log_traces": log_traces,
    }


def _render_live_output() -> None:
    """Render live generation output as items complete."""

    results = st.session_state.get("generation_results", [])
    if not results:
        return

    st.subheader("Generated Q&A Pairs")

    for i, item in enumerate(results[-20:], start=max(0, len(results) - 20)):
        with st.expander(
            f"Q{i}: {item.get('question', 'Untitled')[:80]}...", expanded=False
        ):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**Question:** {item.get('question', '')}")
                st.markdown(f"**Answer:** {item.get('answer', '')}")
            with col2:
                score = item.get("validation_score")
                if score is not None:
                    st.metric("Score", f"{score:.1f}")
                st.caption(f"Category: {item.get('category', 'N/A')}")
                st.caption(f"Template: {item.get('source_template', 'N/A')}")


def _render_metrics_summary() -> None:
    """Render generation metrics summary."""

    metrics = st.session_state.get("generation_metrics")
    if not metrics:
        return

    st.subheader("Generation Metrics Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Generated", metrics.get("generated", 0))
    col2.metric("Run ID", metrics.get("run_id", "N/A"))

    summary = metrics.get("metrics_summary", {})
    if summary:
        col3.metric("Pass Rate", f"{summary.get('overall_pass_rate', 0):.1f}%")
        col4.metric("Total Candidates", summary.get("total_candidates", 0))


def main() -> None:
    """Render the Generate page."""

    from trainforge.ui.components.sidebar import ensure_session_init, render_sidebar
    ensure_session_init()

    st.set_page_config(page_title="Generate", page_icon="⚡", layout="wide")
    render_sidebar()

    st.title("⚡ Generate Training Data")
    st.markdown("---")

    # --- Configuration Form ---
    with st.container():
        config = _render_generation_form()

    if not config:
        return

    # --- Start Generation Button ---
    status_container = st.empty()

    if st.button("🚀 Start Generation", type="primary", use_container_width=True):
        # Reset state
        st.session_state.generation_in_progress = True
        st.session_state.generation_results = []
        st.session_state.generation_metrics = None

        status_container.info("Starting generation...")

        # Run in background thread to allow progress updates
        def _gen_thread():
            result = _run_generation(**config)

            st.session_state.generation_in_progress = False
            st.session_state.generation_results = result.get("items", [])
            st.session_state.generation_metrics = {
                "generated": result["generated"],
                "success": result["success"],
                "errors": result["errors"],
                "run_id": result.get("run_id", ""),
                "metrics_summary": result.get("metrics_summary", {}),
            }

        thread = threading.Thread(target=_gen_thread, daemon=True)
        thread.start()

        # Animate progress bar while running
        while st.session_state.generation_in_progress:
            time.sleep(0.5)
            # Update progress based on trace info if available
            trace_info = st.session_state.get("generation_progress_trace", {})
            if trace_info:
                status_container.info(
                    f"Generating... Outcome: {trace_info.get('outcome', 'pending')} "
                    f"(Score: {trace_info.get('score', 'N/A')})"
                )

        # Final status
        gen_metrics = st.session_state.generation_metrics
        if gen_metrics and gen_metrics.get("success"):
            status_container.success(
                f"Generation complete! Generated {gen_metrics['generated']} items."
            )
        elif gen_metrics:
            errors = gen_metrics.get("errors", [])
            error_msg = "; ".join(errors[:3]) if errors else "Unknown error"
            status_container.error(f"Generation failed: {error_msg}")

    # --- Live Output ---
    _render_live_output()

    # --- Metrics Summary ---
    _render_metrics_summary()


if __name__ == "__main__":
    main()
