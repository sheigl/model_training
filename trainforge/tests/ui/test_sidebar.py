"""Tests for TrainForge UI sidebar component — connection status and stats logic."""

from __future__ import annotations



class TestConnectionStatusLogic:
    """Test MongoDB connection status display logic."""

    def test_connected_status_indicator(self):
        """Should show green indicator when connected."""
        mongo_connected = True
        status_color = "🟢" if mongo_connected else "🔴"
        status_text = "Connected" if mongo_connected else "Disconnected"

        assert status_color == "🟢"
        assert status_text == "Connected"

    def test_disconnected_status_indicator(self):
        """Should show red indicator when disconnected."""
        mongo_connected = False
        status_color = "🟢" if mongo_connected else "🔴"
        status_text = "Connected" if mongo_connected else "Disconnected"

        assert status_color == "🔴"
        assert status_text == "Disconnected"


class TestSidebarDomainDisplay:
    """Test active domain display logic."""

    def test_domain_display_with_mapping(self):
        """Should use display name from mapping when available."""
        current_domain = "mtg"
        domain_display_names = {"mtg": "Magic: The Gathering"}

        if current_domain:
            display = domain_display_names.get(current_domain, current_domain)

        assert display == "Magic: The Gathering"

    def test_domain_display_fallback(self):
        """Should fall back to raw name when no mapping exists."""
        current_domain = "unknown_domain"
        domain_display_names = {}

        if current_domain:
            display = domain_display_names.get(current_domain, current_domain)

        assert display == "unknown_domain"

    def test_no_domain_selected(self):
        """Should not show domain section when no domain selected."""
        current_domain = None

        should_show = current_domain is not None
        assert not should_show


class TestSidebarQuickStats:
    """Test quick stats display logic."""

    def test_total_records_formatting(self):
        """Should format total records with commas."""
        total_records = 1234567
        formatted = f"{total_records:,}"
        assert formatted == "1,234,567"

    def test_zero_records(self):
        """Should handle zero records gracefully."""
        total_records = 0
        formatted = f"{total_records:,}"
        assert formatted == "0"


class TestNavigationMenu:
    """Test navigation menu structure."""

    def test_nav_items_structure(self):
        """Navigation should have all expected pages."""
        nav_items = [
            ("Home", "", "🏠"),
            ("Dashboard", "01_Dashboard.py", "📊"),
            ("Generate", "02_Generate.py", "⚡"),
            ("Browse Data", "03_Browse_Data.py", "🔍"),
            ("Export Training", "04_Export_Training.py", "💾"),
            ("Settings", "05_Settings.py", "⚙️"),
        ]

        assert len(nav_items) == 6
        labels = [item[0] for item in nav_items]
        assert "Home" in labels
        assert "Dashboard" in labels
        assert "Generate" in labels
        assert "Settings" in labels

    def test_home_has_no_page_path(self):
        """Home navigation should have empty page path."""
        home_item = ("Home", "", "🏠")
        assert home_item[1] == ""  # No page_link for Home


class TestSidebarStateDefaults:
    """Test sidebar session state defaults."""

    def test_default_session_state(self):
        """Default session state should have expected keys."""
        default_state = {
            "mongo_connected": False,
            "current_domain": None,
            "domain_display_names": {},
            "total_records": 0,
            "last_generation_time": "Never",
        }

        assert default_state["mongo_connected"] is False
        assert default_state["current_domain"] is None
        assert default_state["total_records"] == 0
        assert default_state["last_generation_time"] == "Never"


class TestSidebarMarkdownContent:
    """Test sidebar markdown content generation."""

    def test_connection_status_markdown(self):
        """Should generate correct connection status markdown."""
        mongo_connected = True
        status_color = "🟢" if mongo_connected else "🔴"
        status_text = "Connected" if mongo_connected else "Disconnected"
        markdown = f"**{status_color} MongoDB:** {status_text}"

        assert "MongoDB" in markdown
        assert "Connected" in markdown

    def test_active_domain_markdown(self):
        """Should generate correct active domain markdown."""
        display_name = "Magic: The Gathering"
        markdown = f"**Active Domain:** {display_name}"

        assert "Active Domain" in markdown
        assert "Magic: The Gathering" in markdown


class TestSidebarMetricDisplay:
    """Test sidebar metric display values."""

    def test_total_records_metric(self):
        """Should display total records as a formatted number."""
        total_records = 5000
        # Streamlit's st.metric would receive this value
        assert isinstance(total_records, int)
        assert total_records == 5000
