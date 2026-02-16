"""Tests for mf.projects.github module (GitHub API client)."""

import base64
import json
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from mf.projects.github import GitHubClient, GITHUB_API, _get_gh_auth_token, check_rate_limit


# -- Helpers --

def _mock_response(data, status=200, headers=None):
    """Create a mock HTTP response from a dict or list."""
    body = json.dumps(data).encode("utf-8")
    response = MagicMock()
    response.read.return_value = body
    response.status = status
    response.headers = headers or {}
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def _mock_http_error(code, reason="Error", headers=None):
    """Create a mock urllib.error.HTTPError."""
    err = urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=code,
        msg=reason,
        hdrs=headers or {},
        fp=BytesIO(b""),
    )
    # Set headers attribute separately since HTTPError uses hdrs
    err.headers = headers or {}
    return err


# -- _get_gh_auth_token tests --

@patch("mf.projects.github.subprocess.run")
def test_get_gh_auth_token_success(mock_run):
    """Should return token from gh auth token command."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="ghp_test_token_12345\n",
    )
    token = _get_gh_auth_token()
    assert token == "ghp_test_token_12345"


@patch("mf.projects.github.subprocess.run")
def test_get_gh_auth_token_not_installed(mock_run):
    """Should return None when gh CLI is not installed."""
    mock_run.side_effect = FileNotFoundError("gh not found")
    token = _get_gh_auth_token()
    assert token is None


@patch("mf.projects.github.subprocess.run")
def test_get_gh_auth_token_not_authenticated(mock_run):
    """Should return None when gh CLI returns non-zero exit code."""
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
    )
    token = _get_gh_auth_token()
    assert token is None


# -- GitHubClient initialization tests --

def test_client_uses_explicit_token():
    """Client should use explicitly provided token."""
    client = GitHubClient(token="explicit-token")
    assert client.token == "explicit-token"


@patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"}, clear=False)
@patch("mf.projects.github._get_gh_auth_token", return_value=None)
def test_client_uses_env_token(mock_gh):
    """Client should fall back to GITHUB_TOKEN env var."""
    client = GitHubClient()
    assert client.token == "env-token"


# -- _make_request tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_make_request_success(mock_urlopen):
    """Successful API request should return parsed JSON."""
    mock_urlopen.return_value = _mock_response({"login": "user", "id": 123})

    client = GitHubClient(token="test-token")
    result = client._make_request("https://api.github.com/user")

    assert result == {"login": "user", "id": 123}


@patch("mf.projects.github.urllib.request.urlopen")
def test_make_request_includes_auth_header(mock_urlopen):
    """Request should include Authorization header when token is set."""
    mock_urlopen.return_value = _mock_response({"ok": True})

    client = GitHubClient(token="my-secret-token")
    client._make_request("https://api.github.com/test")

    # Verify the request was made with auth header
    call_args = mock_urlopen.call_args
    request_obj = call_args[0][0]
    assert request_obj.get_header("Authorization") == "token my-secret-token"


@patch("mf.projects.github.urllib.request.urlopen")
def test_make_request_no_auth_without_token(mock_urlopen):
    """Request should not include Authorization header when no token."""
    mock_urlopen.return_value = _mock_response({"ok": True})

    client = GitHubClient(token="placeholder")
    client.token = None  # bypass auto-detection, force no token
    client._make_request("https://api.github.com/test")

    call_args = mock_urlopen.call_args
    request_obj = call_args[0][0]
    assert request_obj.get_header("Authorization") is None


@patch("mf.projects.github.urllib.request.urlopen")
def test_make_request_returns_none_on_http_error(mock_urlopen):
    """Non-rate-limit HTTP errors should return None."""
    mock_urlopen.side_effect = _mock_http_error(404, "Not Found")

    client = GitHubClient(token="test-token")
    result = client._make_request("https://api.github.com/repos/user/nonexistent", max_retries=1)

    assert result is None


@patch("mf.projects.github.urllib.request.urlopen")
def test_make_request_returns_none_on_url_error(mock_urlopen):
    """Network errors should return None after retries."""
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

    client = GitHubClient(token="test-token")
    # Use max_retries=1 to avoid slow test
    result = client._make_request("https://api.github.com/test", max_retries=1)

    assert result is None


# -- get_user_repos tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_get_user_repos_single_page(mock_urlopen):
    """Should return repos from a single page response."""
    repos = [
        {"name": "repo-1", "language": "Python"},
        {"name": "repo-2", "language": "Rust"},
    ]
    mock_urlopen.return_value = _mock_response(repos)

    client = GitHubClient(token="test-token")
    result = client.get_user_repos("testuser")

    assert len(result) == 2
    assert result[0]["name"] == "repo-1"
    assert result[1]["name"] == "repo-2"


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_user_repos_paginates(mock_urlopen):
    """Should handle pagination when there are 100+ repos."""
    # First page: 100 repos (triggers pagination)
    page1 = [{"name": f"repo-{i}"} for i in range(100)]
    # Second page: fewer than 100 (signals end)
    page2 = [{"name": "repo-100"}, {"name": "repo-101"}]

    mock_urlopen.side_effect = [
        _mock_response(page1),
        _mock_response(page2),
    ]

    client = GitHubClient(token="test-token")
    result = client.get_user_repos("testuser")

    assert len(result) == 102


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_user_repos_empty(mock_urlopen):
    """Should return empty list when user has no repos."""
    mock_urlopen.return_value = _mock_response([])

    client = GitHubClient(token="test-token")
    result = client.get_user_repos("emptyuser")

    assert result == []


# -- get_repo tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_success(mock_urlopen):
    """Should return repo data for a valid owner/repo."""
    repo_data = {
        "name": "my-repo",
        "full_name": "user/my-repo",
        "description": "A cool project.",
        "stargazers_count": 99,
    }
    mock_urlopen.return_value = _mock_response(repo_data)

    client = GitHubClient(token="test-token")
    result = client.get_repo("user", "my-repo")

    assert result["name"] == "my-repo"
    assert result["stargazers_count"] == 99


# -- get_repo_languages tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_languages(mock_urlopen):
    """Should return language percentages."""
    mock_urlopen.return_value = _mock_response({
        "Python": 8000,
        "Shell": 2000,
    })

    client = GitHubClient(token="test-token")
    result = client.get_repo_languages("user", "repo")

    assert abs(result["Python"] - 80.0) < 0.01
    assert abs(result["Shell"] - 20.0) < 0.01


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_languages_empty(mock_urlopen):
    """Should return empty dict when no languages found."""
    mock_urlopen.return_value = _mock_response({})

    client = GitHubClient(token="test-token")
    result = client.get_repo_languages("user", "repo")

    assert result == {}


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_languages_api_failure(mock_urlopen):
    """Should return empty dict on API failure."""
    mock_urlopen.side_effect = _mock_http_error(404)

    client = GitHubClient(token="test-token")
    result = client.get_repo_languages("user", "repo")

    assert result == {}


# -- get_repo_readme tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_readme_success(mock_urlopen):
    """Should decode base64 README content."""
    readme_text = "# My Project\n\nWelcome to the project."
    encoded = base64.b64encode(readme_text.encode("utf-8")).decode("utf-8")
    mock_urlopen.return_value = _mock_response({
        "content": encoded,
        "encoding": "base64",
    })

    client = GitHubClient(token="test-token")
    result = client.get_repo_readme("user", "repo")

    assert result == readme_text


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_readme_not_found(mock_urlopen):
    """Should return None when README doesn't exist."""
    mock_urlopen.side_effect = _mock_http_error(404)

    client = GitHubClient(token="test-token")
    result = client.get_repo_readme("user", "repo")

    assert result is None


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_repo_readme_no_content_field(mock_urlopen):
    """Should return None when response lacks content field."""
    mock_urlopen.return_value = _mock_response({"name": "README.md"})

    client = GitHubClient(token="test-token")
    result = client.get_repo_readme("user", "repo")

    assert result is None


# -- get_github_pages_url tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_get_github_pages_url_enabled(mock_urlopen):
    """Should return Pages URL when enabled."""
    mock_urlopen.return_value = _mock_response({
        "html_url": "https://user.github.io/repo",
        "status": "built",
    })

    client = GitHubClient(token="test-token")
    result = client.get_github_pages_url("user", "repo")

    assert result == "https://user.github.io/repo"


@patch("mf.projects.github.urllib.request.urlopen")
def test_get_github_pages_url_not_enabled(mock_urlopen):
    """Should return None when Pages is not enabled (404)."""
    mock_urlopen.side_effect = _mock_http_error(404)

    client = GitHubClient(token="test-token")
    result = client.get_github_pages_url("user", "repo")

    assert result is None


# -- check_rate_limit tests --

@patch("mf.projects.github.urllib.request.urlopen")
def test_check_rate_limit_displays_info(mock_urlopen, capsys):
    """check_rate_limit should query the rate limit endpoint."""
    mock_urlopen.return_value = _mock_response({
        "resources": {
            "core": {
                "limit": 5000,
                "remaining": 4999,
                "reset": 1700000000,
            }
        }
    })

    # Should not raise
    check_rate_limit(token="test-token")
