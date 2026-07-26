"""Training data export page — Per-domain and cross-domain mixing."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from trainforge.data_source import MongoDataSource
from trainforge.training import TrainingExporter


def _get_data_source() -> MongoDataSource | None:
    """Get the connected data source from session state."""
    ds = st.session_state.get("data_source")
    if isinstance(ds, MongoDataSource) and st.session_state.get("mongo_connected"):
        return ds
    return None


def _get_exporter() -> TrainingExporter | None:
    """Create a TrainingExporter instance."""

    ds = _get_data_source()
    if not ds:
        return None

    paths_cfg = st.session_state.get("paths", {})
    output_dir = paths_cfg.get("jsonl_dir", "outputs/jsonl/")
    # Make path relative to project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    full_output_dir = project_root / output_dir

    return TrainingExporter(ds, full_output_dir)


def _render_per_domain_tab() -> None:
    """Render the per-domain export tab."""

    st.header("Per-Domain Export")
    st.caption("Export Q&A for a single domain with category ratio control.")

    # Domain selector
    domain_names = st.session_state.get("domain_names", [])
    if not domain_names:
        st.warning("No domains configured.")
        return

    display_map = st.session_state.get("domain_display_names", {})
    selected_domain_display = st.selectbox(
        "Domain", options=[display_map.get(d, d) for d in domain_names]
    )
    selected_domain = None
    for d in domain_names:
        if display_map.get(d, d) == selected_domain_display:
            selected_domain = d
            break

    # Get available categories for this domain
    exporter = _get_exporter()
    categories = []
    cat_counts: dict[str, int] = {}

    if exporter and selected_domain:
        try:
            categories = exporter.get_available_categories(selected_domain)
            cat_counts = exporter.get_record_counts(selected_domain)
        except Exception as e:
            st.error(f"Failed to load categories: {e}")

    # Category multi-select with ratio sliders
    if not categories:
        st.info("No generated data found for this domain yet.")
        return

    selected_cats = st.multiselect(
        "Categories", options=categories, default=categories[:3]
    )

    if not selected_cats:
        st.warning("Select at least one category.")
        return

    # Show counts and ratio sliders per category
    st.subheader("Category Ratios")
    ratios = {}
    for cat in selected_cats:
        count = cat_counts.get(cat, 0)
        default_ratio = 1.0 / len(selected_cats) if selected_cats else 1.0
        ratio = st.slider(
            f"{cat} ({count:,} records)",
            min_value=0.0, max_value=1.0, value=default_ratio, step=0.05,
            key=f"ratio_{cat}",
        )
        ratios[cat] = ratio

    # Min validation score
    min_score = st.slider(
        "Minimum Validation Score", min_value=0, max_value=10, value=7
    )

    # Output filename
    output_file = st.text_input(
        "Output Filename",
        value=f"{selected_domain}_training.jsonl" if selected_domain else "export.jsonl",
    )

    # Export button
    if st.button("📤 Export Per-Domain", type="primary"):
        if not exporter:
            st.error("No data source available")
            return

        try:
            output_path = exporter.export_per_domain(
                domain_name=selected_domain,
                categories=selected_cats,
                ratios=ratios,
                min_score=min_score,
                output_file=output_file,
            )

            # Read file for download
            if output_path.exists():
                data = output_path.read_bytes()
                st.success(f"Exported {output_path.name} successfully!")

                with open(output_path) as f:
                    line_count = sum(1 for _ in f)

                st.download_button(
                    label=f"⬇️ Download {output_path.name}",
                    data=data,
                    file_name=output_path.name,
                    mime="application/jsonl",
                )

                # Stats display
                st.subheader("Export Stats")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Examples", line_count)
                with col2:
                    st.metric("Categories", len(selected_cats))

        except Exception as e:
            st.error(f"Export failed: {e}")


def _render_cross_domain_tab() -> None:
    """Render the cross-domain export tab."""

    st.header("Cross-Domain Mix")
    st.caption("Mix Q&A from multiple domains into a single training file.")

    # Initialize session state for domain rows
    if "cross_domain_rows" not in st.session_state:
        st.session_state.cross_domain_rows = []

    domain_names = st.session_state.get("domain_names", [])
    display_map = st.session_state.get("domain_display_names", {})

    def _get_categories_for_domain(domain_name: str) -> list[str]:
        exporter = _get_exporter()
        if not exporter:
            return []
        try:
            return exporter.get_available_categories(domain_name)
        except Exception:
            return []

    # Render existing domain rows
    for i, row in enumerate(st.session_state.cross_domain_rows):
        with st.expander(f"Domain {i + 1}: {row.get('display', 'Unknown')}", expanded=True):
            row_col1, row_col2, row_col3 = st.columns([2, 1, 1])

            # Domain selector (already set)
            row_col1.caption(f"Domain: {row.get('display', '')}")

            # Categories for this domain
            cats = _get_categories_for_domain(row["domain"])
            selected_cats = row_col1.multiselect(
                "Categories", options=cats, default=row.get("categories", []),
                key=f"cd_cats_{i}",
            )

            # Ratio slider
            ratio = row_col2.slider(
                "Ratio Weight", min_value=0.1, max_value=2.0, value=row.get("ratio", 1.0),
                step=0.1, key=f"cd_ratio_{i}",
            )

            # Max count
            max_count = row_col3.number_input(
                "Max Count (0=unlimited)", min_value=0, value=row.get("max_count", 0),
                step=100, key=f"cd_max_{i}",
            )

            # Remove button
            if st.button(f"🗑️ Remove Domain {i + 1}", key=f"cd_remove_{i}"):
                st.session_state.cross_domain_rows.pop(i)
                st.rerun()

            # Update row data
            st.session_state.cross_domain_rows[i].update({
                "categories": selected_cats,
                "ratio": ratio,
                "max_count": max_count,
            })

    # Add domain button
    if st.button("➕ Add Domain"):
        new_row = {
            "domain": "",
            "display": "",
            "categories": [],
            "ratio": 1.0 / (len(st.session_state.cross_domain_rows) + 1),
            "max_count": 0,
        }

        # Show domain selector in a dialog-like way
        if domain_names:
            new_display = st.selectbox(
                "Select Domain to Add",
                options=[display_map.get(d, d) for d in domain_names],
                key="add_domain_select",
            )
            for d in domain_names:
                if display_map.get(d, d) == new_display:
                    new_row["domain"] = d
                    new_row["display"] = new_display
                    break

        st.session_state.cross_domain_rows.append(new_row)
        st.rerun()

    # Min validation score
    min_score = st.slider(
        "Minimum Validation Score", min_value=0, max_value=10, value=7
    )

    # Output filename
    output_file = st.text_input(
        "Output Filename", value="cross_domain_training.jsonl"
    )

    # Export button
    if st.button("📤 Export Cross-Domain Mix", type="primary"):
        if not st.session_state.cross_domain_rows:
            st.warning("Add at least one domain to export.")
            return

        exporter = _get_exporter()
        if not exporter:
            st.error("No data source available")
            return

        # Build domain configs
        domain_configs = []
        for row in st.session_state.cross_domain_rows:
            if not row.get("domain"):
                continue
            domain_configs.append({
                "domain": row["domain"],
                "categories": row.get("categories", []),
                "ratio": row.get("ratio", 1.0),
                "max_count": row.get("max_count", 0),
            })

        if not domain_configs:
            st.warning("No valid domains configured.")
            return

        try:
            output_path = exporter.export_cross_domain(
                domain_configs=domain_configs,
                min_score=min_score,
                output_file=output_file,
            )

            # Read file for download
            if output_path.exists():
                data = output_path.read_bytes()
                st.success(f"Exported {output_path.name} successfully!")

                with open(output_path) as f:
                    line_count = sum(1 for _ in f)

                st.download_button(
                    label=f"⬇️ Download {output_path.name}",
                    data=data,
                    file_name=output_path.name,
                    mime="application/jsonl",
                )

                # Stats display
                st.subheader("Export Stats")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Examples", line_count)
                with col2:
                    st.metric("Domains Mixed", len(domain_configs))

        except Exception as e:
            st.error(f"Export failed: {e}")


def main() -> None:
    """Render the Export Training page."""

    from trainforge.ui.components.sidebar import ensure_session_init, render_sidebar

    st.set_page_config(page_title="Export Training", page_icon="💾", layout="wide")
    ensure_session_init()
    render_sidebar()

    st.title("💾 Export Training Data")
    st.markdown("---")

    # Tab selection
    tab1, tab2 = st.tabs(["Per-Domain Export", "Cross-Domain Mix"])

    with tab1:
        _render_per_domain_tab()

    with tab2:
        _render_cross_domain_tab()


if __name__ == "__main__":
    main()
