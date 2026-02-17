"""Shared test fixtures for mf package."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def sample_json_file(tmp_path):
    """Create a sample JSON file for testing."""
    data = {"key": "value", "number": 42}
    file_path = tmp_path / "sample.json"
    file_path.write_text(json.dumps(data))
    return file_path


@pytest.fixture
def sample_paper_db(tmp_path):
    """Create a sample paper database for testing."""
    data = {
        "_comment": "Test database",
        "_example": {"title": "Example"},
        "test-paper": {
            "title": "Test Paper",
            "abstract": "This is a test paper",
            "tags": ["test", "sample"],
            "category": "research paper",
            "source_path": str(tmp_path / "test.tex"),
            "source_hash": "sha256:abc123",
        },
        "another-paper": {
            "title": "Another Paper",
            "category": "white paper",
        },
    }
    file_path = tmp_path / "paper_db.json"
    file_path.write_text(json.dumps(data, indent=2))

    # Create a mock source file
    tex_file = tmp_path / "test.tex"
    tex_file.write_text("\\documentclass{article}\n\\begin{document}\nTest\n\\end{document}")

    return file_path


@pytest.fixture
def sample_projects_db(tmp_path):
    """Create a sample projects database for testing."""
    data = {
        "_comment": "Test projects",
        "_schema_version": "1.0",
        "_example": {"title": "Example"},
        "test-project": {
            "title": "Test Project",
            "abstract": "A test project",
            "tags": ["python", "test"],
            "category": "library",
            "featured": True,
        },
        "hidden-project": {
            "title": "Hidden",
            "hide": True,
        },
    }
    file_path = tmp_path / "projects_db.json"
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


@pytest.fixture
def sample_series_db(tmp_path):
    """Create a sample series database for testing."""
    data = {
        "_comment": "Test series",
        "_schema_version": "1.0",
        "_example": {"title": "Example"},
        "test-series": {
            "title": "Test Series",
            "description": "A test series",
            "tags": ["test", "sample"],
            "status": "active",
            "featured": True,
        },
        "inactive-series": {
            "title": "Inactive Series",
            "status": "archived",
        },
    }
    file_path = tmp_path / "series_db.json"
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


@pytest.fixture
def mock_site_root(tmp_path, monkeypatch):
    """Create a mock site structure with .mf/ directory."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "papers").mkdir(parents=True)
    (mf_dir / "backups" / "projects").mkdir(parents=True)
    (mf_dir / "backups" / "series").mkdir(parents=True)
    (mf_dir / "backups" / "packages").mkdir(parents=True)

    # Create content directory structure
    (tmp_path / "content" / "papers").mkdir(parents=True)
    (tmp_path / "content" / "projects").mkdir(parents=True)
    (tmp_path / "content" / "publications").mkdir(parents=True)
    (tmp_path / "content" / "post").mkdir(parents=True)
    (tmp_path / "content" / "series").mkdir(parents=True)
    (tmp_path / "content" / "packages").mkdir(parents=True)
    (tmp_path / "static" / "latex").mkdir(parents=True)

    # Mock get_site_root to return our tmp_path
    from mf.core import config
    # Clear the lru_cache first
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


@pytest.fixture
def create_content_file(mock_site_root):
    """Factory fixture for creating markdown content files with frontmatter."""
    def _create(
        content_type: str = "post",
        slug: str = "test-post",
        title: str = "Test Post",
        body: str = "Test content.",
        extra_fm: dict | None = None,
        draft: bool = False,
    ) -> Path:
        content_dir = mock_site_root / "content" / content_type / slug
        content_dir.mkdir(parents=True, exist_ok=True)

        fm = {"title": title, "date": "2024-01-01", "draft": draft}
        if extra_fm:
            fm.update(extra_fm)

        import yaml
        fm_str = yaml.dump(fm, default_flow_style=False)
        content = f"---\n{fm_str}---\n\n{body}\n"

        index_file = content_dir / "index.md"
        index_file.write_text(content, encoding="utf-8")
        return index_file

    return _create
