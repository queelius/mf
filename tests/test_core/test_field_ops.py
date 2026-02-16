"""Tests for mf.core.field_ops -- shared field operations infrastructure."""

import json
import pytest

from mf.core.field_ops import (
    ChangeResult,
    DictDatabaseAdapter,
    EntryDatabaseAdapter,
    FieldDef,
    FieldType,
    coerce_value,
    modify_list_field,
    parse_field_path,
    set_field,
    unset_field,
    validate_field,
)


# ---------------------------------------------------------------------------
# Mock schema for testing (independent of any domain)
# ---------------------------------------------------------------------------

MOCK_SCHEMA: dict[str, FieldDef] = {
    "title": FieldDef(FieldType.STRING, "Title"),
    "count": FieldDef(FieldType.INT, "A count", min_val=0, max_val=100),
    "enabled": FieldDef(FieldType.BOOL, "On/off toggle"),
    "tags": FieldDef(FieldType.STRING_LIST, "Tags"),
    "meta": FieldDef(FieldType.DICT, "Metadata dict"),
    "kind": FieldDef(FieldType.STRING, "Kind", choices=["alpha", "beta", "gamma"]),
}


# ---------------------------------------------------------------------------
# parse_field_path
# ---------------------------------------------------------------------------


class TestParseFieldPath:
    def test_simple(self):
        assert parse_field_path("title") == ("title", None)

    def test_dot_notation(self):
        assert parse_field_path("meta.key") == ("meta", "key")

    def test_only_first_dot(self):
        assert parse_field_path("a.b.c") == ("a", "b.c")


# ---------------------------------------------------------------------------
# coerce_value
# ---------------------------------------------------------------------------


class TestCoerceValue:
    def test_string(self):
        assert coerce_value("hello", FieldDef(FieldType.STRING, "")) == "hello"

    def test_int_valid(self):
        assert coerce_value("42", FieldDef(FieldType.INT, "")) == 42

    def test_int_invalid(self):
        with pytest.raises(ValueError, match="Expected integer"):
            coerce_value("nope", FieldDef(FieldType.INT, ""))

    def test_bool_true(self):
        fdef = FieldDef(FieldType.BOOL, "")
        for v in ("true", "yes", "1", "on"):
            assert coerce_value(v, fdef) is True

    def test_bool_false(self):
        fdef = FieldDef(FieldType.BOOL, "")
        for v in ("false", "no", "0", "off"):
            assert coerce_value(v, fdef) is False

    def test_bool_invalid(self):
        with pytest.raises(ValueError, match="Expected boolean"):
            coerce_value("maybe", FieldDef(FieldType.BOOL, ""))

    def test_string_list_csv(self):
        assert coerce_value("a,b,c", FieldDef(FieldType.STRING_LIST, "")) == ["a", "b", "c"]

    def test_string_list_json(self):
        assert coerce_value('["a","b"]', FieldDef(FieldType.STRING_LIST, "")) == ["a", "b"]

    def test_dict_valid(self):
        assert coerce_value('{"k":"v"}', FieldDef(FieldType.DICT, "")) == {"k": "v"}

    def test_dict_invalid(self):
        with pytest.raises(ValueError, match="Expected JSON object"):
            coerce_value("bad", FieldDef(FieldType.DICT, ""))


# ---------------------------------------------------------------------------
# validate_field (with mock schema)
# ---------------------------------------------------------------------------


class TestValidateField:
    def test_unknown_field(self):
        errors = validate_field("bogus", "x", MOCK_SCHEMA)
        assert any("Unknown field" in e for e in errors)

    def test_int_in_range(self):
        assert validate_field("count", 50, MOCK_SCHEMA) == []

    def test_int_below_min(self):
        errors = validate_field("count", -1, MOCK_SCHEMA)
        assert any("below minimum" in e for e in errors)

    def test_int_above_max(self):
        errors = validate_field("count", 200, MOCK_SCHEMA)
        assert any("above maximum" in e for e in errors)

    def test_valid_choice(self):
        assert validate_field("kind", "alpha", MOCK_SCHEMA) == []

    def test_invalid_choice(self):
        errors = validate_field("kind", "delta", MOCK_SCHEMA)
        assert any("not a valid choice" in e for e in errors)

    def test_dot_on_dict(self):
        assert validate_field("meta.key", "x", MOCK_SCHEMA) == []

    def test_dot_on_non_dict(self):
        errors = validate_field("count.sub", 1, MOCK_SCHEMA)
        assert any("Dot notation" in e for e in errors)


# ---------------------------------------------------------------------------
# DictDatabaseAdapter (wraps ProjectsDatabase-like objects)
# ---------------------------------------------------------------------------


class FakeProjectsDB:
    """Minimal stand-in for ProjectsDatabase (get returns dict)."""

    def __init__(self):
        self._data = {}

    def get(self, slug):
        return self._data.get(slug)

    def set(self, slug, data):
        self._data[slug] = data

    def update(self, slug, **kwargs):
        if slug not in self._data:
            self._data[slug] = {}
        self._data[slug].update(kwargs)

    def __contains__(self, slug):
        return slug in self._data


class TestDictDatabaseAdapter:
    def test_get_data(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"title": "T"}
        adapter = DictDatabaseAdapter(fdb)
        assert adapter.get_data("s") == {"title": "T"}
        assert adapter.get_data("missing") is None

    def test_update_data(self):
        fdb = FakeProjectsDB()
        adapter = DictDatabaseAdapter(fdb)
        adapter.update_data("s", title="T")
        assert fdb._data["s"]["title"] == "T"

    def test_set_data(self):
        fdb = FakeProjectsDB()
        adapter = DictDatabaseAdapter(fdb)
        adapter.set_data("s", {"title": "T"})
        assert fdb._data["s"] == {"title": "T"}

    def test_contains(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {}
        adapter = DictDatabaseAdapter(fdb)
        assert "s" in adapter
        assert "missing" not in adapter


# ---------------------------------------------------------------------------
# EntryDatabaseAdapter (wraps PaperDatabase/SeriesDatabase-like objects)
# ---------------------------------------------------------------------------


class FakeEntry:
    def __init__(self, data):
        self.data = data


class FakeEntryDB:
    """Minimal stand-in for PaperDatabase/SeriesDatabase (get returns Entry)."""

    def __init__(self):
        self._data = {}

    def get(self, slug):
        if slug not in self._data:
            return None
        return FakeEntry(self._data[slug])

    def set(self, slug, data):
        self._data[slug] = data

    def update(self, slug, **kwargs):
        if slug not in self._data:
            self._data[slug] = {}
        self._data[slug].update(kwargs)

    def __contains__(self, slug):
        return slug in self._data


class TestEntryDatabaseAdapter:
    def test_get_data(self):
        fdb = FakeEntryDB()
        fdb._data["s"] = {"title": "T"}
        adapter = EntryDatabaseAdapter(fdb)
        assert adapter.get_data("s") == {"title": "T"}
        assert adapter.get_data("missing") is None

    def test_update_data(self):
        fdb = FakeEntryDB()
        adapter = EntryDatabaseAdapter(fdb)
        adapter.update_data("s", title="T")
        assert fdb._data["s"]["title"] == "T"

    def test_set_data(self):
        fdb = FakeEntryDB()
        adapter = EntryDatabaseAdapter(fdb)
        adapter.set_data("s", {"title": "T"})
        assert fdb._data["s"] == {"title": "T"}

    def test_contains(self):
        fdb = FakeEntryDB()
        fdb._data["s"] = {}
        adapter = EntryDatabaseAdapter(fdb)
        assert "s" in adapter
        assert "missing" not in adapter


# ---------------------------------------------------------------------------
# Generic set_field / unset_field / modify_list_field
# ---------------------------------------------------------------------------


class TestSetField:
    def test_set_simple(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"title": "Old"}
        adapter = DictDatabaseAdapter(fdb)
        result = set_field(adapter, "s", "title", "New")
        assert result.old_value == "Old"
        assert result.new_value == "New"
        assert fdb._data["s"]["title"] == "New"

    def test_set_dot_notation(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"meta": {"k": "v1"}}
        adapter = DictDatabaseAdapter(fdb)
        result = set_field(adapter, "s", "meta.k", "v2")
        assert result.old_value == "v1"
        assert result.new_value == "v2"
        assert fdb._data["s"]["meta"]["k"] == "v2"

    def test_set_creates_entry(self):
        fdb = FakeProjectsDB()
        adapter = DictDatabaseAdapter(fdb)
        result = set_field(adapter, "new", "title", "Brand New")
        assert result.old_value is None
        assert fdb._data["new"]["title"] == "Brand New"

    def test_set_on_entry_adapter(self):
        fdb = FakeEntryDB()
        fdb._data["s"] = {"count": 1}
        adapter = EntryDatabaseAdapter(fdb)
        result = set_field(adapter, "s", "count", 2)
        assert result.old_value == 1
        assert fdb._data["s"]["count"] == 2


class TestUnsetField:
    def test_unset_simple(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"title": "T", "count": 5}
        adapter = DictDatabaseAdapter(fdb)
        result = unset_field(adapter, "s", "count")
        assert result.old_value == 5
        assert "count" not in fdb._data["s"]

    def test_unset_dot_notation(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"meta": {"a": 1, "b": 2}}
        adapter = DictDatabaseAdapter(fdb)
        result = unset_field(adapter, "s", "meta.a")
        assert result.old_value == 1
        assert "a" not in fdb._data["s"]["meta"]
        assert fdb._data["s"]["meta"]["b"] == 2

    def test_unset_missing_entry_raises(self):
        fdb = FakeProjectsDB()
        adapter = DictDatabaseAdapter(fdb)
        with pytest.raises(KeyError, match="Entry not found"):
            unset_field(adapter, "nope", "title")

    def test_unset_on_entry_adapter(self):
        fdb = FakeEntryDB()
        fdb._data["s"] = {"title": "T", "count": 5}
        adapter = EntryDatabaseAdapter(fdb)
        result = unset_field(adapter, "s", "count")
        assert result.old_value == 5
        assert "count" not in fdb._data["s"]


class TestModifyListField:
    def test_add(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"tags": ["a"]}
        adapter = DictDatabaseAdapter(fdb)
        result = modify_list_field(adapter, "s", "tags", add=["b"], schema=MOCK_SCHEMA)
        assert result.new_value == ["a", "b"]

    def test_remove(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"tags": ["a", "b"]}
        adapter = DictDatabaseAdapter(fdb)
        result = modify_list_field(adapter, "s", "tags", remove=["a"], schema=MOCK_SCHEMA)
        assert result.new_value == ["b"]

    def test_replace(self):
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"tags": ["a"]}
        adapter = DictDatabaseAdapter(fdb)
        result = modify_list_field(adapter, "s", "tags", replace=["x", "y"], schema=MOCK_SCHEMA)
        assert result.new_value == ["x", "y"]

    def test_unknown_field_raises(self):
        fdb = FakeProjectsDB()
        adapter = DictDatabaseAdapter(fdb)
        with pytest.raises(ValueError, match="Unknown field"):
            modify_list_field(adapter, "s", "bogus", add=["x"], schema=MOCK_SCHEMA)

    def test_non_list_field_raises(self):
        fdb = FakeProjectsDB()
        adapter = DictDatabaseAdapter(fdb)
        with pytest.raises(ValueError, match="not a list"):
            modify_list_field(adapter, "s", "count", add=["x"], schema=MOCK_SCHEMA)

    def test_add_on_entry_adapter(self):
        fdb = FakeEntryDB()
        fdb._data["s"] = {"tags": ["a"]}
        adapter = EntryDatabaseAdapter(fdb)
        result = modify_list_field(adapter, "s", "tags", add=["b"], schema=MOCK_SCHEMA)
        assert result.new_value == ["a", "b"]


# ---------------------------------------------------------------------------
# ChangeResult
# ---------------------------------------------------------------------------


class TestChangeResult:
    def test_creation(self):
        r = ChangeResult(slug="s", field="f", old_value=1, new_value=2, action="set")
        assert r.slug == "s"
        assert r.action == "set"


# ---------------------------------------------------------------------------
# Regression: set_field with schema validation (Fix #7)
# ---------------------------------------------------------------------------


class TestSetFieldWithSchema:
    def test_set_field_rejects_invalid_with_schema(self):
        """set_field should raise ValueError when schema validation fails."""
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"count": 5}
        adapter = DictDatabaseAdapter(fdb)
        with pytest.raises(ValueError, match="above maximum"):
            set_field(adapter, "s", "count", 999, schema=MOCK_SCHEMA)

    def test_set_field_passes_valid_with_schema(self):
        """set_field should succeed when schema validation passes."""
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"count": 5}
        adapter = DictDatabaseAdapter(fdb)
        result = set_field(adapter, "s", "count", 50, schema=MOCK_SCHEMA)
        assert result.new_value == 50

    def test_set_field_without_schema_skips_validation(self):
        """set_field without schema should not validate (backward compat)."""
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"count": 5}
        adapter = DictDatabaseAdapter(fdb)
        # 999 exceeds max_val=100 but no schema provided → no error
        result = set_field(adapter, "s", "count", 999)
        assert result.new_value == 999


# ---------------------------------------------------------------------------
# Regression: unset_field does not mutate source dict (Fix #8)
# ---------------------------------------------------------------------------


class TestUnsetFieldNoMutation:
    def test_unset_dot_field_does_not_mutate_source(self):
        """Unsetting a dot-notation field that empties a dict must not
        mutate the dict returned by get_data()."""
        fdb = FakeEntryDB()
        fdb._data["s"] = {"meta": {"only_key": "val"}, "title": "T"}
        adapter = EntryDatabaseAdapter(fdb)

        # Grab reference before unset
        original_data = adapter.get_data("s")
        original_meta_ref = original_data.get("meta")

        unset_field(adapter, "s", "meta.only_key")

        # The original_meta_ref should still have its key
        # (the unset should have worked on a copy)
        assert "only_key" in original_meta_ref

    def test_unset_top_level_does_not_mutate_source(self):
        """Unsetting a top-level field must not mutate the original dict."""
        fdb = FakeEntryDB()
        fdb._data["s"] = {"title": "T", "count": 5}
        adapter = EntryDatabaseAdapter(fdb)

        original_data = adapter.get_data("s")

        unset_field(adapter, "s", "count")

        # The original_data reference should still have 'count'
        assert "count" in original_data


# ---------------------------------------------------------------------------
# Regression: efficient list deduplication (Fix #15)
# ---------------------------------------------------------------------------


class TestListDeduplication:
    def test_add_deduplicates(self):
        """Adding items that already exist should not create duplicates."""
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"tags": ["a", "b"]}
        adapter = DictDatabaseAdapter(fdb)
        result = modify_list_field(
            adapter, "s", "tags", add=["b", "c", "a"], schema=MOCK_SCHEMA
        )
        assert result.new_value == ["a", "b", "c"]

    def test_remove_uses_set_lookup(self):
        """Remove should handle large lists efficiently (set-based)."""
        fdb = FakeProjectsDB()
        fdb._data["s"] = {"tags": [f"tag-{i}" for i in range(100)]}
        adapter = DictDatabaseAdapter(fdb)
        result = modify_list_field(
            adapter, "s", "tags",
            remove=[f"tag-{i}" for i in range(50)],
            schema=MOCK_SCHEMA,
        )
        assert len(result.new_value) == 50
        assert result.new_value[0] == "tag-50"
