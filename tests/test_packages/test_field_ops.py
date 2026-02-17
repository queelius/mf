"""Tests for mf.packages.field_ops -- package-specific field operations."""

import json

import pytest

from mf.core.field_ops import FieldType
from mf.packages.field_ops import (
    PACKAGES_SCHEMA,
    modify_package_list_field,
    set_package_field,
    unset_package_field,
    validate_package_field,
)


# ---------------------------------------------------------------------------
# Schema completeness
# ---------------------------------------------------------------------------


class TestPackagesSchema:
    def test_has_core_fields(self):
        for field in ("name", "registry", "project", "description", "latest_version",
                       "install_command", "registry_url", "license"):
            assert field in PACKAGES_SCHEMA, f"Missing core field: {field}"

    def test_has_classification_fields(self):
        for field in ("tags", "featured", "stars"):
            assert field in PACKAGES_SCHEMA, f"Missing classification field: {field}"

    def test_registry_choices(self):
        s = PACKAGES_SCHEMA["registry"]
        assert s.choices is not None
        assert "pypi" in s.choices
        assert "cran" in s.choices

    def test_stars_range(self):
        s = PACKAGES_SCHEMA["stars"]
        assert s.field_type == FieldType.INT
        assert s.min_val == 0
        assert s.max_val == 5

    def test_downloads_is_int(self):
        assert PACKAGES_SCHEMA["downloads"].field_type == FieldType.INT

    def test_field_count(self):
        """Verify we have roughly the expected number of fields."""
        assert len(PACKAGES_SCHEMA) >= 13


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_registry(self):
        assert validate_package_field("registry", "pypi") == []

    def test_invalid_registry(self):
        errors = validate_package_field("registry", "npm")
        assert any("not a valid choice" in e for e in errors)

    def test_valid_stars(self):
        assert validate_package_field("stars", 3) == []

    def test_invalid_stars(self):
        errors = validate_package_field("stars", 10)
        assert any("above maximum" in e for e in errors)


# ---------------------------------------------------------------------------
# set / unset / modify using real PackageDatabase
# ---------------------------------------------------------------------------


@pytest.fixture
def pkg_db(tmp_path):
    """Create a PackageDatabase with one test entry."""
    from mf.packages.database import PackageDatabase

    db_path = tmp_path / "packages_db.json"
    data = {
        "_comment": "test",
        "_schema_version": "1.0",
        "foo": {
            "name": "foo-pkg",
            "registry": "pypi",
            "description": "A test package",
            "featured": False,
            "tags": ["python", "testing"],
        },
    }
    db_path.write_text(json.dumps(data, indent=2))
    db = PackageDatabase(db_path)
    db.load()
    return db


class TestSetUnset:
    def test_set_field(self, pkg_db):
        result = set_package_field(pkg_db, "foo", "description", "Updated description")
        assert result.old_value == "A test package"
        assert result.new_value == "Updated description"
        entry = pkg_db.get("foo")
        assert entry.data["description"] == "Updated description"

    def test_unset_field(self, pkg_db):
        result = unset_package_field(pkg_db, "foo", "description")
        assert result.old_value == "A test package"
        assert "description" not in pkg_db.get("foo").data

    def test_unset_nonexistent_package_raises(self, pkg_db):
        with pytest.raises(KeyError, match="Package not found"):
            unset_package_field(pkg_db, "nope", "name")

    def test_modify_tags(self, pkg_db):
        result = modify_package_list_field(pkg_db, "foo", "tags", add=["data", "cli"])
        assert "data" in result.new_value
        assert "cli" in result.new_value
        assert "python" in result.new_value
        assert "testing" in result.new_value
