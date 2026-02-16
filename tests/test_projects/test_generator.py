"""Tests for mf.projects.generator module (Hugo content generation for projects)."""

import pytest
from unittest.mock import patch

from mf.projects.generator import (
    merge_project_data,
    generate_project_frontmatter,
    generate_section_frontmatter,
    generate_project_content,
    generate_all_projects,
    SECTION_TEMPLATES,
)


# -- Fixtures --

@pytest.fixture
def github_data():
    """Sample GitHub API data for a repository."""
    return {
        "name": "test-repo",
        "full_name": "user/test-repo",
        "html_url": "https://github.com/user/test-repo",
        "default_branch": "main",
        "description": "A test repository for unit testing.",
        "language": "Python",
        "created_at": "2024-03-15T10:00:00Z",
        "pushed_at": "2024-12-01T08:00:00Z",
        "stargazers_count": 42,
        "topics": ["testing", "python"],
        "_readme_content": "# Test Repo\n\nThis is the README.",
        "_github_pages_url": "https://user.github.io/test-repo",
        "_languages_breakdown": {"Python": 85.0, "Shell": 15.0},
    }


@pytest.fixture
def manual_overrides():
    """Sample manual overrides from projects_db.json."""
    return {
        "title": "My Custom Title",
        "abstract": "Custom abstract override.",
        "tags": ["custom-tag", "override"],
        "featured": True,
        "category": "tool",
        "packages": {"pypi": "test-repo"},
        "external_docs": {
            "readthedocs": "https://test-repo.readthedocs.io/",
        },
    }


# -- merge_project_data tests --

def test_merge_uses_github_html_url(github_data):
    """Merge should set github_url from GitHub data's html_url."""
    merged = merge_project_data("test-repo", github_data, {})
    assert merged["github_url"] == "https://github.com/user/test-repo"


def test_merge_overrides_take_precedence(github_data, manual_overrides):
    """Manual overrides should take precedence over GitHub data."""
    merged = merge_project_data("test-repo", github_data, manual_overrides)
    assert merged["title"] == "My Custom Title"
    assert merged["tags"] == ["custom-tag", "override"]
    assert merged["category"] == "tool"
    assert merged["featured"] is True


def test_merge_preserves_github_data(github_data, manual_overrides):
    """Merged result should preserve full github_data under github_data key."""
    merged = merge_project_data("test-repo", github_data, manual_overrides)
    assert merged["github_data"] is github_data
    assert merged["github_data"]["stargazers_count"] == 42


def test_merge_with_empty_overrides(github_data):
    """Merge with empty overrides should only set github_url and github_data."""
    merged = merge_project_data("test-repo", github_data, {})
    assert "title" not in merged
    assert "tags" not in merged
    assert "github_url" in merged
    assert "github_data" in merged


def test_merge_includes_rich_project_settings(github_data):
    """Merge should include rich_project and content_sections when present."""
    overrides = {
        "rich_project": True,
        "content_sections": ["docs", "tutorials"],
    }
    merged = merge_project_data("test-repo", github_data, overrides)
    assert merged["rich_project"] is True
    assert merged["content_sections"] == ["docs", "tutorials"]


# -- generate_project_frontmatter tests --

def test_frontmatter_basic_structure(github_data):
    """Generated frontmatter should have required YAML sections."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    fm = generate_project_frontmatter("test-repo", metadata)

    assert fm.startswith("---")
    assert fm.rstrip().endswith("---")
    assert 'title: "test-repo"' in fm
    assert "date: 2024-03-15T10:00:00Z" in fm
    assert "draft: false" in fm
    assert "project:" in fm
    assert "tech:" in fm
    assert "sources:" in fm
    assert "packages:" in fm
    assert "metrics:" in fm


def test_frontmatter_uses_override_title(github_data, manual_overrides):
    """Frontmatter should prefer manual title over github name."""
    merged = merge_project_data("test-repo", github_data, manual_overrides)
    fm = generate_project_frontmatter("test-repo", merged)

    assert 'title: "My Custom Title"' in fm


def test_frontmatter_featured_flag(github_data, manual_overrides):
    """Frontmatter should include featured status from overrides."""
    merged = merge_project_data("test-repo", github_data, manual_overrides)
    fm = generate_project_frontmatter("test-repo", merged)

    assert "featured: true" in fm


def test_frontmatter_hidden_project_is_draft(github_data):
    """Hidden projects should have draft: true in frontmatter."""
    metadata = {
        "hide": True,
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    fm = generate_project_frontmatter("test-repo", metadata)

    assert "draft: true" in fm


def test_frontmatter_branch_bundle_has_layout(github_data):
    """Branch bundles (rich projects) should have layout: project-landing."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    fm = generate_project_frontmatter("test-repo", metadata, is_branch_bundle=True)

    assert "layout: project-landing" in fm


def test_frontmatter_includes_stars_from_github(github_data):
    """Metrics section should include stargazers_count from GitHub."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    fm = generate_project_frontmatter("test-repo", metadata)

    assert "stars: 42" in fm


def test_frontmatter_includes_packages(github_data, manual_overrides):
    """Packages section should be populated from overrides."""
    merged = merge_project_data("test-repo", github_data, manual_overrides)
    fm = generate_project_frontmatter("test-repo", merged)

    assert 'pypi: "test-repo"' in fm


def test_frontmatter_includes_external_docs(github_data, manual_overrides):
    """External docs section should appear when provided."""
    merged = merge_project_data("test-repo", github_data, manual_overrides)
    fm = generate_project_frontmatter("test-repo", merged)

    assert "external_docs:" in fm
    assert 'readthedocs: "https://test-repo.readthedocs.io/"' in fm


def test_frontmatter_description_escapes_quotes(github_data):
    """Description with quotes should have them escaped."""
    github_data_copy = dict(github_data)
    github_data_copy["description"] = 'A "quoted" description'
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data_copy,
    }
    fm = generate_project_frontmatter("test-repo", metadata)

    assert 'description: "A \\"quoted\\" description"' in fm


def test_frontmatter_papers_section(github_data):
    """Papers section should be populated when papers are present."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
        "papers": [
            {"title": "Test Paper", "venue": "ICML", "year": 2024, "arxiv": "2401.12345"},
        ],
    }
    fm = generate_project_frontmatter("test-repo", metadata)

    assert "papers:" in fm
    assert 'title: "Test Paper"' in fm
    assert 'venue: "ICML"' in fm
    assert 'arxiv: "2401.12345"' in fm


def test_frontmatter_related_posts(github_data):
    """Related posts should appear when provided."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
        "related_posts": ["/post/2024-01-01-intro/"],
    }
    fm = generate_project_frontmatter("test-repo", metadata)

    assert "related_posts:" in fm
    assert '"/post/2024-01-01-intro/"' in fm


# -- generate_section_frontmatter tests --

def test_section_frontmatter_uses_template():
    """Section frontmatter should use values from SECTION_TEMPLATES."""
    fm = generate_section_frontmatter("docs", "My Project")

    assert 'title: "Documentation"' in fm
    assert "layout: project-section" in fm
    assert "weight: 10" in fm


def test_section_frontmatter_fallback_for_unknown_section():
    """Unknown sections should fall back to title-cased name."""
    fm = generate_section_frontmatter("unknown-section", "My Project")

    assert 'title: "Unknown-Section"' in fm
    assert "weight: 99" in fm


def test_section_frontmatter_custom_template():
    """Custom template should override defaults."""
    template = {"title": "Custom", "description": "Custom desc", "weight": 5}
    fm = generate_section_frontmatter("docs", "My Project", template=template)

    assert 'title: "Custom"' in fm
    assert 'description: "Custom desc"' in fm
    assert "weight: 5" in fm


# -- generate_project_content tests --

def test_generate_project_content_leaf_bundle(mock_site_root, github_data):
    """Simple project should create index.md (leaf bundle)."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    result = generate_project_content("test-repo", metadata)

    assert result is True
    content_file = mock_site_root / "content" / "projects" / "test-repo" / "index.md"
    assert content_file.exists()
    text = content_file.read_text()
    assert "---" in text
    assert "# Test Repo" in text  # README content


def test_generate_project_content_branch_bundle(mock_site_root, github_data):
    """Rich project should create _index.md (branch bundle) and section pages."""
    metadata = {
        "title": "Rich Project",
        "rich_project": True,
        "content_sections": ["docs", "tutorials"],
        "github_url": "https://github.com/user/rich-proj",
        "github_data": github_data,
    }
    result = generate_project_content("rich-proj", metadata)

    assert result is True
    index_file = mock_site_root / "content" / "projects" / "rich-proj" / "_index.md"
    assert index_file.exists()

    docs_section = mock_site_root / "content" / "projects" / "rich-proj" / "docs" / "_index.md"
    assert docs_section.exists()
    assert "Documentation" in docs_section.read_text()

    tutorials_section = mock_site_root / "content" / "projects" / "rich-proj" / "tutorials" / "_index.md"
    assert tutorials_section.exists()


def test_generate_project_content_dry_run(mock_site_root, github_data):
    """Dry run should not create any files."""
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    result = generate_project_content("test-repo", metadata, dry_run=True)

    assert result is True
    content_file = mock_site_root / "content" / "projects" / "test-repo" / "index.md"
    assert not content_file.exists()


def test_generate_project_content_uses_abstract_when_no_readme(mock_site_root):
    """When no README, content should fall back to abstract."""
    metadata = {
        "abstract": "Fallback abstract text.",
        "github_url": "https://github.com/user/no-readme",
        "github_data": {
            "name": "no-readme",
            "created_at": "2024-01-01T00:00:00Z",
            "stargazers_count": 0,
        },
    }
    result = generate_project_content("no-readme", metadata)

    assert result is True
    text = (mock_site_root / "content" / "projects" / "no-readme" / "index.md").read_text()
    assert "Fallback abstract text." in text


def test_generate_project_content_skips_existing_sections(mock_site_root, github_data):
    """Existing section files should not be overwritten."""
    slug = "existing-sections"
    metadata = {
        "title": "Existing Sections",
        "rich_project": True,
        "content_sections": ["docs"],
        "github_url": "https://github.com/user/existing-sections",
        "github_data": github_data,
    }

    # Pre-create the docs section with custom content
    docs_dir = mock_site_root / "content" / "projects" / slug / "docs"
    docs_dir.mkdir(parents=True)
    existing_file = docs_dir / "_index.md"
    existing_file.write_text("---\ntitle: Manual Edit\n---\nCustom content.")

    generate_project_content(slug, metadata)

    # Existing file should be preserved
    assert existing_file.read_text() == "---\ntitle: Manual Edit\n---\nCustom content."


# -- generate_all_projects tests --

def test_generate_all_projects(mock_site_root):
    """generate_all_projects should process all cached projects."""
    from mf.core.database import ProjectsCache, ProjectsDatabase

    cache = ProjectsCache(mock_site_root / ".mf" / "cache" / "projects.json")
    cache._data = {
        "proj-a": {
            "name": "proj-a",
            "html_url": "https://github.com/user/proj-a",
            "created_at": "2024-01-01T00:00:00Z",
            "stargazers_count": 5,
        },
        "proj-b": {
            "name": "proj-b",
            "html_url": "https://github.com/user/proj-b",
            "created_at": "2024-06-01T00:00:00Z",
            "stargazers_count": 10,
        },
    }
    cache._loaded = True

    db = ProjectsDatabase(mock_site_root / ".mf" / "projects_db.json")
    db._data = {"_comment": "test"}
    db._loaded = True

    success, failed = generate_all_projects(cache, db)

    assert success == 2
    assert failed == 0
    assert (mock_site_root / "content" / "projects" / "proj-a" / "index.md").exists()
    assert (mock_site_root / "content" / "projects" / "proj-b" / "index.md").exists()


def test_generate_all_projects_skips_hidden(mock_site_root):
    """generate_all_projects should skip hidden projects and delete their dirs."""
    from mf.core.database import ProjectsCache, ProjectsDatabase

    # Create a content dir for the hidden project to test deletion
    hidden_dir = mock_site_root / "content" / "projects" / "hidden-proj"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "index.md").write_text("old content")

    cache = ProjectsCache(mock_site_root / ".mf" / "cache" / "projects.json")
    cache._data = {
        "hidden-proj": {
            "name": "hidden-proj",
            "html_url": "https://github.com/user/hidden-proj",
            "created_at": "2024-01-01T00:00:00Z",
            "stargazers_count": 0,
        },
    }
    cache._loaded = True

    db = ProjectsDatabase(mock_site_root / ".mf" / "projects_db.json")
    db._data = {
        "_comment": "test",
        "hidden-proj": {"hide": True},
    }
    db._loaded = True

    success, failed = generate_all_projects(cache, db)

    assert success == 0
    assert failed == 0
    # The hidden project dir should be deleted
    assert not hidden_dir.exists()


# -- README URL rewriting integration tests --

def test_generate_project_content_rewrites_readme_urls(mock_site_root, github_data):
    """GitHub README relative URLs should be rewritten to absolute GitHub URLs."""
    github_data_copy = dict(github_data)
    github_data_copy["_readme_content"] = (
        "# Test Repo\n\n"
        "See [docs](docs/api.md) and ![logo](images/logo.png).\n"
    )
    metadata = {
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data_copy,
    }
    generate_project_content("test-repo", metadata)

    text = (mock_site_root / "content" / "projects" / "test-repo" / "index.md").read_text()
    assert "github.com/user/test-repo/blob/main/docs/api.md" in text
    assert "raw.githubusercontent.com/user/test-repo/main/images/logo.png" in text


def test_generate_project_content_does_not_rewrite_readme_override(mock_site_root, github_data):
    """Manual readme_override content should NOT have URLs rewritten."""
    metadata = {
        "readme_override": "See [local](docs/local.md) for details.",
        "github_url": "https://github.com/user/test-repo",
        "github_data": github_data,
    }
    generate_project_content("test-repo", metadata)

    text = (mock_site_root / "content" / "projects" / "test-repo" / "index.md").read_text()
    # The relative URL should remain as-is (not rewritten)
    assert "[local](docs/local.md)" in text
    assert "github.com" not in text.split("---")[-1]  # Body only, not frontmatter


def test_generate_project_content_missing_default_branch(mock_site_root):
    """When default_branch is missing from github_data, should fall back to 'main'."""
    github_data_no_branch = {
        "name": "no-branch",
        "html_url": "https://github.com/user/no-branch",
        "created_at": "2024-01-01T00:00:00Z",
        "stargazers_count": 0,
        "_readme_content": "[Link](docs/api.md)",
    }
    metadata = {
        "github_url": "https://github.com/user/no-branch",
        "github_data": github_data_no_branch,
    }
    generate_project_content("no-branch", metadata)

    text = (mock_site_root / "content" / "projects" / "no-branch" / "index.md").read_text()
    assert "blob/main/docs/api.md" in text
