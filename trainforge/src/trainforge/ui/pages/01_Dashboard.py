"""Dashboard page — Generation metrics and statistics."""

from __future__ import annotations

import streamlit as st
import plotly.express as px

from trainforge.data_source import MongoDataSource


def _get_data_source() -> MongoDataSource | None:
    """Get the connected data source from session state."""
    ds = st.session_state.get("data_source")
    if isinstance(ds, MongoDataSource) and st.session_state.get("mongo_connected"):
        return ds
    return None


def _fetch_metrics(filters: dict | None = None) -> list[dict]:
    """Fetch validation metrics from MongoDB."""

    ds = _get_data_source()
    if not ds:
        return []

    try:
        collection = "synthetic_metrics.validation_metrics"
        docs = ds.get_records(collection, filters=filters, limit=1000)
        # Convert ObjectId and datetime to serializable types
        for doc in docs:
            if "_id" in doc and not isinstance(doc["_id"], str):
                doc["_id"] = str(doc["_id"])
            if "run_id" in doc and not isinstance(doc["run_id"], str):
                doc["run_id"] = str(doc["run_id"])
        return docs
    except Exception as e:
        st.error(f"Failed to fetch metrics: {e}")
        return []


def _fetch_generation_traces(filters: dict | None = None) -> list[dict]:
    """Fetch generation traces from MongoDB."""

    ds = _get_data_source()
    if not ds:
        return []

    try:
        collection = "synthetic_metrics.generation_traces"
        docs = ds.get_records(collection, filters=filters, limit=5000)
        for doc in docs:
            if "_id" in doc and not isinstance(doc["_id"], str):
                doc["_id"] = str(doc["_id"])
        return docs
    except Exception as e:
        st.error(f"Failed to fetch traces: {e}")
        return []


def _render_overall_stats(metrics_docs: list[dict]) -> None:
    """Render overall aggregated statistics."""

    if not metrics_docs:
        st.info("No generation runs found. Run some generations first.")
        return

    # Aggregate across all runs
    total_candidates = sum(m.get("total_candidates", 0) for m in metrics_docs)
    total_validated = sum(m.get("total_validated", 0) for m in metrics_docs)
    total_passed = sum(m.get("total_passed", 0) for m in metrics_docs)
    total_failed = sum(m.get("total_failed", 0) for m in metrics_docs)

    pass_rate = (total_passed / total_validated * 100) if total_validated > 0 else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Candidates", f"{total_candidates:,}")
    col2.metric("Validated", f"{total_validated:,}")
    col3.metric("Passed", f"{total_passed:,}")
    col4.metric("Failed", f"{total_failed:,}")
    col5.metric("Pass Rate", f"{pass_rate:.1f}%")


def _render_category_breakdown(metrics_docs: list[dict]) -> None:
    """Render per-category breakdown table."""

    if not metrics_docs:
        return

    # Aggregate category stats across runs
    cat_stats: dict[str, dict] = {}

    for m in metrics_docs:
        for cat, stats in m.get("category_stats", {}).items():
            if cat not in cat_stats:
                cat_stats[cat] = {
                    "candidates": 0,
                    "validated": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "fix_attempts": 0,
                    "first_attempt_passes": 0,
                    "pass_after_fix": 0,
                }
            for key in cat_stats[cat]:
                if key in stats:
                    cat_stats[cat][key] += stats[key]

    # Build table data
    rows = []
    for cat, s in sorted(cat_stats.items()):
        pass_rate = (s["passed"] / s["validated"] * 100) if s["validated"] > 0 else 0.0
        rows.append({
            "Category": cat,
            "Candidates": s["candidates"],
            "Validated": s["validated"],
            "Passed": s["passed"],
            "Failed": s["failed"],
            "Skipped": s["skipped"],
            "Pass Rate": f"{pass_rate:.1f}%",
        })

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_generator_breakdown(metrics_docs: list[dict]) -> None:
    """Render per-generator breakdown table."""

    if not metrics_docs:
        return

    gen_stats: dict[str, dict] = {}

    for m in metrics_docs:
        gname = m.get("generator_name", "unknown")
        if gname not in gen_stats:
            gen_stats[gname] = {
                "candidates": 0,
                "validated": 0,
                "passed": 0,
                "failed": 0,
                "model_gen": m.get("generation_model", ""),
                "model_val": m.get("validation_model", ""),
            }
        gen_stats[gname]["candidates"] += m.get("total_candidates", 0)
        gen_stats[gname]["validated"] += m.get("total_validated", 0)
        gen_stats[gname]["passed"] += m.get("total_passed", 0)
        gen_stats[gname]["failed"] += m.get("total_failed", 0)

    rows = []
    for gname, s in sorted(gen_stats.items()):
        pass_rate = (s["passed"] / s["validated"] * 100) if s["validated"] > 0 else 0.0
        short_name = gname.replace("Generate", "")[:25]
        rows.append({
            "Generator": short_name,
            "Candidates": s["candidates"],
            "Validated": s["validated"],
            "Passed": s["passed"],
            "Failed": s["failed"],
            "Pass Rate": f"{pass_rate:.1f}%",
            "Gen Model": s.get("model_gen", ""),
            "Val Model": s.get("model_val", ""),
        })

    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_pass_rate_chart(metrics_docs: list[dict]) -> None:
    """Bar chart of pass rates by category."""

    cat_stats: dict[str, dict] = {}
    for m in metrics_docs:
        for cat, stats in m.get("category_stats", {}).items():
            if cat not in cat_stats:
                cat_stats[cat] = {"validated": 0, "passed": 0}
            cat_stats[cat]["validated"] += stats.get("validated", 0)
            cat_stats[cat]["passed"] += stats.get("passed", 0)

    if not cat_stats:
        return

    data = []
    for cat, s in sorted(cat_stats.items()):
        rate = (s["passed"] / s["validated"] * 100) if s["validated"] > 0 else 0.0
        data.append({"Category": cat, "Pass Rate (%)": round(rate, 1)})

    fig = px.bar(
        data, x="Category", y="Pass Rate (%)",
        title="Validation Pass Rate by Category",
        color="Pass Rate (%)",
        color_continuous_scale="RdYlGn",
    )
    fig.update_layout(xaxis_tickangle=-45, height=350)
    st.plotly_chart(fig, use_container_width=True)


def _render_outcome_pie(metrics_docs: list[dict]) -> None:
    """Pie chart of outcomes (passed/failed/skipped)."""

    total_passed = sum(m.get("total_passed", 0) for m in metrics_docs)
    total_failed = sum(m.get("total_failed", 0) for m in metrics_docs)
    total_skipped = sum(m.get("total_skipped", 0) for m in metrics_docs)

    if not any([total_passed, total_failed, total_skipped]):
        return

    data = [
        {"Outcome": "Passed", "Count": total_passed},
        {"Outcome": "Failed", "Count": total_failed},
        {"Outcome": "Skipped", "Count": total_skipped},
    ]

    fig = px.pie(
        data, values="Count", names="Outcome",
        title="Generation Outcomes",
        color="Outcome",
        color_discrete_map={"Passed": "#4CAF50", "Failed": "#F44336", "Skipped": "#FFC107"},
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


def _render_trace_summary(traces: list[dict]) -> None:
    """Summary of generation traces."""

    if not traces:
        return

    outcomes = {}
    for t in traces:
        outcome = t.get("final_outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Accepted (1st)", outcomes.get("accepted_first_attempt", 0))
    col2.metric("Accepted (after fix)", outcomes.get("accepted_after_fix", 0))
    col3.metric("Rejected", outcomes.get("rejected", 0))
    col4.metric("Skipped", outcomes.get("skipped", 0))

    # Average latency
    latencies = [t.get("generation_latency_ms", 0) for t in traces if t.get("generation_latency_ms")]
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        st.caption(f"Average generation latency: {avg_lat:.0f}ms")


def main() -> None:
    """Render the Dashboard page."""

    from trainforge.ui.components.sidebar import ensure_session_init, render_sidebar

    st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
    ensure_session_init()
    render_sidebar()

    st.title("📊 Generation Dashboard")
    st.markdown("---")

    # --- Filter Controls ---
    with st.expander("Filter Controls"):
        col1, col2 = st.columns(2)
        with col1:
            generator_filter = st.text_input("Generator Name (partial match)")
        with col2:
            domain_filter = st.text_input("Domain")

    # Build filter dict
    filters: dict | None = None
    if generator_filter or domain_filter:
        filters = {}
        if generator_filter:
            filters["generator_name"] = {"$regex": generator_filter, "$options": "i"}
        if domain_filter:
            # Domain is stored in traces; metrics don't have it directly
            pass

    # --- Fetch Data ---
    st.subheader("Validation Metrics")
    metrics_docs = _fetch_metrics(filters)

    # Overall stats
    _render_overall_stats(metrics_docs)

    # Charts row
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        _render_pass_rate_chart(metrics_docs)
    with chart_col2:
        _render_outcome_pie(metrics_docs)

    # Breakdown tables
    table_col1, table_col2 = st.columns(2)
    with table_col1:
        st.subheader("Per-Category Breakdown")
        _render_category_breakdown(metrics_docs)
    with table_col2:
        st.subheader("Per-Generator Breakdown")
        _render_generator_breakdown(metrics_docs)

    # --- Generation Traces Summary ---
    st.markdown("---")
    st.subheader("Generation Traces")
    traces = _fetch_generation_traces()
    _render_trace_summary(traces)


if __name__ == "__main__":
    main()
