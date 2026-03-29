"""
Unit tests for pure functions in app/routes/admin/helpers.py
"""
from app.routes.admin.helpers import track_changes, safe_int, safe_int_or_none, sort_with_override, safe_redirect_url


class TestTrackChanges:
    """Tests for the track_changes function."""

    def test_track_changes_detects_modified_values(self):
        """track_changes should detect when a value is modified."""
        old = {"name": "Alice", "age": 30}
        new = {"name": "Alice", "age": 31}

        changes = track_changes(old, new)

        assert "age" in changes
        assert changes["age"]["old"] == 30
        assert changes["age"]["new"] == 31
        assert "name" not in changes

    def test_track_changes_detects_added_keys(self):
        """track_changes should detect when a key is added."""
        old = {"name": "Alice"}
        new = {"name": "Alice", "email": "alice@example.com"}

        changes = track_changes(old, new)

        assert "email" in changes
        assert changes["email"]["old"] is None
        assert changes["email"]["new"] == "alice@example.com"

    def test_track_changes_detects_removed_keys(self):
        """track_changes should detect when a key is removed."""
        old = {"name": "Alice", "phone": "555-1234"}
        new = {"name": "Alice"}

        changes = track_changes(old, new)

        assert "phone" in changes
        assert changes["phone"]["old"] == "555-1234"
        assert changes["phone"]["new"] is None

    def test_track_changes_normalizes_empty_strings(self):
        """track_changes should treat empty strings as None."""
        old = {"name": "Alice", "notes": ""}
        new = {"name": "Alice", "notes": None}

        changes = track_changes(old, new)

        # Empty string and None should be treated as equal
        assert "notes" not in changes


class TestSafeInt:
    """Tests for the safe_int function."""

    def test_safe_int_converts_valid_string(self):
        """safe_int should convert a valid numeric string to int."""
        assert safe_int("42") == 42
        assert safe_int("0") == 0
        assert safe_int("-10") == -10

    def test_safe_int_returns_default_for_invalid(self):
        """safe_int should return default for invalid input."""
        assert safe_int("abc") == 0
        assert safe_int("abc", default=99) == 99
        assert safe_int(None) == 0
        assert safe_int("") == 0
        assert safe_int("12.5") == 0


class TestSafeIntOrNone:
    """Tests for the safe_int_or_none function."""

    def test_safe_int_or_none_converts_valid_string(self):
        """safe_int_or_none should convert valid strings to int."""
        assert safe_int_or_none("42") == 42
        assert safe_int_or_none("0") == 0
        assert safe_int_or_none("-5") == -5

    def test_safe_int_or_none_returns_none_for_invalid(self):
        """safe_int_or_none should return None for invalid input."""
        assert safe_int_or_none("abc") is None
        assert safe_int_or_none(None) is None
        assert safe_int_or_none("") is None
        assert safe_int_or_none("12.5") is None


class TestSortWithOverride:
    """Tests for the sort_with_override helper function."""

    def test_returns_three_ordering_clauses(self):
        """sort_with_override should return a 3-tuple of ordering clauses."""
        from app.models import Division
        result = sort_with_override(Division)
        assert len(result) == 3

    def test_items_with_priority_sort_before_null(self, db_session):
        """Items with sort_order set should appear before items with NULL."""
        from app.models import Division
        d1 = Division(code="AAA", name="Alpha", sort_order=None, is_active=True)
        d2 = Division(code="BBB", name="Beta", sort_order=1, is_active=True)
        d3 = Division(code="CCC", name="Charlie", sort_order=None, is_active=True)
        db_session.add_all([d1, d2, d3])
        db_session.flush()

        result = Division.query.order_by(*sort_with_override(Division)).all()
        assert result[0].code == "BBB"  # Has sort_order=1
        assert result[1].code == "AAA"  # NULL, alphabetical
        assert result[2].code == "CCC"  # NULL, alphabetical

    def test_multiple_priorities_ordered_by_value(self, db_session):
        """Items with sort_order should be ordered by that value."""
        from app.models import Division
        d1 = Division(code="AAA", name="Alpha", sort_order=2, is_active=True)
        d2 = Division(code="BBB", name="Beta", sort_order=1, is_active=True)
        db_session.add_all([d1, d2])
        db_session.flush()

        result = Division.query.order_by(*sort_with_override(Division)).all()
        assert result[0].code == "BBB"  # sort_order=1
        assert result[1].code == "AAA"  # sort_order=2

    def test_null_items_sort_alphabetically(self, db_session):
        """Items without sort_order should sort by name."""
        from app.models import Division
        d1 = Division(code="ZZZ", name="Zeta", sort_order=None, is_active=True)
        d2 = Division(code="AAA", name="Alpha", sort_order=None, is_active=True)
        d3 = Division(code="MMM", name="Mid", sort_order=None, is_active=True)
        db_session.add_all([d1, d2, d3])
        db_session.flush()

        result = Division.query.order_by(*sort_with_override(Division)).all()
        assert result[0].code == "AAA"  # Alpha
        assert result[1].code == "MMM"  # Mid
        assert result[2].code == "ZZZ"  # Zeta

    def test_custom_name_attr(self, db_session):
        """sort_with_override should accept a custom name attribute."""
        from app.models import SupplyItem, SupplyCategory
        cat = SupplyCategory(
            code="TESTCAT", name="Test Category", is_active=True,
        )
        db_session.add(cat)
        db_session.flush()

        item1 = SupplyItem(
            category_id=cat.id, item_name="Zebra Tape", unit="roll",
            sort_order=None, is_active=True,
        )
        item2 = SupplyItem(
            category_id=cat.id, item_name="Alpha Glue", unit="tube",
            sort_order=None, is_active=True,
        )
        db_session.add_all([item1, item2])
        db_session.flush()

        result = SupplyItem.query.order_by(
            *sort_with_override(SupplyItem, name_attr=SupplyItem.item_name)
        ).all()
        assert result[0].item_name == "Alpha Glue"
        assert result[1].item_name == "Zebra Tape"


class TestSafeRedirectUrl:
    """Tests for the safe_redirect_url function (open redirect prevention)."""

    def test_allows_relative_paths(self):
        assert safe_redirect_url("/admin/config") == "/admin/config"
        assert safe_redirect_url("/") == "/"
        assert safe_redirect_url("/some/deep/path?q=1") == "/some/deep/path?q=1"

    def test_rejects_external_urls(self):
        assert safe_redirect_url("https://attacker-site.com") == "/"
        assert safe_redirect_url("http://attacker-site.com/phish") == "/"

    def test_rejects_protocol_relative_urls(self):
        assert safe_redirect_url("//attacker-site.com") == "/"
        assert safe_redirect_url("//attacker-site.com/path") == "/"

    def test_rejects_javascript_urls(self):
        assert safe_redirect_url("javascript:alert(1)") == "/"

    def test_rejects_data_urls(self):
        assert safe_redirect_url("data:text/html,<h1>hi</h1>") == "/"

    def test_returns_fallback_for_empty(self):
        assert safe_redirect_url(None) == "/"
        assert safe_redirect_url("") == "/"
        assert safe_redirect_url("   ") == "/"

    def test_custom_fallback(self):
        assert safe_redirect_url("https://attacker-site.com", fallback="/dashboard") == "/dashboard"
        assert safe_redirect_url(None, fallback="/home") == "/home"
