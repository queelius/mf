from pathlib import Path

from mf.core.frontmatter import (
    compute_body_hash,
    frontmatter_equal,
    parse_post,
    parse_text,
)


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_text_splits_frontmatter_and_body():
    fm, body = parse_text('---\ntitle: "Hi"\ntags:\n  - a\n---\n\nHello world\n')
    assert fm["title"] == "Hi"
    assert fm["tags"] == ["a"]
    assert body.strip() == "Hello world"


def test_parse_post_reads_index_md_from_dir(tmp_path):
    _write(tmp_path / "index.md", '---\ntitle: "Hi"\n---\n\nBody\n')
    fm, body = parse_post(tmp_path)
    assert fm["title"] == "Hi"
    assert body.strip() == "Body"


def test_parse_post_missing_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_post(tmp_path / "nope")


def test_parse_text_and_parse_post_agree(tmp_path):
    text = '---\ntitle: "Hi"\n---\n\nSame body\n'
    _write(tmp_path / "index.md", text)
    assert parse_text(text) == parse_post(tmp_path)


def test_compute_body_hash_ignores_frontmatter(tmp_path):
    a = _write(tmp_path / "a" / "index.md", '---\ntitle: "A"\n---\n\nbody\n')
    b = _write(tmp_path / "b" / "index.md", '---\ntitle: "B"\ntts: true\n---\n\nbody\n')
    assert compute_body_hash(a.parent) == compute_body_hash(b.parent)


def test_frontmatter_equal_is_order_insensitive():
    assert frontmatter_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})
    assert not frontmatter_equal({"a": 1}, {"a": 2})
