"""
GitHub repository importer.

Import and sync GitHub repositories to Hugo content.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from typing import Any

from rich.console import Console

from mf.core.config import get_paths
from mf.core.database import ProjectsCache, ProjectsDatabase
from mf.projects.generator import generate_project_content, merge_project_data
from mf.projects.github import GitHubClient, check_rate_limit

console = Console()


def filter_repos(
    repos: list[dict],
    exclude_forks: bool = False,
    exclude_archived: bool = False,
    min_stars: int | None = None,
    has_description: bool = False,
    languages: list[str] | None = None,
    topics: list[str] | None = None,
) -> list[dict]:
    """Filter repositories based on criteria.

    Args:
        repos: List of repository data
        exclude_forks: Exclude forked repositories
        exclude_archived: Exclude archived repositories
        min_stars: Minimum number of stars
        has_description: Only repos with descriptions
        languages: Filter by language(s)
        topics: Filter by topic(s)

    Returns:
        Filtered list of repositories
    """
    filtered = repos

    if exclude_forks:
        filtered = [r for r in filtered if not r.get("fork", False)]

    if exclude_archived:
        filtered = [r for r in filtered if not r.get("archived", False)]

    if min_stars:
        filtered = [r for r in filtered if r.get("stargazers_count", 0) >= min_stars]

    if has_description:
        filtered = [r for r in filtered if r.get("description")]

    if languages:
        langs_lower = [lang.lower() for lang in languages]
        filtered = [r for r in filtered if (r.get("language") or "").lower() in langs_lower]

    if topics:
        required_topics = {t.lower() for t in topics}
        filtered = [
            r for r in filtered
            if required_topics.issubset({t.lower() for t in r.get("topics", [])})
        ]

    return filtered


def extract_repo_metadata(
    repo: dict,
    client: GitHubClient,
) -> dict[str, Any]:
    """Extract and augment GitHub repo data.

    Args:
        repo: Repository data from GitHub API
        client: GitHub API client

    Returns:
        Complete GitHub data dict (for caching)
    """
    owner = repo["owner"]["login"]
    name = repo["name"]

    # Start with the entire GitHub API response
    github_data = dict(repo)

    # Add sync metadata
    github_data["_last_synced"] = datetime.now(timezone.utc).isoformat()

    # Get language breakdown
    console.print("    Fetching languages...")
    languages = client.get_repo_languages(owner, name)
    if languages:
        github_data["_languages_breakdown"] = languages

    # Check for GitHub Pages
    console.print("    Checking GitHub Pages...")
    pages_url = client.get_github_pages_url(owner, name)
    if pages_url:
        github_data["_github_pages_url"] = pages_url
        console.print(f"    [green]✓[/green] Pages: {pages_url}")

    # Fetch README
    console.print("    Fetching README...")
    readme = client.get_repo_readme(owner, name)
    if readme:
        github_data["_readme_content"] = readme
        console.print(f"    [green]✓[/green] README ({len(readme)} bytes)")

    return github_data


def import_user_repos(
    username: str,
    token: str | None = None,
    exclude_forks: bool = False,
    exclude_archived: bool = False,
    min_stars: int | None = None,
    has_description: bool = False,
    languages: list[str] | None = None,
    topics: list[str] | None = None,
    include_private: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Import all repositories from a GitHub user.

    Args:
        username: GitHub username
        token: GitHub personal access token
        exclude_forks: Exclude forked repositories
        exclude_archived: Exclude archived repositories
        min_stars: Minimum number of stars
        has_description: Only repos with descriptions
        languages: Filter by language(s)
        topics: Filter by topic(s)
        include_private: Include private repositories
        force: Force overwrite existing projects
        dry_run: Preview only
    """
    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        console.print("=" * 60)
        console.print()

    client = GitHubClient(token)

    # Check rate limit first
    check_rate_limit(token)
    console.print()

    console.print(f"[cyan]Fetching repositories for: {username}[/cyan]")

    repos = client.get_user_repos(username, include_private)
    console.print(f"Found {len(repos)} repositories")

    # Filter repos
    filtered = filter_repos(
        repos,
        exclude_forks=exclude_forks,
        exclude_archived=exclude_archived,
        min_stars=min_stars,
        has_description=has_description,
        languages=languages,
        topics=topics,
    )
    console.print(f"After filtering: {len(filtered)} repositories")

    if dry_run:
        console.print("\n[yellow]Would import:[/yellow]")
        for repo in filtered:
            lang = repo.get("language", "Unknown")
            console.print(f"  - {repo['full_name']} ({lang})")
        return

    # Load existing data
    db = ProjectsDatabase()
    db.load()

    cache = ProjectsCache()
    cache.load()

    # Import each repo
    imported = 0
    skipped = 0

    for i, repo in enumerate(filtered):
        slug = repo["name"]

        # Skip if already exists (unless force)
        if slug in cache and not force:
            console.print(f"[dim]Skipping {slug} (exists, use --force)[/dim]")
            skipped += 1
            continue

        console.print(f"\n[cyan]Importing: {repo['full_name']}[/cyan]")

        # Extract GitHub data
        github_data = extract_repo_metadata(repo, client)

        # Store in cache
        cache.set(slug, github_data)

        # Merge with manual overrides
        overrides = db.get(slug) or {}
        merged = merge_project_data(slug, github_data, overrides)

        # Generate Hugo content
        generate_project_content(slug, merged)

        imported += 1

        # Polite delay between requests
        if i < len(filtered) - 1:
            time.sleep(0.5)

    # Save cache
    cache.save()

    console.print(f"\n[green]Imported {imported} projects[/green]")
    if skipped:
        console.print(f"[dim]Skipped {skipped} existing projects[/dim]")


def refresh_projects(
    slug: str | None = None,
    token: str | None = None,
    older_than: float | None = None,
    newer_than: float | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Refresh project data from GitHub.

    Args:
        slug: Refresh only this project (None = all)
        token: GitHub personal access token
        older_than: Only refresh if not synced in N hours
        newer_than: Only refresh if synced within N hours
        force: Force refresh even if unchanged
        dry_run: Preview only
    """
    if dry_run:
        console.print("=" * 60)
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")
        console.print("=" * 60)
        console.print()

    client = GitHubClient(token)
    check_rate_limit(token)
    console.print()

    cache = ProjectsCache()
    cache.load()

    db = ProjectsDatabase()
    db.load()

    if slug:
        # Single project
        if slug not in cache:
            console.print(f"[red]Project not found: {slug}[/red]")
            return
        projects = [slug]
    else:
        projects = list(cache)

    # Filter by time if specified
    if older_than or newer_than:
        now = datetime.now(timezone.utc)
        filtered = []

        for s in projects:
            cached = cache.get(s)
            last_synced_str: str | None = str(cached.get("_last_synced")) if cached and cached.get("_last_synced") else None

            if not last_synced_str:
                filtered.append(s)
                continue

            try:
                last_synced = datetime.fromisoformat(last_synced_str.replace("Z", "+00:00"))
                hours_since = (now - last_synced).total_seconds() / 3600

                if older_than and hours_since < older_than:
                    continue
                if newer_than and hours_since > newer_than:
                    continue

                filtered.append(s)
            except (ValueError, AttributeError):
                filtered.append(s)

        console.print(f"Filtered to {len(filtered)} projects based on sync time")
        projects = filtered

    if not projects:
        console.print("No projects to refresh")
        return

    console.print(f"Refreshing {len(projects)} project(s)...\n")

    updated = 0
    unchanged = 0

    for s in projects:
        cached = cache.get(s)
        if not cached:
            continue

        github_url = cached.get("html_url")
        if not github_url:
            continue

        # Parse owner/repo
        parts = github_url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1]

        console.print(f"Checking {s}...", end=" ")

        # Fetch current repo data
        repo_data = client.get_repo(owner, repo)
        if not repo_data:
            console.print("[red]Failed[/red]")
            continue

        # Check if changed
        cached_pushed_at = cached.get("pushed_at")
        current_pushed_at = repo_data.get("pushed_at")

        if cached_pushed_at == current_pushed_at and not force:
            console.print("[dim]No changes[/dim]")
            unchanged += 1

            # Update sync time but keep cached expensive data
            cached_readme = cached.get("_readme_content")
            cached_languages = cached.get("_languages_breakdown")

            cache.set(s, dict(repo_data))
            cached_new = cache.get(s)
            if cached_new is None:
                continue
            cached_new["_last_synced"] = datetime.now(timezone.utc).isoformat()
            if cached_readme:
                cached_new["_readme_content"] = cached_readme
            if cached_languages:
                cached_new["_languages_breakdown"] = cached_languages

            # Regenerate content with updated metadata
            overrides = db.get(s) or {}
            merged = merge_project_data(s, cached_new, overrides)
            generate_project_content(s, merged, dry_run)
            continue

        console.print("[cyan]Updating...[/cyan]")

        # Full refresh
        github_data = extract_repo_metadata(repo_data, client)
        cache.set(s, github_data)

        overrides = db.get(s) or {}
        merged = merge_project_data(s, github_data, overrides)
        generate_project_content(s, merged, dry_run)

        updated += 1
        time.sleep(0.5)

    # Save cache
    if not dry_run:
        cache.save()

    console.print(f"\n[green]Updated:[/green] {updated}")
    console.print(f"[dim]Unchanged:[/dim] {unchanged}")


def clean_stale_projects(
    username: str,
    token: str | None = None,
    include_private: bool = False,
    auto_confirm: bool = False,
    prune_overrides: bool = False,
    dry_run: bool = False,
) -> None:
    """Remove projects that no longer exist on GitHub.

    Also warns about orphaned overrides in projects_db.json.

    Args:
        username: GitHub username
        token: GitHub personal access token
        include_private: Include private repositories when checking
        auto_confirm: Skip confirmation prompts
        prune_overrides: Also remove orphaned overrides from projects_db.json
        dry_run: Preview only
    """
    console.print("Checking for stale projects...")

    client = GitHubClient(token)
    repos = client.get_user_repos(username, include_private=include_private)
    github_slugs = {repo["name"] for repo in repos}

    paths = get_paths()
    local_projects = []

    for item in paths.projects.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            local_projects.append(item.name)

    # Find stale content directories
    stale = [s for s in local_projects if s not in github_slugs]

    # Load databases
    cache = ProjectsCache()
    cache.load()

    db = ProjectsDatabase()
    db.load()

    # Find orphaned cache entries (in cache but not on GitHub)
    stale_cache = [s for s in cache if s not in github_slugs and s not in stale]

    # Find orphaned overrides (in db but not on GitHub, excluding special keys)
    special_keys = {"_comment", "_schema_version", "_example"}
    orphaned_overrides = [
        s for s in db._data
        if s not in special_keys and s not in github_slugs
    ]

    if not stale and not stale_cache:
        console.print("[green]No stale projects found[/green]")
    else:
        if stale:
            console.print(f"\n[yellow]Found {len(stale)} stale content dir(s):[/yellow]")
            for s in sorted(stale):
                console.print(f"  - {s}")

        if stale_cache:
            console.print(f"\n[yellow]Found {len(stale_cache)} orphaned cache entries:[/yellow]")
            for s in sorted(stale_cache):
                console.print(f"  - {s}")

    # Handle orphaned overrides
    if orphaned_overrides:
        if prune_overrides:
            console.print(f"\n[yellow]Found {len(orphaned_overrides)} orphaned override(s) to prune:[/yellow]")
            for s in sorted(orphaned_overrides):
                console.print(f"  - {s}")
        else:
            console.print(f"\n[cyan]Note: {len(orphaned_overrides)} override(s) in projects_db.json for non-existent repos:[/cyan]")
            for s in sorted(orphaned_overrides):
                console.print(f"  - {s} [dim](use --prune to remove)[/dim]")

    all_stale = set(stale) | set(stale_cache)
    if not all_stale and not (prune_overrides and orphaned_overrides):
        return

    if dry_run:
        console.print("\n[yellow](Dry run - nothing removed)[/yellow]")
        return

    # Confirm (unless auto_confirm)
    if not auto_confirm:
        from mf.core.prompts import confirm
        if not confirm(f"\nRemove {len(all_stale)} stale projects?"):
            console.print("Cancelled")
            return

    # Remove content directories and cache entries
    removed = 0
    for s in all_stale:
        project_dir = paths.projects / s
        try:
            if project_dir.exists():
                shutil.rmtree(project_dir)
            # Also remove from cache to prevent regeneration
            if s in cache:
                cache.delete(s)
            console.print(f"  [green]✓[/green] Removed {s}")
            removed += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed to remove {s}: {e}")

    # Save cache with deletions
    if removed > 0:
        cache.save()

    console.print(f"\n[green]Removed {removed} stale project(s)[/green]")

    # Prune orphaned overrides if requested
    if prune_overrides and orphaned_overrides:
        pruned = 0
        for s in orphaned_overrides:
            try:
                db.delete(s)
                console.print(f"  [green]✓[/green] Pruned override: {s}")
                pruned += 1
            except Exception as e:
                console.print(f"  [red]✗[/red] Failed to prune {s}: {e}")

        if pruned > 0:
            db.save()
            console.print(f"\n[green]Pruned {pruned} orphaned override(s) from projects_db.json[/green]")
