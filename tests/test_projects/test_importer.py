"""Tests for mf.projects.importer module (GitHub repository import)."""

from unittest.mock import MagicMock, patch

import pytest

from mf.projects.importer import (
    filter_repos,
    extract_repo_metadata,
    import_user_repos,
    refresh_projects,
    clean_stale_projects,
)


# -- Fixtures --

@pytest.fixture
def sample_repos():
    """A list of sample GitHub repository data dicts."""
    return [
        {
            "name": "alpha",
            "full_name": "user/alpha",
            "language": "Python",
            "description": "Alpha project",
            "fork": False,
            "archived": False,
            "stargazers_count": 10,
            "topics": ["ml", "data"],
            "owner": {"login": "user"},
            "html_url": "https://github.com/user/alpha",
            "created_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2024-12-01T00:00:00Z",
        },
        {
            "name": "beta-fork",
            "full_name": "user/beta-fork",
            "language": "JavaScript",
            "description": None,
            "fork": True,
            "archived": False,
            "stargazers_count": 0,
            "topics": [],
            "owner": {"login": "user"},
            "html_url": "https://github.com/user/beta-fork",
            "created_at": "2024-02-01T00:00:00Z",
            "pushed_at": "2024-06-01T00:00:00Z",
        },
        {
            "name": "gamma-archived",
            "full_name": "user/gamma-archived",
            "language": "Rust",
            "description": "Old archived project",
            "fork": False,
            "archived": True,
            "stargazers_count": 25,
            "topics": ["systems", "ml"],
            "owner": {"login": "user"},
            "html_url": "https://github.com/user/gamma-archived",
            "created_at": "2023-01-01T00:00:00Z",
            "pushed_at": "2023-06-01T00:00:00Z",
        },
        {
            "name": "delta",
            "full_name": "user/delta",
            "language": "Python",
            "description": "A small utility",
            "fork": False,
            "archived": False,
            "stargazers_count": 3,
            "topics": ["cli", "data"],
            "owner": {"login": "user"},
            "html_url": "https://github.com/user/delta",
            "created_at": "2024-05-01T00:00:00Z",
            "pushed_at": "2024-11-01T00:00:00Z",
        },
    ]


# -- filter_repos tests --

def test_filter_no_filters(sample_repos):
    """No filters should return all repos."""
    result = filter_repos(sample_repos)
    assert len(result) == 4


def test_filter_exclude_forks(sample_repos):
    """Exclude forks should remove forked repos."""
    result = filter_repos(sample_repos, exclude_forks=True)
    assert len(result) == 3
    assert all(not r["fork"] for r in result)
    names = [r["name"] for r in result]
    assert "beta-fork" not in names


def test_filter_exclude_archived(sample_repos):
    """Exclude archived should remove archived repos."""
    result = filter_repos(sample_repos, exclude_archived=True)
    assert len(result) == 3
    names = [r["name"] for r in result]
    assert "gamma-archived" not in names


def test_filter_min_stars(sample_repos):
    """Min stars should filter out repos below threshold."""
    result = filter_repos(sample_repos, min_stars=5)
    assert len(result) == 2
    names = [r["name"] for r in result]
    assert "alpha" in names
    assert "gamma-archived" in names


def test_filter_has_description(sample_repos):
    """Has description should exclude repos without descriptions."""
    result = filter_repos(sample_repos, has_description=True)
    assert len(result) == 3
    names = [r["name"] for r in result]
    assert "beta-fork" not in names


def test_filter_by_language(sample_repos):
    """Language filter should match case-insensitively."""
    result = filter_repos(sample_repos, languages=["python"])
    assert len(result) == 2
    names = [r["name"] for r in result]
    assert "alpha" in names
    assert "delta" in names


def test_filter_by_topics(sample_repos):
    """Topics filter requires all specified topics to be present."""
    result = filter_repos(sample_repos, topics=["ml", "data"])
    assert len(result) == 1
    assert result[0]["name"] == "alpha"


def test_filter_combined(sample_repos):
    """Multiple filters should combine (AND logic)."""
    result = filter_repos(
        sample_repos,
        exclude_forks=True,
        exclude_archived=True,
        min_stars=5,
    )
    assert len(result) == 1
    assert result[0]["name"] == "alpha"


def test_filter_by_language_no_match(sample_repos):
    """Language filter with no matching repos should return empty."""
    result = filter_repos(sample_repos, languages=["Haskell"])
    assert len(result) == 0


def test_filter_topics_empty_topics_list(sample_repos):
    """Topics=[] should not filter (vacuously true -- empty subset)."""
    result = filter_repos(sample_repos, topics=[])
    assert len(result) == 4


# -- extract_repo_metadata tests --

def test_extract_repo_metadata_augments_data(sample_repos):
    """extract_repo_metadata should add languages, pages, readme data."""
    repo = sample_repos[0]  # alpha
    mock_client = MagicMock()
    mock_client.get_repo_languages.return_value = {"Python": 90.0, "Shell": 10.0}
    mock_client.get_github_pages_url.return_value = "https://user.github.io/alpha"
    mock_client.get_repo_readme.return_value = "# Alpha\n\nProject README."

    result = extract_repo_metadata(repo, mock_client)

    assert result["name"] == "alpha"
    assert result["_languages_breakdown"] == {"Python": 90.0, "Shell": 10.0}
    assert result["_github_pages_url"] == "https://user.github.io/alpha"
    assert result["_readme_content"] == "# Alpha\n\nProject README."
    assert "_last_synced" in result


def test_extract_repo_metadata_no_pages(sample_repos):
    """When pages URL is None, key should not appear."""
    repo = sample_repos[0]
    mock_client = MagicMock()
    mock_client.get_repo_languages.return_value = {}
    mock_client.get_github_pages_url.return_value = None
    mock_client.get_repo_readme.return_value = None

    result = extract_repo_metadata(repo, mock_client)

    assert "_github_pages_url" not in result
    assert "_readme_content" not in result


def test_extract_repo_metadata_no_languages(sample_repos):
    """When languages are empty, key should not appear."""
    repo = sample_repos[0]
    mock_client = MagicMock()
    mock_client.get_repo_languages.return_value = {}
    mock_client.get_github_pages_url.return_value = None
    mock_client.get_repo_readme.return_value = None

    result = extract_repo_metadata(repo, mock_client)

    assert "_languages_breakdown" not in result


def test_extract_repo_metadata_preserves_original(sample_repos):
    """extract_repo_metadata should copy the repo dict, not mutate original."""
    repo = sample_repos[0]
    original_keys = set(repo.keys())

    mock_client = MagicMock()
    mock_client.get_repo_languages.return_value = {"Python": 100.0}
    mock_client.get_github_pages_url.return_value = None
    mock_client.get_repo_readme.return_value = "readme"

    extract_repo_metadata(repo, mock_client)

    # Original should not have underscore-prefixed keys
    assert set(repo.keys()) == original_keys


# -- import_user_repos tests --

@patch("mf.projects.importer.check_rate_limit")
@patch("mf.projects.importer.GitHubClient")
def test_import_user_repos_dry_run(mock_client_cls, mock_rate_limit, sample_repos, capsys):
    """Dry run should list repos but not create content."""
    mock_client = MagicMock()
    mock_client.get_user_repos.return_value = sample_repos
    mock_client_cls.return_value = mock_client

    import_user_repos(
        username="testuser",
        token="test-token",
        dry_run=True,
    )

    # Dry run should not call extract_repo_metadata
    mock_client.get_repo_languages.assert_not_called()


@patch("mf.projects.importer.generate_project_content")
@patch("mf.projects.importer.extract_repo_metadata")
@patch("mf.projects.importer.check_rate_limit")
@patch("mf.projects.importer.GitHubClient")
@patch("mf.projects.importer.ProjectsCache")
@patch("mf.projects.importer.ProjectsDatabase")
def test_import_user_repos_skips_existing(
    mock_db_cls, mock_cache_cls,
    mock_client_cls, mock_rate_limit,
    mock_extract, mock_generate,
    sample_repos,
):
    """Existing cached projects should be skipped unless --force."""
    mock_client = MagicMock()
    mock_client.get_user_repos.return_value = [sample_repos[0]]  # just alpha
    mock_client_cls.return_value = mock_client

    mock_cache = MagicMock()
    mock_cache.__contains__ = MagicMock(return_value=True)  # alpha exists
    mock_cache_cls.return_value = mock_cache

    mock_db = MagicMock()
    mock_db.get.return_value = None
    mock_db_cls.return_value = mock_db

    import_user_repos(username="testuser", token="test-token")

    # Should not have called extract since project exists
    mock_extract.assert_not_called()


# -- refresh_projects tests --

@patch("mf.projects.importer.generate_project_content")
@patch("mf.projects.importer.extract_repo_metadata")
@patch("mf.projects.importer.check_rate_limit")
@patch("mf.projects.importer.GitHubClient")
def test_refresh_updates_changed_project(
    mock_client_cls, mock_rate_limit, mock_extract, mock_generate,
    mock_site_root,
):
    """Refresh should update projects that have changed pushed_at."""
    from mf.core.database import ProjectsCache, ProjectsDatabase

    mock_client = MagicMock()
    mock_client.get_repo.return_value = {
        "name": "proj",
        "pushed_at": "2024-12-15T00:00:00Z",  # newer
    }
    mock_client_cls.return_value = mock_client

    mock_extract.return_value = {
        "name": "proj",
        "pushed_at": "2024-12-15T00:00:00Z",
        "_last_synced": "2024-12-15T00:00:00Z",
    }

    with patch("mf.projects.importer.ProjectsCache") as pc_cls, \
         patch("mf.projects.importer.ProjectsDatabase") as pd_cls:

        cache = MagicMock()
        cache.__iter__ = MagicMock(return_value=iter(["proj"]))
        cache.__contains__ = MagicMock(return_value=True)
        cache.get.return_value = {
            "html_url": "https://github.com/user/proj",
            "pushed_at": "2024-11-01T00:00:00Z",  # older
        }
        pc_cls.return_value = cache

        db = MagicMock()
        db.get.return_value = {}
        pd_cls.return_value = db

        refresh_projects(slug="proj", token="test-token")

        # Should have done a full refresh via extract_repo_metadata
        mock_extract.assert_called_once()


@patch("mf.projects.importer.check_rate_limit")
@patch("mf.projects.importer.GitHubClient")
def test_refresh_slug_not_found(mock_client_cls, mock_rate_limit, capsys):
    """Refreshing a non-existent slug should print error."""
    mock_client_cls.return_value = MagicMock()

    with patch("mf.projects.importer.ProjectsCache") as pc_cls, \
         patch("mf.projects.importer.ProjectsDatabase") as pd_cls:

        cache = MagicMock()
        cache.__contains__ = MagicMock(return_value=False)
        pc_cls.return_value = cache

        db = MagicMock()
        pd_cls.return_value = db

        # Should not raise, just print error
        refresh_projects(slug="nonexistent", token="test-token")


# -- clean_stale_projects tests --

@patch("mf.projects.importer.GitHubClient")
def test_clean_stale_dry_run(mock_client_cls, mock_site_root):
    """Dry run should not remove any files."""
    mock_client = MagicMock()
    mock_client.get_user_repos.return_value = [
        {"name": "existing-repo"},
    ]
    mock_client_cls.return_value = mock_client

    # Create a stale project dir
    stale_dir = mock_site_root / "content" / "projects" / "stale-repo"
    stale_dir.mkdir(parents=True)
    (stale_dir / "index.md").write_text("old content")

    with patch("mf.projects.importer.ProjectsCache") as pc_cls, \
         patch("mf.projects.importer.ProjectsDatabase") as pd_cls:

        cache = MagicMock()
        cache.__iter__ = MagicMock(return_value=iter([]))
        pc_cls.return_value = cache

        db = MagicMock()
        db._data = {}
        pd_cls.return_value = db

        clean_stale_projects(
            username="testuser",
            token="test-token",
            dry_run=True,
        )

    # Dir should still exist after dry run
    assert stale_dir.exists()


@patch("mf.projects.importer.GitHubClient")
def test_clean_stale_no_stale(mock_client_cls, mock_site_root):
    """Should report no stale projects when everything matches."""
    mock_client = MagicMock()
    mock_client.get_user_repos.return_value = [
        {"name": "my-project"},
    ]
    mock_client_cls.return_value = mock_client

    # Create a matching project dir
    proj_dir = mock_site_root / "content" / "projects" / "my-project"
    proj_dir.mkdir(parents=True)

    with patch("mf.projects.importer.ProjectsCache") as pc_cls, \
         patch("mf.projects.importer.ProjectsDatabase") as pd_cls:

        cache = MagicMock()
        cache.__iter__ = MagicMock(return_value=iter([]))
        pc_cls.return_value = cache

        db = MagicMock()
        db._data = {}
        pd_cls.return_value = db

        # Should complete without error
        clean_stale_projects(
            username="testuser",
            token="test-token",
            dry_run=True,
        )
