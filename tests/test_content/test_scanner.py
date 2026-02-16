"""Tests for the ContentScanner and ContentItem classes."""

import os

import pytest
import yaml

from mf.content.scanner import ContentItem, ContentScanner


# ---------------------------------------------------------------------------
# ContentItem property tests
# ---------------------------------------------------------------------------

def test_content_item_title_from_front_matter():
    """Test that title is read from front matter."""
    item = ContentItem(
        path="/fake/path.md",
        slug="my-post",
        content_type="post",
        front_matter={"title": "My Custom Title"},
    )
    assert item.title == "My Custom Title"


def test_content_item_title_fallback_to_slug():
    """Test that title falls back to slug when not in front matter."""
    item = ContentItem(
        path="/fake/path.md",
        slug="fallback-slug",
        content_type="post",
        front_matter={},
    )
    assert item.title == "fallback-slug"


def test_content_item_date_property():
    """Test date property returns front matter date or None."""
    item_with = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"date": "2024-06-15"},
    )
    item_without = ContentItem(
        path="/f", slug="s", content_type="post", front_matter={},
    )
    assert item_with.date == "2024-06-15"
    assert item_without.date is None


def test_content_item_tags():
    """Test tags property returns list from front matter."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"tags": ["python", "testing"]},
    )
    assert item.tags == ["python", "testing"]


def test_content_item_tags_default_empty():
    """Test tags property returns empty list when missing."""
    item = ContentItem(path="/f", slug="s", content_type="post", front_matter={})
    assert item.tags == []


def test_content_item_categories_list():
    """Test categories as a list."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"categories": ["tech", "science"]},
    )
    assert item.categories == ["tech", "science"]


def test_content_item_categories_string_coerced_to_list():
    """Test a single-string category is wrapped in a list."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"categories": "solo"},
    )
    assert item.categories == ["solo"]


def test_content_item_projects_list():
    """Test projects returns linked_project taxonomy."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"linked_project": ["ctk", "likelihood.model"]},
    )
    assert item.projects == ["ctk", "likelihood.model"]


def test_content_item_projects_string_coerced():
    """Test single-string linked_project is wrapped."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"linked_project": "my-proj"},
    )
    assert item.projects == ["my-proj"]


def test_content_item_is_draft():
    """Test is_draft property."""
    draft = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"draft": True},
    )
    published = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"draft": False},
    )
    no_field = ContentItem(
        path="/f", slug="s", content_type="post", front_matter={},
    )
    assert draft.is_draft is True
    assert published.is_draft is False
    assert no_field.is_draft is False


def test_content_item_hugo_path():
    """Test hugo_path construction."""
    item = ContentItem(
        path="/f", slug="2024-01-hello-world", content_type="post",
        front_matter={},
    )
    assert item.hugo_path == "/post/2024-01-hello-world/"


def test_content_item_mentions_text_case_insensitive():
    """Test mentions_text with default case-insensitive search."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"title": "Great Title"},
        body="Some body text about Python.",
    )
    assert item.mentions_text("python") is True
    assert item.mentions_text("PYTHON") is True
    assert item.mentions_text("great") is True
    assert item.mentions_text("missing") is False


def test_content_item_mentions_text_case_sensitive():
    """Test mentions_text with case sensitivity on."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={"title": "Great Title"},
        body="Some body text about Python.",
    )
    assert item.mentions_text("Python", case_sensitive=True) is True
    assert item.mentions_text("python", case_sensitive=True) is False


def test_content_item_contains_url():
    """Test contains_url checks body for URL pattern."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={},
        body="Check out https://github.com/queelius/ctk for details.",
    )
    assert item.contains_url("github.com/queelius/ctk") is True
    assert item.contains_url("github.com/other/repo") is False


def test_content_item_extract_github_urls():
    """Test extraction of GitHub URLs from body."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={},
        body=(
            "Visit https://github.com/queelius/ctk and also "
            "https://github.com/queelius/likelihood.model for more."
        ),
    )
    urls = item.extract_github_urls()
    assert len(urls) == 2
    assert "https://github.com/queelius/ctk" in urls
    assert "https://github.com/queelius/likelihood.model" in urls


def test_content_item_extract_github_urls_deduplicates():
    """Test that duplicate GitHub URLs are deduplicated."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={},
        body="See https://github.com/user/repo and again https://github.com/user/repo here.",
    )
    urls = item.extract_github_urls()
    assert len(urls) == 1


def test_content_item_extract_internal_links():
    """Test extraction of internal Hugo links."""
    item = ContentItem(
        path="/f", slug="s", content_type="post",
        front_matter={},
        body="See [my post](/post/2024-hello/) and [paper](/papers/my-paper/).",
    )
    links = item.extract_internal_links()
    assert "/post/2024-hello/" in links
    assert "/papers/my-paper/" in links


# ---------------------------------------------------------------------------
# ContentScanner tests
# ---------------------------------------------------------------------------

def test_scanner_scan_all_empty_site(mock_site_root):
    """Test scanning an empty site returns empty list."""
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_all()
    assert items == []


def test_scanner_scan_type_leaf_bundle(create_content_file, mock_site_root):
    """Test scanning picks up a leaf bundle (slug/index.md)."""
    create_content_file(content_type="post", slug="hello-world", title="Hello World")
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post")
    assert len(items) == 1
    assert items[0].slug == "hello-world"
    assert items[0].title == "Hello World"


def test_scanner_scan_type_branch_bundle(mock_site_root):
    """Test scanning picks up a branch bundle (slug/_index.md)."""
    proj_dir = mock_site_root / "content" / "projects" / "my-project"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "_index.md").write_text(
        "---\ntitle: My Project\ndate: 2024-01-01\n---\nProject body.\n"
    )
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("projects")
    assert len(items) == 1
    assert items[0].slug == "my-project"


def test_scanner_scan_type_single_file(mock_site_root):
    """Test scanning picks up a single .md file (not in a subdirectory)."""
    post_file = mock_site_root / "content" / "post" / "simple-post.md"
    post_file.write_text(
        "---\ntitle: Simple Post\ndate: 2024-01-01\n---\nSimple body.\n"
    )
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post")
    assert len(items) == 1
    assert items[0].slug == "simple-post"


def test_scanner_skips_drafts_by_default(create_content_file, mock_site_root):
    """Test that drafts are excluded by default."""
    create_content_file(slug="published", title="Published", draft=False)
    create_content_file(slug="draft-post", title="Draft", draft=True)
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post")
    assert len(items) == 1
    assert items[0].slug == "published"


def test_scanner_includes_drafts_when_requested(create_content_file, mock_site_root):
    """Test that drafts are included when include_drafts=True."""
    create_content_file(slug="published", title="Published", draft=False)
    create_content_file(slug="draft-post", title="Draft", draft=True)
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post", include_drafts=True)
    assert len(items) == 2


def test_scanner_skips_symlinks(mock_site_root):
    """Test that symlinks are skipped during scanning."""
    # Create a real content file
    real_dir = mock_site_root / "content" / "post" / "real-post"
    real_dir.mkdir(parents=True, exist_ok=True)
    (real_dir / "index.md").write_text(
        "---\ntitle: Real Post\ndate: 2024-01-01\n---\nReal body.\n"
    )

    # Create a symlink pointing to the real file
    link_dir = mock_site_root / "content" / "post" / "link-post"
    link_dir.mkdir(parents=True, exist_ok=True)
    link_target = link_dir / "index.md"
    os.symlink(real_dir / "index.md", link_target)

    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post")
    slugs = [i.slug for i in items]
    assert "real-post" in slugs
    assert "link-post" not in slugs


def test_scanner_skips_dotfiles(mock_site_root):
    """Test that files starting with '.' are skipped."""
    post_dir = mock_site_root / "content" / "post" / "normal-post"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.md").write_text(
        "---\ntitle: Normal\ndate: 2024-01-01\n---\nBody.\n"
    )
    (post_dir / ".hidden.md").write_text(
        "---\ntitle: Hidden\ndate: 2024-01-01\n---\nHidden body.\n"
    )

    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post")
    assert len(items) == 1
    assert items[0].title == "Normal"


def test_scanner_skips_section_index(mock_site_root):
    """Test that the top-level _index.md in the section dir is skipped."""
    section_dir = mock_site_root / "content" / "post"
    (section_dir / "_index.md").write_text(
        "---\ntitle: Posts\n---\nSection page.\n"
    )
    # Real post
    post_dir = section_dir / "real-post"
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.md").write_text(
        "---\ntitle: Real\ndate: 2024-01-01\n---\nBody.\n"
    )

    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("post")
    assert len(items) == 1
    assert items[0].slug == "real-post"


def test_scanner_scan_all_multiple_types(create_content_file, mock_site_root):
    """Test scan_all returns items from multiple content types."""
    create_content_file(content_type="post", slug="blog-post", title="Blog")
    # Create a paper
    paper_dir = mock_site_root / "content" / "papers" / "my-paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "index.md").write_text(
        "---\ntitle: My Paper\ndate: 2024-01-01\n---\nPaper body.\n"
    )

    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_all()
    types_found = {i.content_type for i in items}
    assert "post" in types_found
    assert "papers" in types_found


def test_scanner_scan_type_unknown_returns_empty(mock_site_root):
    """Test scanning an unknown content type returns empty list."""
    scanner = ContentScanner(site_root=mock_site_root)
    items = scanner.scan_type("nonexistent")
    assert items == []


def test_scanner_search_by_query(create_content_file, mock_site_root):
    """Test search with a text query."""
    create_content_file(slug="python-guide", title="Python Guide", body="Learn python basics.")
    create_content_file(slug="rust-intro", title="Rust Intro", body="Learn rust basics.")

    scanner = ContentScanner(site_root=mock_site_root)
    results = scanner.search(query="python")
    assert len(results) == 1
    assert results[0].slug == "python-guide"


def test_scanner_search_by_tags(create_content_file, mock_site_root):
    """Test search filtered by tags."""
    create_content_file(
        slug="tagged-post", title="Tagged",
        extra_fm={"tags": ["alpha", "beta"]},
    )
    create_content_file(
        slug="other-post", title="Other",
        extra_fm={"tags": ["gamma"]},
    )

    scanner = ContentScanner(site_root=mock_site_root)
    results = scanner.search(tags=["alpha"])
    assert len(results) == 1
    assert results[0].slug == "tagged-post"


def test_scanner_search_by_projects(create_content_file, mock_site_root):
    """Test search filtered by project taxonomy."""
    create_content_file(
        slug="linked-post", title="Linked",
        extra_fm={"linked_project": ["ctk"]},
    )
    create_content_file(slug="unlinked-post", title="Unlinked")

    scanner = ContentScanner(site_root=mock_site_root)
    results = scanner.search(projects=["ctk"])
    assert len(results) == 1
    assert results[0].slug == "linked-post"


def test_scanner_find_content_about_project(create_content_file, mock_site_root):
    """Test finding content about a project by slug mention."""
    create_content_file(
        slug="about-ctk", title="About CTK",
        body="The ctk project is great.",
    )
    create_content_file(
        slug="unrelated", title="Unrelated",
        body="Nothing about that project.",
    )

    scanner = ContentScanner(site_root=mock_site_root)
    results = scanner.find_content_about_project("ctk")
    slugs = [r.slug for r in results]
    assert "about-ctk" in slugs


def test_scanner_stats(create_content_file, mock_site_root):
    """Test stats returns correct counts."""
    create_content_file(slug="p1", title="P1")
    create_content_file(slug="p2", title="P2", draft=True)
    create_content_file(
        slug="p3", title="P3",
        extra_fm={"linked_project": ["ctk"]},
    )

    scanner = ContentScanner(site_root=mock_site_root)
    stats = scanner.stats()
    assert stats["total"] == 3
    assert stats["drafts"] == 1
    assert stats["published"] == 2
    assert stats["with_project_taxonomy"] == 1
    assert stats["by_type"]["post"] == 3


def test_split_content_no_front_matter(mock_site_root):
    """Test _split_content with content that has no front matter."""
    scanner = ContentScanner(site_root=mock_site_root)
    fm, body = scanner._split_content("Just plain text, no dashes.")
    assert fm is None
    assert body == "Just plain text, no dashes."


def test_split_content_valid(mock_site_root):
    """Test _split_content with valid YAML front matter."""
    scanner = ContentScanner(site_root=mock_site_root)
    content = "---\ntitle: Hello\n---\nBody text."
    fm, body = scanner._split_content(content)
    assert fm == {"title": "Hello"}
    assert body == "Body text."


def test_split_content_invalid_yaml_with_path(mock_site_root):
    """Test _split_content with invalid YAML includes path in error."""
    scanner = ContentScanner(site_root=mock_site_root)
    from pathlib import Path
    content = "---\n: bad yaml :\n  [unclosed\n---\nBody."
    # Should not raise, returns None for front matter
    fm, body = scanner._split_content(content, path=Path("/test/file.md"))
    assert fm is None
