"""Tests for mf.series.field_ops -- series-specific field operations."""

import json
import pytest

from mf.series.field_ops import (
    SERIES_SCHEMA,
    modify_series_list_field,
    set_series_field,
    unset_series_field,
    validate_series_field,
)
from mf.core.field_ops import FieldType


# ---------------------------------------------------------------------------
# Schema completeness
# ---------------------------------------------------------------------------


class TestSeriesSchema:
    def test_has_core_fields(self):
        for field in ("title", "description", "created_date"):
            assert field in SERIES_SCHEMA, f"Missing core field: {field}"

    def test_has_status_fields(self):
        assert "status" in SERIES_SCHEMA
        assert "featured" in SERIES_SCHEMA
        assert SERIES_SCHEMA["featured"].field_type == FieldType.BOOL

    def test_has_classification_fields(self):
        for field in ("tags", "color", "icon"):
            assert field in SERIES_SCHEMA, f"Missing classification field: {field}"

    def test_has_related_fields(self):
        assert "related_projects" in SERIES_SCHEMA
        assert SERIES_SCHEMA["related_projects"].field_type == FieldType.STRING_LIST

    def test_has_associations(self):
        assert "associations" in SERIES_SCHEMA
        assert SERIES_SCHEMA["associations"].field_type == FieldType.DICT

    def test_has_source_fields(self):
        for field in ("source_dir", "posts_subdir", "landing_page"):
            assert field in SERIES_SCHEMA, f"Missing source field: {field}"

    def test_status_choices(self):
        s = SERIES_SCHEMA["status"]
        assert s.choices is not None
        assert "active" in s.choices
        assert "completed" in s.choices
        assert "archived" in s.choices

    def test_field_count(self):
        """Verify we have roughly the expected number of fields."""
        assert len(SERIES_SCHEMA) >= 12


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateSeriesField:
    def test_valid_status(self):
        assert validate_series_field("status", "active") == []

    def test_invalid_status(self):
        errors = validate_series_field("status", "bogus")
        assert any("not a valid choice" in e for e in errors)

    def test_valid_string_field(self):
        assert validate_series_field("title", "My Series") == []

    def test_unknown_field(self):
        errors = validate_series_field("nonexistent", "x")
        assert any("Unknown field" in e for e in errors)

    def test_dot_on_dict_field(self):
        assert validate_series_field("associations.papers", ["paper1"]) == []


# ---------------------------------------------------------------------------
# set / unset / modify using real SeriesDatabase
# ---------------------------------------------------------------------------


@pytest.fixture
def series_db(tmp_path):
    """Create a SeriesDatabase with test data."""
    from mf.core.database import SeriesDatabase

    db_path = tmp_path / "series_db.json"
    data = {
        "_comment": "test",
        "_schema_version": "1.3",
        "test-series": {
            "title": "Test Series",
            "status": "active",
            "featured": False,
            "tags": ["math", "computing"],
            "color": "#667eea",
        },
    }
    db_path.write_text(json.dumps(data, indent=2))
    db = SeriesDatabase(db_path)
    db.load()
    return db


class TestSetSeriesField:
    def test_set_simple(self, series_db):
        result = set_series_field(series_db, "test-series", "status", "completed")
        assert result.old_value == "active"
        assert result.new_value == "completed"
        entry = series_db.get("test-series")
        assert entry.data["status"] == "completed"

    def test_set_new_field(self, series_db):
        result = set_series_field(series_db, "test-series", "icon", "book")
        assert result.old_value is None
        assert result.new_value == "book"

    def test_set_creates_entry(self, series_db):
        result = set_series_field(series_db, "new-series", "title", "New Series")
        assert result.old_value is None
        entry = series_db.get("new-series")
        assert entry.data["title"] == "New Series"

    def test_set_bool_field(self, series_db):
        result = set_series_field(series_db, "test-series", "featured", True)
        assert result.old_value is False
        assert result.new_value is True


class TestUnsetSeriesField:
    def test_unset_field(self, series_db):
        result = unset_series_field(series_db, "test-series", "color")
        assert result.old_value == "#667eea"
        assert "color" not in series_db.get("test-series").data

    def test_unset_nonexistent_series_raises(self, series_db):
        with pytest.raises(KeyError, match="Series not found"):
            unset_series_field(series_db, "nope", "title")

    def test_unset_absent_field(self, series_db):
        result = unset_series_field(series_db, "test-series", "icon")
        assert result.old_value is None


class TestModifySeriesListField:
    def test_add_tags(self, series_db):
        result = modify_series_list_field(series_db, "test-series", "tags", add=["philosophy"])
        assert "philosophy" in result.new_value
        assert "math" in result.new_value

    def test_remove_tags(self, series_db):
        result = modify_series_list_field(series_db, "test-series", "tags", remove=["computing"])
        assert "computing" not in result.new_value
        assert "math" in result.new_value

    def test_replace_tags(self, series_db):
        result = modify_series_list_field(series_db, "test-series", "tags", replace=["x", "y"])
        assert result.new_value == ["x", "y"]

    def test_add_related_projects(self, series_db):
        result = modify_series_list_field(
            series_db, "test-series", "related_projects", add=["project-a"]
        )
        assert result.new_value == ["project-a"]
