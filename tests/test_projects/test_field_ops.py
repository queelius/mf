"""Tests for mf.projects.field_ops module."""

import json
import pytest

from mf.projects.field_ops import (
    FIELD_SCHEMA,
    ChangeResult,
    FieldDef,
    FieldType,
    coerce_value,
    modify_list_field,
    parse_field_path,
    set_project_field,
    unset_project_field,
    validate_field,
)


class TestParseFieldPath:
    """Tests for parse_field_path."""

    def test_simple_field(self):
        assert parse_field_path("stars") == ("stars", None)

    def test_dot_notation(self):
        assert parse_field_path("packages.pypi") == ("packages", "pypi")

    def test_dot_notation_nested(self):
        assert parse_field_path("external_docs.readthedocs") == ("external_docs", "readthedocs")

    def test_only_first_dot_splits(self):
        # "a.b.c" should split into ("a", "b.c")
        assert parse_field_path("a.b.c") == ("a", "b.c")


class TestCoerceValue:
    """Tests for coerce_value."""

    def test_string(self):
        fdef = FieldDef(FieldType.STRING, "test")
        assert coerce_value("hello", fdef) == "hello"

    def test_int_valid(self):
        fdef = FieldDef(FieldType.INT, "test")
        assert coerce_value("42", fdef) == 42

    def test_int_invalid(self):
        fdef = FieldDef(FieldType.INT, "test")
        with pytest.raises(ValueError, match="Expected integer"):
            coerce_value("not-a-number", fdef)

    def test_bool_true_variants(self):
        fdef = FieldDef(FieldType.BOOL, "test")
        for val in ("true", "True", "yes", "YES", "1", "on", "ON"):
            assert coerce_value(val, fdef) is True

    def test_bool_false_variants(self):
        fdef = FieldDef(FieldType.BOOL, "test")
        for val in ("false", "False", "no", "NO", "0", "off", "OFF"):
            assert coerce_value(val, fdef) is False

    def test_bool_invalid(self):
        fdef = FieldDef(FieldType.BOOL, "test")
        with pytest.raises(ValueError, match="Expected boolean"):
            coerce_value("maybe", fdef)

    def test_string_list_comma_separated(self):
        fdef = FieldDef(FieldType.STRING_LIST, "test")
        assert coerce_value("python,stats,ml", fdef) == ["python", "stats", "ml"]

    def test_string_list_json_array(self):
        fdef = FieldDef(FieldType.STRING_LIST, "test")
        assert coerce_value('["python", "stats"]', fdef) == ["python", "stats"]

    def test_string_list_strips_whitespace(self):
        fdef = FieldDef(FieldType.STRING_LIST, "test")
        assert coerce_value(" python , stats , ml ", fdef) == ["python", "stats", "ml"]

    def test_string_list_empty_items_filtered(self):
        fdef = FieldDef(FieldType.STRING_LIST, "test")
        assert coerce_value("a,,b,", fdef) == ["a", "b"]

    def test_dict_valid_json(self):
        fdef = FieldDef(FieldType.DICT, "test")
        result = coerce_value('{"key": "value"}', fdef)
        assert result == {"key": "value"}

    def test_dict_invalid_json(self):
        fdef = FieldDef(FieldType.DICT, "test")
        with pytest.raises(ValueError, match="Expected JSON object"):
            coerce_value("not-json", fdef)

    def test_dict_json_array_rejected(self):
        fdef = FieldDef(FieldType.DICT, "test")
        with pytest.raises(ValueError, match="Expected JSON object"):
            coerce_value("[1, 2, 3]", fdef)


class TestValidateField:
    """Tests for validate_field."""

    def test_unknown_field(self):
        errors = validate_field("nonexistent", "value")
        assert len(errors) == 1
        assert "Unknown field" in errors[0]

    def test_valid_int_in_range(self):
        errors = validate_field("stars", 3)
        assert errors == []

    def test_int_below_min(self):
        errors = validate_field("stars", -1)
        assert len(errors) == 1
        assert "below minimum" in errors[0]

    def test_int_above_max(self):
        errors = validate_field("stars", 10)
        assert len(errors) == 1
        assert "above maximum" in errors[0]

    def test_valid_choice(self):
        errors = validate_field("category", "library")
        assert errors == []

    def test_invalid_choice(self):
        errors = validate_field("category", "invalid-category")
        assert len(errors) == 1
        assert "not a valid choice" in errors[0]

    def test_dot_notation_on_dict_field(self):
        errors = validate_field("packages.pypi", "my-pkg")
        assert errors == []

    def test_dot_notation_on_non_dict_field(self):
        errors = validate_field("stars.sub", 5)
        assert len(errors) == 1
        assert "Dot notation only works on dict fields" in errors[0]

    def test_string_field_no_constraints(self):
        errors = validate_field("title", "My Project")
        assert errors == []


class TestFieldSchema:
    """Tests for FIELD_SCHEMA completeness."""

    def test_schema_has_core_fields(self):
        assert "title" in FIELD_SCHEMA
        assert "stars" in FIELD_SCHEMA
        assert "featured" in FIELD_SCHEMA
        assert "hide" in FIELD_SCHEMA
        assert "tags" in FIELD_SCHEMA
        assert "category" in FIELD_SCHEMA

    def test_schema_has_dict_fields(self):
        assert "packages" in FIELD_SCHEMA
        assert "external_docs" in FIELD_SCHEMA
        assert FIELD_SCHEMA["packages"].field_type == FieldType.DICT
        assert FIELD_SCHEMA["external_docs"].field_type == FieldType.DICT

    def test_stars_constraints(self):
        s = FIELD_SCHEMA["stars"]
        assert s.field_type == FieldType.INT
        assert s.min_val == 0
        assert s.max_val == 5

    def test_category_choices(self):
        s = FIELD_SCHEMA["category"]
        assert s.choices is not None
        assert "library" in s.choices


class TestSetProjectField:
    """Tests for set_project_field using a real ProjectsDatabase."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a ProjectsDatabase with test data."""
        from mf.core.database import ProjectsDatabase

        db_path = tmp_path / "projects_db.json"
        data = {
            "_comment": "test",
            "_schema_version": "2.0",
            "my-project": {
                "title": "My Project",
                "stars": 3,
                "tags": ["python"],
                "packages": {"pypi": "old-pkg"},
            },
        }
        db_path.write_text(json.dumps(data, indent=2))
        db = ProjectsDatabase(db_path)
        db.load()
        return db

    def test_set_simple_field(self, db):
        result = set_project_field(db, "my-project", "stars", 5)
        assert result.old_value == 3
        assert result.new_value == 5
        assert result.action == "set"
        assert db.get("my-project")["stars"] == 5

    def test_set_new_field(self, db):
        result = set_project_field(db, "my-project", "category", "library")
        assert result.old_value is None
        assert result.new_value == "library"
        assert db.get("my-project")["category"] == "library"

    def test_set_dot_notation(self, db):
        result = set_project_field(db, "my-project", "packages.pypi", "new-pkg")
        assert result.old_value == "old-pkg"
        assert result.new_value == "new-pkg"
        assert db.get("my-project")["packages"]["pypi"] == "new-pkg"

    def test_set_dot_notation_new_subkey(self, db):
        result = set_project_field(db, "my-project", "packages.npm", "my-npm-pkg")
        assert result.old_value is None
        assert result.new_value == "my-npm-pkg"
        # Original pypi should still be there
        pkgs = db.get("my-project")["packages"]
        assert pkgs["pypi"] == "old-pkg"
        assert pkgs["npm"] == "my-npm-pkg"

    def test_set_creates_project_entry(self, db):
        result = set_project_field(db, "new-project", "stars", 4)
        assert result.old_value is None
        assert result.new_value == 4
        assert db.get("new-project")["stars"] == 4


class TestUnsetProjectField:
    """Tests for unset_project_field."""

    @pytest.fixture
    def db(self, tmp_path):
        from mf.core.database import ProjectsDatabase

        db_path = tmp_path / "projects_db.json"
        data = {
            "_comment": "test",
            "my-project": {
                "title": "My Project",
                "stars": 3,
                "packages": {"pypi": "my-pkg", "npm": "my-npm"},
            },
        }
        db_path.write_text(json.dumps(data, indent=2))
        db = ProjectsDatabase(db_path)
        db.load()
        return db

    def test_unset_simple_field(self, db):
        result = unset_project_field(db, "my-project", "stars")
        assert result.old_value == 3
        assert result.new_value is None
        assert result.action == "unset"
        assert "stars" not in db.get("my-project")

    def test_unset_dot_notation(self, db):
        result = unset_project_field(db, "my-project", "packages.pypi")
        assert result.old_value == "my-pkg"
        # npm should still exist
        pkgs = db.get("my-project")["packages"]
        assert "pypi" not in pkgs
        assert pkgs["npm"] == "my-npm"

    def test_unset_dot_notation_last_key_removes_dict(self, db):
        # Remove both sub-keys
        unset_project_field(db, "my-project", "packages.pypi")
        unset_project_field(db, "my-project", "packages.npm")
        assert "packages" not in db.get("my-project")

    def test_unset_nonexistent_field(self, db):
        result = unset_project_field(db, "my-project", "nonexistent")
        assert result.old_value is None

    def test_unset_nonexistent_project_raises(self, db):
        with pytest.raises(KeyError, match="Project not found"):
            unset_project_field(db, "does-not-exist", "stars")


class TestModifyListField:
    """Tests for modify_list_field."""

    @pytest.fixture
    def db(self, tmp_path):
        from mf.core.database import ProjectsDatabase

        db_path = tmp_path / "projects_db.json"
        data = {
            "_comment": "test",
            "my-project": {
                "tags": ["python", "stats"],
            },
        }
        db_path.write_text(json.dumps(data, indent=2))
        db = ProjectsDatabase(db_path)
        db.load()
        return db

    def test_add_tags(self, db):
        result = modify_list_field(db, "my-project", "tags", add=["ml", "ai"])
        assert result.old_value == ["python", "stats"]
        assert result.new_value == ["python", "stats", "ml", "ai"]
        assert result.action == "add"

    def test_add_duplicate_tag_deduplicated(self, db):
        result = modify_list_field(db, "my-project", "tags", add=["python", "ml"])
        assert result.new_value == ["python", "stats", "ml"]

    def test_remove_tags(self, db):
        result = modify_list_field(db, "my-project", "tags", remove=["stats"])
        assert result.new_value == ["python"]
        assert result.action == "remove"

    def test_replace_tags(self, db):
        result = modify_list_field(db, "my-project", "tags", replace=["a", "b"])
        assert result.new_value == ["a", "b"]
        assert result.action == "replace"

    def test_add_and_remove(self, db):
        result = modify_list_field(db, "my-project", "tags", add=["ml"], remove=["stats"])
        assert "ml" in result.new_value
        assert "stats" not in result.new_value
        assert "python" in result.new_value

    def test_replace_overrides_add_remove(self, db):
        result = modify_list_field(db, "my-project", "tags", add=["ml"], remove=["stats"], replace=["only"])
        assert result.new_value == ["only"]

    def test_unknown_field_raises(self, db):
        with pytest.raises(ValueError, match="Unknown field"):
            modify_list_field(db, "my-project", "nonexistent", add=["x"])

    def test_non_list_field_raises(self, db):
        with pytest.raises(ValueError, match="not a list"):
            modify_list_field(db, "my-project", "stars", add=["x"])

    def test_add_to_empty_project(self, db):
        result = modify_list_field(db, "new-project", "tags", add=["first"])
        assert result.old_value == []
        assert result.new_value == ["first"]


class TestChangeResult:
    """Tests for ChangeResult dataclass."""

    def test_creation(self):
        r = ChangeResult(slug="proj", field="stars", old_value=1, new_value=5, action="set")
        assert r.slug == "proj"
        assert r.field == "stars"
        assert r.old_value == 1
        assert r.new_value == 5
        assert r.action == "set"
