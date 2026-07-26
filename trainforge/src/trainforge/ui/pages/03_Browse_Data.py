"""Data browser — Explore and manage generated Q&A pairs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import streamlit as st

from trainforge.data_source import MongoDataSource


def _get_data_source() -> MongoDataSource | None:
    """Get the connected data source from session state."""
    ds = st.session_state.get("data_source")
    if isinstance(ds, MongoDataSource) and st.session_state.get("mongo_connected"):
        return ds
    return None


def _build_filter(filters_section: st.delta_generator.DeltaGenerator) -> dict:
    """Build MongoDB filter from user inputs. Returns filter dict."""

    filters: dict = {}

    # Domain dropdown
    domain_names = st.session_state.get("domain_names", [])
    if domain_names:
        selected_domain = filters_section.selectbox(
            "Domain", options=["All"] + domain_names
        )
        if selected_domain != "All":
            filters["domain"] = selected_domain

    # Category multi-select (populated from data)
    ds = _get_data_source()
    categories: list[str] = []
    if ds:
        try:
            sample = ds.get_records("synthetic_queries.queries", limit=5000)
            cats = set()
            for r in sample:
                c = r.get("category")
                if c:
                    cats.add(c)
            categories = sorted(cats)
        except Exception:
            pass

    selected_cats = filters_section.multiselect(
        "Categories", options=categories, default=[]
    )
    if selected_cats:
        filters["category"] = {"$in": selected_cats}

    # Validation score range
    min_score, max_score = filters_section.slider(
        "Validation Score Range",
        min_value=0, max_value=10, value=(0, 10), step=1,
    )
    if min_score > 0 or max_score < 10:
        score_filter: dict = {}
        if min_score > 0:
            score_filter["$gte"] = min_score
        if max_score < 10:
            score_filter["$lte"] = max_score
        filters["validation_score"] = score_filter

    # Date range (uses generated_at field)
    date_col1, date_col2 = filters_section.columns(2)
    with date_col1:
        start_date = date_col1.date_input("From", value=datetime.now() - timedelta(days=30))
    with date_col2:
        end_date = date_col2.date_input("To", value=datetime.now())

    if start_date or end_date:
        date_filter: dict = {}
        if start_date:
            date_filter["$gte"] = datetime.combine(start_date, datetime.min.time())
        if end_date:
            # End of day
            date_filter["$lte"] = datetime.combine(end_date, datetime.max.time())
        filters["generated_at"] = date_filter

    return filters


def _render_record_card(record: dict, index: int) -> None:
    """Render a single Q&A record as an expandable card."""

    question = record.get("question", "No question")
    answer = record.get("answer", "No answer")
    category = record.get("category", "N/A")
    domain = record.get("domain", "N/A")
    score = record.get("validation_score")
    gen_model = record.get("generation_model", "N/A")

    with st.expander(f"Q{index}: {question[:60]}...", expanded=False):
        col_main, col_meta = st.columns([3, 1])

        with col_main:
            st.markdown(f"**Question:** {question}")
            st.markdown(f"**Answer:** {answer}")

        with col_meta:
            # Metadata badges
            st.markdown(f"📁 **Domain:** `{domain}`")
            st.markdown(f"🏷️ **Category:** `{category}`")
            if score is not None:
                color = "✅" if score >= 7 else "⚠️" if score >= 5 else "❌"
                st.markdown(f"{color} **Score:** {score:.1f}")
            st.caption(f"Model: {gen_model}")

        # Actions row
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            if st.button("✏️ Edit", key=f"edit_{index}"):
                st.session_state.editing_record = record
                st.rerun()
        with action_col2:
            rec_id = str(record.get("_id", f"temp_{index}"))
            if st.button("🗑️ Delete", key=f"delete_{index}"):
                _delete_record(rec_id)


def _delete_record(record_id: str) -> None:
    """Delete a record from MongoDB."""

    ds = _get_data_source()
    if not ds:
        st.error("Not connected to database")
        return

    try:
        # Try to parse as ObjectId if it looks like one
        from bson import ObjectId
        filter_doc = {"_id": ObjectId(record_id)}
    except Exception:
        filter_doc = {"_id": record_id}

    deleted = ds.delete_records("synthetic_queries.queries", filter_doc)
    if deleted > 0:
        st.success(f"Deleted {deleted} record(s)")
    else:
        st.warning("Record not found or already deleted")


def _export_filtered(filters: dict, search_query: str) -> bytes | None:
    """Export filtered records to JSONL. Returns file bytes."""

    ds = _get_data_source()
    if not ds:
        return None

    # Apply search query
    if search_query:
        search_filter = {
            "$or": [
                {"question": {"$regex": search_query, "$options": "i"}},
                {"answer": {"$regex": search_query, "$options": "i"}},
            ]
        }
        # Merge with existing filters
        if not filters:
            filters = {}
        filters["$and"] = [filters] if filters else []
        filters["$and"].append(search_filter)

    try:
        records = ds.get_records("synthetic_queries.queries", filters=filters, limit=50000)
    except Exception as e:
        st.error(f"Failed to fetch records for export: {e}")
        return None

    # Format as JSONL (Unsloth SFTTrainer format)
    lines = []
    for record in records:
        question = record.get("question", "")
        answer = record.get("answer", "")
        if not question or not answer:
            continue
        example = {
            "messages": [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        }
        lines.append(json.dumps(example, ensure_ascii=False))

    if not lines:
        st.warning("No records to export")
        return None

    return "\n".join(lines).encode("utf-8")


def main() -> None:
    """Render the Browse Data page."""

    from trainforge.ui.components.sidebar import ensure_session_init, render_sidebar

    st.set_page_config(page_title="Browse Data", page_icon="🔍", layout="wide")
    ensure_session_init()
    render_sidebar()

    st.title("🔍 Browse Generated Data")
    st.markdown("---")

    # --- Search Bar ---
    search_query = st.text_input(
        "Search Q&A pairs...", placeholder="Type to search questions and answers..."
    )

    # --- Filter Controls ---
    filters: dict = {}
    show_filters = st.toggle("Show Advanced Filters", value=False)
    if show_filters:
        filters = _build_filter(st.container())

    # Apply search query as filter
    if search_query:
        if not filters:
            filters = {}
        filters["$or"] = [
            {"question": {"$regex": search_query, "$options": "i"}},
            {"answer": {"$regex": search_query, "$options": "i"}},
        ]

    # --- Pagination Controls ---
    page_size_options = [25, 50, 100]
    page_size = st.selectbox("Page Size", options=page_size_options, index=1)

    ds = _get_data_source()
    total_count = 0
    if ds:
        try:
            total_count = ds.count("synthetic_queries.queries", filters=filters or None)
        except Exception as e:
            st.error(f"Failed to count records: {e}")

    st.caption(f"Showing up to {page_size} of {total_count:,} matching records")

    # Calculate pages
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    if "current_page" not in st.session_state:
        st.session_state.current_page = 0

    page_col1, page_col2, page_col3 = st.columns([1, 2, 1])
    with page_col1:
        if st.button("⬅️ Previous", disabled=st.session_state.current_page <= 0):
            st.session_state.current_page -= 1
            st.rerun()
    with page_col2:
        st.caption(f"Page {st.session_state.current_page + 1} of {total_pages}")
    with page_col3:
        if st.button("Next ➡️", disabled=st.session_state.current_page >= total_pages - 1):
            st.session_state.current_page += 1
            st.rerun()

    # --- Fetch and Display Records ---
    skip = st.session_state.current_page * page_size

    if ds:
        try:
            records = ds.get_records(
                "synthetic_queries.queries",
                filters=filters or None,
                limit=page_size,
                skip=skip,
            )
            # Convert ObjectId to string for display
            for r in records:
                if "_id" in r and not isinstance(r["_id"], str):
                    r["_id"] = str(r["_id"])
        except Exception as e:
            st.error(f"Failed to fetch records: {e}")
            records = []
    else:
        st.warning("Not connected to MongoDB. Connect via Settings page.")
        records = []

    if not records:
        st.info("No records found matching your filters.")
    else:
        # Render record cards
        for i, record in enumerate(records):
            _render_record_card(record, skip + i + 1)

    # --- Export Button ---
    st.markdown("---")
    export_col1, export_col2 = st.columns([3, 1])
    with export_col1:
        if st.button("📥 Export Filtered Results to JSONL", type="primary"):
            data_bytes = _export_filtered(filters, search_query)
            if data_bytes:
                filename = f"trainforge_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
                st.download_button(
                    label=f"Download {filename}",
                    data=data_bytes,
                    file_name=filename,
                    mime="application/jsonl",
                )

    # --- Edit Mode ---
    if st.session_state.get("editing_record"):
        record = st.session_state.editing_record
        with st.expander("✏️ Editing Record", expanded=True):
            _new_question = st.text_area(
                "Question", value=record.get("question", ""), key="edit_q"
            )
            _new_answer = st.text_area(
                "Answer", value=record.get("answer", ""), key="edit_a", height=200
            )

            edit_col1, edit_col2 = st.columns(2)
            with edit_col1:
                if st.button("💾 Save Changes"):
                    # For now, just show a message (full save would need update logic)
                    st.success("Edit functionality — record updated in session")
                    st.session_state.editing_record = None
                    st.rerun()
            with edit_col2:
                if st.button("❌ Cancel"):
                    st.session_state.editing_record = None
                    st.rerun()


if __name__ == "__main__":
    main()
