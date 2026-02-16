"""
GitHub API client with rate limiting and caching.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, cast

from rich.console import Console

console = Console()

GITHUB_API = "https://api.github.com"


def _get_gh_auth_token() -> str | None:
    """Try to get token from GitHub CLI (gh auth token).

    Returns:
        Token string or None if gh CLI not available/authenticated
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


class GitHubClient:
    """GitHub API client with rate limit handling."""

    def __init__(self, token: str | None = None):
        """Initialize client.

        Token resolution order:
        1. Explicit token parameter
        2. GITHUB_TOKEN environment variable
        3. gh auth token (GitHub CLI)

        Args:
            token: GitHub personal access token
        """
        self.token = token or os.environ.get("GITHUB_TOKEN") or _get_gh_auth_token()
        self._rate_limit_remaining = None
        self._rate_limit_reset = None

    def _make_request(
        self,
        url: str,
        max_retries: int = 5,
    ) -> dict | list | None:
        """Make a request to GitHub API with rate limit handling.

        Args:
            url: Full API URL
            max_retries: Maximum retry attempts

        Returns:
            JSON response as dict/list, or None on error
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "mf-github-import/1.0",
        }

        if self.token:
            headers["Authorization"] = f"token {self.token}"

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    # Update rate limit info
                    self._rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
                    self._rate_limit_reset = response.headers.get("X-RateLimit-Reset")
                    return cast(dict | list | None, json.loads(response.read()))

            except urllib.error.HTTPError as e:
                if e.code in [403, 429]:
                    # Rate limit exceeded
                    reset_time = e.headers.get("X-RateLimit-Reset")
                    remaining = e.headers.get("X-RateLimit-Remaining", "0")

                    if remaining == "0" and reset_time:
                        reset_dt = datetime.fromtimestamp(int(reset_time))
                        wait_seconds = max(0, (reset_dt - datetime.now()).total_seconds())

                        if 0 < wait_seconds < 3600:
                            console.print(
                                f"[yellow]Rate limit exceeded. "
                                f"Waiting {int(wait_seconds)}s until {reset_dt.strftime('%H:%M:%S')}...[/yellow]"
                            )
                            time.sleep(wait_seconds + 5)
                            continue
                        else:
                            console.print(f"[red]Rate limit exceeded. Reset at {reset_dt}[/red]")
                            return None

                    # Exponential backoff
                    wait_time = min(2 ** attempt, 300)
                    console.print(f"[yellow]Rate limit hit. Retrying in {wait_time}s...[/yellow]")
                    time.sleep(wait_time)
                    continue

                if attempt == max_retries - 1:
                    console.print(f"[red]GitHub API error {e.code}: {e.reason}[/red]")
                return None

            except urllib.error.URLError as e:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 60)
                    console.print(f"[yellow]Network error. Retrying in {wait_time}s...[/yellow]")
                    time.sleep(wait_time)
                    continue
                console.print(f"[red]Network error: {e}[/red]")
                return None

            except Exception as e:
                console.print(f"[red]Request error: {e}[/red]")
                return None

        return None

    def get_rate_limit(self) -> dict[str, Any] | None:
        """Get current rate limit status.

        Returns:
            Rate limit info dict or None
        """
        result = self._make_request(f"{GITHUB_API}/rate_limit", max_retries=1)
        if isinstance(result, dict):
            return result
        return None

    def get_user_repos(
        self,
        username: str,
        include_private: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch all repositories for a user.

        Args:
            username: GitHub username
            include_private: Include private repos (requires token)

        Returns:
            List of repository data dicts
        """
        repos: list[dict[str, Any]] = []
        page = 1

        while True:
            visibility = "all" if include_private else "public"
            url = f"{GITHUB_API}/users/{username}/repos?per_page=100&page={page}&type={visibility}"

            data = self._make_request(url)
            if not data or not isinstance(data, list):
                break

            repos.extend(data)
            page += 1

            # Check if there are more pages
            if len(data) < 100:
                break

        return repos

    def get_repo(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get repository details.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository data dict or None
        """
        url = f"{GITHUB_API}/repos/{owner}/{repo}"
        result = self._make_request(url)
        if isinstance(result, dict):
            return result
        return None

    def get_repo_languages(self, owner: str, repo: str) -> dict[str, float]:
        """Get language breakdown for a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict mapping language name to percentage
        """
        url = f"{GITHUB_API}/repos/{owner}/{repo}/languages"
        data = self._make_request(url)

        if not data or not isinstance(data, dict):
            return {}

        total = sum(data.values())
        if total == 0:
            return {}

        return {lang: (bytes_count / total) * 100 for lang, bytes_count in data.items()}

    def get_repo_readme(self, owner: str, repo: str) -> str | None:
        """Fetch README content.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            README content as string, or None
        """
        url = f"{GITHUB_API}/repos/{owner}/{repo}/readme"
        data = self._make_request(url)

        if not isinstance(data, dict) or "content" not in data:
            return None

        try:
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content
        except Exception:
            return None

    def get_github_pages_url(self, owner: str, repo: str) -> str | None:
        """Check if repository has GitHub Pages enabled.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            GitHub Pages URL if enabled, None otherwise
        """
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pages"
        data = self._make_request(url)

        if isinstance(data, dict) and "html_url" in data:
            result: str = data["html_url"]
            return result
        return None


def check_rate_limit(token: str | None = None) -> None:
    """Display current GitHub API rate limit status.

    Args:
        token: GitHub personal access token
    """
    client = GitHubClient(token)
    data = client.get_rate_limit()

    if not data:
        console.print("[red]Could not fetch rate limit info[/red]")
        return

    core = data.get("resources", {}).get("core", {})
    remaining = core.get("remaining", 0)
    limit = core.get("limit", 0)
    reset_timestamp = core.get("reset", 0)

    reset_time = datetime.fromtimestamp(reset_timestamp)

    # Show auth status (5000 = authenticated, 60 = unauthenticated)
    auth_status = "[green]authenticated[/green]" if limit > 60 else "[yellow]unauthenticated[/yellow]"
    console.print(f"[cyan]Auth status:[/cyan] {auth_status} (limit: {limit}/hour)")
    console.print(f"[cyan]Rate limit:[/cyan] {remaining}/{limit} remaining")
    console.print(f"[cyan]Resets at:[/cyan] {reset_time.strftime('%H:%M:%S')}")

    if remaining < 10:
        console.print("[yellow]Warning: Low rate limit remaining![/yellow]")
