"""
Series synchronization between external source repos and metafunctor.

Syncs posts and landing pages from external series repositories
(e.g., ~/github/alpha/stepanov) to the metafunctor Hugo site.
"""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import frontmatter
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from mf.core.config import get_paths
from mf.core.crypto import compute_file_hash
from mf.core.database import SeriesDatabase, SeriesEntry

console = Console()

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")

ACTION_STYLES: dict[SyncAction, str] = {}  # Populated after SyncAction definition


def strip_date_prefix(slug: str) -> str:
    """Strip YYYY-MM-DD- date prefix from a slug, if present.

    Examples:
        "2024-01-01-test-post" -> "test-post"
        "2025-10-ctk"         -> "2025-10-ctk"  (not a full date)
        "algotree"            -> "algotree"       (no prefix)
    """
    return DATE_PREFIX_RE.sub("", slug)


class SyncAction(Enum):
    """Possible sync actions for a post."""

    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"
    RENAME = "rename"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


class ConflictResolution(Enum):
    """How to resolve sync conflicts."""

    SKIP = "skip"
    OURS = "ours"
    THEIRS = "theirs"


# Rich markup style per action, used by print_sync_plan
ACTION_STYLES = {
    SyncAction.ADD: "green",
    SyncAction.UPDATE: "yellow",
    SyncAction.RENAME: "blue",
    SyncAction.REMOVE: "red",
    SyncAction.UNCHANGED: "dim",
    SyncAction.CONFLICT: "magenta bold",
}


@dataclass
class PostSyncItem:
    """A single post to sync."""

    slug: str
    source_path: Path | None = None
    target_path: Path | None = None
    action: SyncAction = SyncAction.UNCHANGED
    source_hash: str | None = None
    target_hash: str | None = None
    reason: str = ""
    old_slug: str | None = None
    old_path: Path | None = None


@dataclass
class SyncPlan:
    """Plan for syncing a series."""

    series_slug: str
    direction: str  # "pull" or "push"
    posts: list[PostSyncItem] = field(default_factory=list)
    landing_page: PostSyncItem | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes to sync."""
        if any(item.action != SyncAction.UNCHANGED for item in self.posts):
            return True
        return bool(
            self.landing_page and self.landing_page.action != SyncAction.UNCHANGED
        )

    @property
    def add_count(self) -> int:
        return sum(1 for p in self.posts if p.action == SyncAction.ADD)

    @property
    def update_count(self) -> int:
        return sum(1 for p in self.posts if p.action == SyncAction.UPDATE)

    @property
    def remove_count(self) -> int:
        return sum(1 for p in self.posts if p.action == SyncAction.REMOVE)

    @property
    def rename_count(self) -> int:
        return sum(1 for p in self.posts if p.action == SyncAction.RENAME)

    @property
    def conflict_count(self) -> int:
        return sum(1 for p in self.posts if p.action == SyncAction.CONFLICT)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for p in self.posts if p.action == SyncAction.UNCHANGED)

    @property
    def conflicts(self) -> list[PostSyncItem]:
        """Get all conflicted posts."""
        return [p for p in self.posts if p.action == SyncAction.CONFLICT]


def _parse_series_from_dir(posts_dir: Path, slug: str) -> tuple[dict[str, Path], list[str]]:
    """Scan a directory for post bundles belonging to a series.

    Reads frontmatter from each index.md and checks for a matching series slug.

    Args:
        posts_dir: Directory containing post subdirectories
        slug: Series slug to match

    Returns:
        Tuple of (matched posts dict, skipped post names list)
    """
    posts: dict[str, Path] = {}
    skipped: list[str] = []

    for post_dir in posts_dir.iterdir():
        if not post_dir.is_dir():
            continue

        index_file = post_dir / "index.md"
        if not index_file.exists():
            continue

        try:
            post = frontmatter.load(index_file)
            series_list = post.get("series", [])
            if isinstance(series_list, str):
                series_list = [series_list]

            if slug in series_list:
                posts[post_dir.name] = post_dir
            else:
                skipped.append(post_dir.name)
        except Exception:
            skipped.append(post_dir.name)

    return posts, skipped


def get_source_posts(entry: SeriesEntry, verbose: bool = False) -> dict[str, Path]:
    """Get all posts from the source repository that belong to this series.

    Only includes posts where frontmatter contains `series: [slug]` matching
    the entry's slug. This ensures symmetric filtering with get_metafunctor_posts().

    Args:
        entry: Series entry with source_dir configured
        verbose: If True, print info about skipped posts

    Returns:
        Dict mapping post slug to source path
    """
    source_dir = entry.source_dir
    if not source_dir or not source_dir.exists():
        return {}

    posts_dir = source_dir / entry.posts_subdir
    if not posts_dir.exists():
        return {}

    posts, skipped = _parse_series_from_dir(posts_dir, entry.slug)

    if skipped and verbose:
        console.print(f"[dim]Skipped {len(skipped)} posts without series '{entry.slug}' in frontmatter[/dim]")

    return posts


def get_metafunctor_posts(slug: str) -> dict[str, Path]:
    """Get all posts in metafunctor that belong to this series.

    Args:
        slug: Series slug

    Returns:
        Dict mapping post slug to post directory path
    """
    paths = get_paths()
    posts_dir = paths.content / "post"
    posts, _skipped = _parse_series_from_dir(posts_dir, slug)
    return posts


def compute_post_hash(post_dir: Path) -> str:
    """Compute a hash for a post directory.

    Hashes only the index.md file, since that is what sync transfers.
    Extra files (source code, images, etc.) in the target directory are
    preserved by sync and should not affect the hash.
    """
    index_file = post_dir / "index.md"
    if not index_file.exists():
        raise FileNotFoundError(f"No index.md in post directory: {post_dir}")
    return compute_file_hash(index_file)


def _detect_renames(plan: SyncPlan) -> None:
    """Detect renames among unmatched ADD/REMOVE pairs.

    Mutates plan.posts in-place: converts matching ADD+REMOVE pairs into
    a single RENAME item when their base slugs (date-prefix stripped) match.

    Only matches when exactly 1 ADD and 1 REMOVE share a base slug
    (conservative: ambiguous cases are left as ADD+REMOVE).
    """
    adds = [p for p in plan.posts if p.action == SyncAction.ADD]
    removes = [p for p in plan.posts if p.action == SyncAction.REMOVE]

    if not adds or not removes:
        return

    # Group by base slug
    add_by_base: dict[str, list[PostSyncItem]] = {}
    for item in adds:
        base = strip_date_prefix(item.slug)
        add_by_base.setdefault(base, []).append(item)

    remove_by_base: dict[str, list[PostSyncItem]] = {}
    for item in removes:
        base = strip_date_prefix(item.slug)
        remove_by_base.setdefault(base, []).append(item)

    # Find unambiguous 1-to-1 matches
    matched_removes: set[int] = set()
    renames: list[tuple[PostSyncItem, PostSyncItem]] = []

    for base_slug, add_group in add_by_base.items():
        remove_group = remove_by_base.get(base_slug)
        if not remove_group:
            continue

        if len(add_group) != 1 or len(remove_group) != 1:
            continue

        add_item = add_group[0]
        remove_item = remove_group[0]

        # Guard against identical slugs (should not happen, but be safe)
        if add_item.slug == remove_item.slug:
            continue

        renames.append((add_item, remove_item))
        matched_removes.add(id(remove_item))

    # Convert matched pairs to RENAME items
    for add_item, remove_item in renames:
        add_item.action = SyncAction.RENAME
        add_item.old_slug = remove_item.slug
        add_item.old_path = (
            remove_item.target_path if plan.direction == "pull"
            else remove_item.source_path
        )
        add_item.reason = f"renamed from {remove_item.slug}"

    # Remove the matched REMOVE items from plan
    plan.posts = [p for p in plan.posts if id(p) not in matched_removes]


def _classify_existing_post(
    post_slug: str,
    source_hash: str,
    target_hash: str,
    sync_state: dict[str, dict[str, str | None]],
    origin_is_source: bool,
) -> tuple[SyncAction, str]:
    """Classify an existing post (present in both sides) as UPDATE, CONFLICT, or UNCHANGED.

    The logic is symmetric: for pull, the "origin" is the source side; for push,
    the "origin" is the metafunctor (target) side. The origin side drives updates.

    Args:
        post_slug: Slug of the post
        source_hash: Current hash of source version
        target_hash: Current hash of target (metafunctor) version
        sync_state: Stored sync state from the database
        origin_is_source: True for pull (source drives), False for push (target drives)

    Returns:
        Tuple of (action, reason)
    """
    stored = sync_state.get(post_slug, {})
    stored_source_hash = stored.get("source_hash")
    stored_target_hash = stored.get("target_hash")

    source_changed = stored_source_hash != source_hash
    target_changed = stored_target_hash != target_hash

    if origin_is_source:
        # Pull: source drives. Target is "non-origin".
        # On first sync (no stored target hash), detect divergence.
        if stored_target_hash is None and target_hash != source_hash:
            target_changed = True
        # For pull, only require stored hash for target-side change detection
        # (source change is always detectable by comparing stored vs current)
    else:
        # Push: target drives. Source is "non-origin".
        # Only flag source_changed when there is a stored hash to compare against
        source_changed = stored_source_hash is not None and stored_source_hash != source_hash

    # Determine action
    origin_changed = source_changed if origin_is_source else target_changed
    non_origin_changed = target_changed if origin_is_source else source_changed

    if origin_changed and non_origin_changed:
        return SyncAction.CONFLICT, "both source and metafunctor modified"

    if origin_changed:
        origin_label = "source" if origin_is_source else "metafunctor"
        stored_origin_hash = stored_source_hash if origin_is_source else stored_target_hash
        reason = f"modified in {origin_label}" if stored_origin_hash else "no stored hash"
        return SyncAction.UPDATE, reason

    return SyncAction.UNCHANGED, ""


def _validate_source_dir(entry: SeriesEntry, plan: SyncPlan) -> Path | None:
    """Validate that the series has an accessible source directory.

    Appends errors to plan.errors if validation fails.

    Returns:
        The source directory Path, or None if validation failed.
    """
    if not entry.has_source():
        plan.errors.append("No source_dir configured for this series")
        return None

    source_dir = entry.source_dir
    assert source_dir is not None
    if not source_dir.exists():
        plan.errors.append(f"Source directory not found: {source_dir}")
        return None

    return source_dir


def plan_pull_sync(
    entry: SeriesEntry,
    include_landing: bool = True,
    include_posts: bool = True,
) -> SyncPlan:
    """Plan a pull sync (source -> metafunctor).

    Args:
        entry: Series entry with source_dir configured
        include_landing: Include landing page in sync
        include_posts: Include posts in sync

    Returns:
        SyncPlan with actions to take
    """
    plan = SyncPlan(series_slug=entry.slug, direction="pull")
    paths = get_paths()

    source_dir = _validate_source_dir(entry, plan)
    if source_dir is None:
        return plan

    if include_posts:
        source_posts = get_source_posts(entry)
        target_posts = get_metafunctor_posts(entry.slug)
        sync_state = entry.sync_state

        # Check for new/updated posts from source (the origin side for pull)
        for post_slug, source_path in source_posts.items():
            current_source_hash = compute_post_hash(source_path)
            target_path = paths.content / "post" / post_slug

            if post_slug not in target_posts:
                plan.posts.append(PostSyncItem(
                    slug=post_slug,
                    source_path=source_path,
                    target_path=target_path,
                    action=SyncAction.ADD,
                    source_hash=current_source_hash,
                    reason="new in source",
                ))
            else:
                current_target_hash = compute_post_hash(target_posts[post_slug])
                action, reason = _classify_existing_post(
                    post_slug, current_source_hash, current_target_hash,
                    sync_state, origin_is_source=True,
                )
                plan.posts.append(PostSyncItem(
                    slug=post_slug,
                    source_path=source_path,
                    target_path=target_posts[post_slug],
                    action=action,
                    source_hash=current_source_hash,
                    target_hash=current_target_hash,
                    reason=reason,
                ))

        # Posts removed from source
        for post_slug, target_path in target_posts.items():
            if post_slug not in source_posts:
                plan.posts.append(PostSyncItem(
                    slug=post_slug,
                    target_path=target_path,
                    action=SyncAction.REMOVE,
                    reason="missing from source",
                ))

        _detect_renames(plan)

    # Plan landing page sync
    if include_landing and entry.landing_page:
        source_landing = source_dir / entry.landing_page
        target_landing = paths.content / "series" / entry.slug / "_index.md"

        if source_landing.exists():
            source_hash = compute_file_hash(source_landing)
            stored_state = entry.sync_state.get("_landing_page", {})
            stored_source_hash = stored_state.get("source_hash") if isinstance(stored_state, dict) else stored_state

            if not target_landing.exists():
                action = SyncAction.ADD
                reason = "new landing page"
            elif stored_source_hash != source_hash:
                action = SyncAction.UPDATE
                reason = "landing page modified"
            else:
                action = SyncAction.UNCHANGED
                reason = ""

            plan.landing_page = PostSyncItem(
                slug="_landing_page",
                source_path=source_landing,
                target_path=target_landing,
                action=action,
                source_hash=source_hash,
                reason=reason,
            )

    return plan


def plan_push_sync(
    entry: SeriesEntry,
    include_landing: bool = True,
    include_posts: bool = True,
) -> SyncPlan:
    """Plan a push sync (metafunctor -> source).

    Args:
        entry: Series entry with source_dir configured
        include_landing: Include landing page in sync
        include_posts: Include posts in sync

    Returns:
        SyncPlan with actions to take
    """
    plan = SyncPlan(series_slug=entry.slug, direction="push")
    paths = get_paths()

    source_dir = _validate_source_dir(entry, plan)
    if source_dir is None:
        return plan

    if include_posts:
        source_posts = get_source_posts(entry)
        target_posts = get_metafunctor_posts(entry.slug)
        sync_state = entry.sync_state

        # Check for new/updated posts from metafunctor (the origin side for push)
        for post_slug, mf_path in target_posts.items():
            current_target_hash = compute_post_hash(mf_path)
            source_path_for_slug = source_dir / entry.posts_subdir / post_slug

            if post_slug not in source_posts:
                plan.posts.append(PostSyncItem(
                    slug=post_slug,
                    source_path=source_path_for_slug,
                    target_path=mf_path,
                    action=SyncAction.ADD,
                    target_hash=current_target_hash,
                    reason="new in metafunctor",
                ))
            else:
                current_source_hash = compute_post_hash(source_posts[post_slug])
                action, reason = _classify_existing_post(
                    post_slug, current_source_hash, current_target_hash,
                    sync_state, origin_is_source=False,
                )
                plan.posts.append(PostSyncItem(
                    slug=post_slug,
                    source_path=source_posts[post_slug],
                    target_path=mf_path,
                    action=action,
                    source_hash=current_source_hash,
                    target_hash=current_target_hash,
                    reason=reason,
                ))

        # Posts only in source (removed from metafunctor)
        for post_slug, source_path in source_posts.items():
            if post_slug not in target_posts:
                plan.posts.append(PostSyncItem(
                    slug=post_slug,
                    source_path=source_path,
                    action=SyncAction.REMOVE,
                    reason="missing from metafunctor",
                ))

        _detect_renames(plan)

    # Plan landing page sync (push)
    if include_landing and entry.landing_page:
        target_landing = paths.content / "series" / entry.slug / "_index.md"
        source_landing = source_dir / entry.landing_page

        if target_landing.exists():
            target_hash = compute_file_hash(target_landing)

            if not source_landing.exists():
                action = SyncAction.ADD
                reason = "new landing page in metafunctor"
            else:
                source_hash = compute_file_hash(source_landing)
                if source_hash != target_hash:
                    action = SyncAction.UPDATE
                    reason = "landing page modified in metafunctor"
                else:
                    action = SyncAction.UNCHANGED
                    reason = ""

            plan.landing_page = PostSyncItem(
                slug="_landing_page",
                source_path=source_landing,
                target_path=target_landing,
                action=action,
                source_hash=target_hash,
                reason=reason,
            )

    return plan


def _get_copy_paths(item: PostSyncItem, direction: str) -> tuple[Path, Path]:
    """Return (copy_from, copy_to) paths based on sync direction.

    For pull: source -> target. For push: target -> source.
    """
    assert item.source_path is not None and item.target_path is not None
    if direction == "pull":
        return item.source_path, item.target_path
    return item.target_path, item.source_path


def _update_sync_state_after_copy(
    entry: SeriesEntry,
    item: PostSyncItem,
    direction: str,
) -> None:
    """Update sync state after a successful copy (ADD, UPDATE, or RENAME).

    Computes the fresh hash for the destination side and records both hashes.
    """
    if direction == "pull":
        new_target_hash = compute_post_hash(item.target_path)  # type: ignore[arg-type]
        entry.set_sync_state(
            item.slug,
            source_hash=item.source_hash,
            target_hash=new_target_hash,
        )
    else:
        new_source_hash = compute_post_hash(item.source_path)  # type: ignore[arg-type]
        entry.set_sync_state(
            item.slug,
            source_hash=new_source_hash,
            target_hash=item.target_hash,
        )


def execute_sync(
    plan: SyncPlan,
    db: SeriesDatabase,
    delete: bool = False,
    dry_run: bool = False,
    conflict_resolution: ConflictResolution = ConflictResolution.SKIP,
) -> tuple[int, int, int]:
    """Execute a sync plan.

    Args:
        plan: The sync plan to execute
        db: Series database (for updating sync state)
        delete: Whether to delete removed posts
        dry_run: Preview only, don't make changes
        conflict_resolution: How to resolve conflicts (default: skip)

    Returns:
        Tuple of (success_count, failure_count, skipped_conflicts)
    """
    entry = db.get(plan.series_slug)
    if not entry:
        console.print(f"[red]Series not found: {plan.series_slug}[/red]")
        return (0, 0, 0)

    success = 0
    failures = 0
    skipped_conflicts = 0

    for item in plan.posts:
        if item.action == SyncAction.UNCHANGED:
            continue

        try:
            # Resolve conflicts first
            if item.action == SyncAction.CONFLICT:
                resolved_action = resolve_conflict(item, conflict_resolution, plan.direction)
                if resolved_action == SyncAction.UNCHANGED:
                    console.print(f"  [magenta]conflict skipped:[/magenta] {item.slug}")
                    skipped_conflicts += 1
                    continue
                item.action = resolved_action

            if item.action in (SyncAction.ADD, SyncAction.UPDATE):
                if item.source_path is None or item.target_path is None:
                    console.print(f"  [red]error:[/red] {item.slug} - missing source or target path")
                    failures += 1
                    continue
                copy_from, copy_to = _get_copy_paths(item, plan.direction)
                if not dry_run:
                    copy_post_directory(copy_from, copy_to)
                    _update_sync_state_after_copy(entry, item, plan.direction)
                console.print(f"  [green]{item.action.value}:[/green] {item.slug}")
                success += 1

            elif item.action == SyncAction.RENAME:
                if item.source_path is None or item.target_path is None:
                    console.print(f"  [red]error:[/red] {item.slug} - missing source or target path")
                    failures += 1
                    continue
                copy_from, copy_to = _get_copy_paths(item, plan.direction)
                if not dry_run:
                    copy_post_directory(copy_from, copy_to)
                    if item.old_path and item.old_path.exists():
                        shutil.rmtree(item.old_path)
                    if item.old_slug:
                        entry.clear_sync_state(item.old_slug)
                    _update_sync_state_after_copy(entry, item, plan.direction)
                console.print(f"  [blue]rename:[/blue] {item.old_slug} -> {item.slug}")
                success += 1

            elif item.action == SyncAction.REMOVE:
                if delete:
                    if not dry_run:
                        # Delete from the destination side
                        delete_path = item.target_path if plan.direction == "pull" else item.source_path
                        if delete_path:
                            shutil.rmtree(delete_path)
                            entry.clear_sync_state(item.slug)
                    console.print(f"  [red]removed:[/red] {item.slug}")
                    success += 1
                else:
                    console.print(f"  [yellow]skipped (use --delete):[/yellow] {item.slug}")

        except Exception as e:
            console.print(f"  [red]error:[/red] {item.slug} - {e}")
            failures += 1

    # Handle landing page
    if plan.landing_page and plan.landing_page.action != SyncAction.UNCHANGED:
        item = plan.landing_page
        try:
            if item.action in (SyncAction.ADD, SyncAction.UPDATE):
                if item.source_path is None or item.target_path is None:
                    console.print("[red]landing page error:[/red] missing source or target path")
                    failures += 1
                elif plan.direction == "pull":
                    if not dry_run:
                        copy_landing_page(item.source_path, item.target_path)
                        entry.set_sync_state(
                            "_landing_page",
                            source_hash=item.source_hash,
                            target_hash=compute_file_hash(item.target_path),
                        )
                    console.print(f"  [green]landing page {item.action.value}[/green]")
                    success += 1
                else:
                    if not dry_run:
                        copy_landing_page(item.target_path, item.source_path)
                        entry.set_sync_state(
                            "_landing_page",
                            source_hash=compute_file_hash(item.source_path),
                            target_hash=item.source_hash,
                        )
                    console.print(f"  [green]landing page {item.action.value}[/green]")
                    success += 1

            elif item.action == SyncAction.REMOVE and delete:
                if not dry_run:
                    delete_path = item.target_path if plan.direction == "pull" else item.source_path
                    if delete_path:
                        delete_path.unlink(missing_ok=True)
                        entry.clear_sync_state("_landing_page")
                console.print("  [red]landing page removed[/red]")
                success += 1

        except Exception as e:
            console.print(f"  [red]landing page error:[/red] {e}")
            failures += 1

    if not dry_run and success > 0:
        db.save()

    return (success, failures, skipped_conflicts)


def copy_post_directory(source: Path, target: Path) -> None:
    """Copy a post directory, preserving extra files in target.

    Copies all files from source into target, overwriting files that exist
    in both. Files that exist only in target are preserved (e.g., source
    code, tests, examples that aren't part of the synced content).

    Args:
        source: Source post directory
        target: Target post directory
    """
    shutil.copytree(source, target, dirs_exist_ok=True)


def copy_landing_page(source: Path, target: Path) -> None:
    """Copy a landing page file.

    Args:
        source: Source markdown file
        target: Target markdown file
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def print_sync_plan(plan: SyncPlan, verbose: bool = False, show_diff: bool = False) -> None:
    """Print a sync plan summary.

    Args:
        plan: The sync plan to display
        verbose: Show all posts, not just changes
        show_diff: Show unified diff for conflicted posts
    """
    if plan.errors:
        for error in plan.errors:
            console.print(f"[red]Error: {error}[/red]")
        return

    direction_str = "source -> metafunctor" if plan.direction == "pull" else "metafunctor -> source"
    panel_content = (
        f"[cyan]Series:[/cyan] {plan.series_slug}\n"
        f"[cyan]Direction:[/cyan] {direction_str}\n"
        f"[cyan]Posts:[/cyan] {len(plan.posts)} total\n"
        f"  [green]Add:[/green] {plan.add_count}\n"
        f"  [yellow]Update:[/yellow] {plan.update_count}\n"
        f"  [blue]Rename:[/blue] {plan.rename_count}\n"
        f"  [red]Remove:[/red] {plan.remove_count}\n"
    )
    if plan.conflict_count > 0:
        panel_content += f"  [magenta bold]Conflict:[/magenta bold] {plan.conflict_count}\n"
    panel_content += f"  [dim]Unchanged:[/dim] {plan.unchanged_count}"

    console.print(Panel(panel_content, title="Sync Plan"))

    if plan.has_changes or verbose:
        table = Table(title="Posts")
        table.add_column("Slug", style="cyan")
        table.add_column("Action", style="bold")
        table.add_column("Reason")

        for item in sorted(plan.posts, key=lambda x: x.slug):
            if item.action == SyncAction.UNCHANGED and not verbose:
                continue

            style = ACTION_STYLES.get(item.action, "")

            slug_display = item.slug
            if item.action == SyncAction.RENAME and item.old_slug:
                slug_display = f"{item.old_slug} -> {item.slug}"

            reason = item.reason
            if item.action in (SyncAction.CONFLICT, SyncAction.UPDATE) and item.source_path and item.target_path:
                diffstat = generate_diffstat(item.source_path, item.target_path)
                if diffstat:
                    reason = f"{diffstat} ({reason})" if reason else diffstat

            table.add_row(
                slug_display,
                f"[{style}]{item.action.value}[/{style}]",
                reason,
            )

        if table.row_count > 0:
            console.print(table)

    if show_diff and plan.conflict_count > 0:
        console.print("\n[magenta bold]Conflict Details:[/magenta bold]")
        for item in plan.conflicts:
            print_conflict_diff(item)

    if plan.landing_page:
        lp = plan.landing_page
        if lp.action != SyncAction.UNCHANGED or verbose:
            style = ACTION_STYLES.get(lp.action, "")
            reason = lp.reason
            if lp.action in (SyncAction.CONFLICT, SyncAction.UPDATE) and lp.source_path and lp.target_path:
                diffstat = generate_diffstat(lp.source_path, lp.target_path)
                if diffstat:
                    reason = f"{diffstat} ({reason})" if reason else diffstat
            console.print(f"\n[cyan]Landing page:[/cyan] [{style}]{lp.action.value}[/{style}] - {reason}")


def list_syncable_series(db: SeriesDatabase) -> list[SeriesEntry]:
    """Get all series with source_dir configured.

    Args:
        db: Series database

    Returns:
        List of series entries with source configuration
    """
    return [entry for _, entry in db.items() if entry.has_source()]


def generate_diffstat(source_path: Path, target_path: Path) -> str:
    """Generate a compact diffstat string like ``+5 -2 lines``.

    Works with both post directories (reads ``index.md`` inside) and plain
    files (for landing pages).

    Args:
        source_path: Source post directory or file.
        target_path: Target post directory or file.

    Returns:
        Diffstat string, or empty string if files are identical or missing.
    """
    # Resolve to actual files
    source_file = source_path / "index.md" if source_path.is_dir() else source_path
    target_file = target_path / "index.md" if target_path.is_dir() else target_path

    if not source_file.exists() or not target_file.exists():
        return ""

    source_lines = source_file.read_text(encoding="utf-8").splitlines(keepends=True)
    target_lines = target_file.read_text(encoding="utf-8").splitlines(keepends=True)

    added = 0
    removed = 0
    for line in difflib.unified_diff(source_lines, target_lines):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1

    if added == 0 and removed == 0:
        return ""

    return f"+{added} -{removed} lines"


def generate_diff(source_path: Path, target_path: Path) -> list[str]:
    """Generate a unified diff between source and target index.md files.

    Args:
        source_path: Path to source post directory
        target_path: Path to target post directory

    Returns:
        List of diff lines
    """
    source_file = source_path / "index.md"
    target_file = target_path / "index.md"

    source_lines = source_file.read_text(encoding="utf-8").splitlines(keepends=True) if source_file.exists() else []
    target_lines = target_file.read_text(encoding="utf-8").splitlines(keepends=True) if target_file.exists() else []

    return list(difflib.unified_diff(
        source_lines,
        target_lines,
        fromfile=f"source/{source_path.name}/index.md",
        tofile=f"metafunctor/{target_path.name}/index.md",
        lineterm="",
    ))


def print_conflict_diff(item: PostSyncItem) -> None:
    """Print the diff for a conflicted post.

    Args:
        item: The conflicted PostSyncItem
    """
    console.print(f"\n[magenta bold]CONFLICT:[/magenta bold] {item.slug}")

    if not item.source_path or not item.target_path:
        console.print("  [dim]Cannot generate diff - missing path[/dim]")
        return

    diff_lines = generate_diff(item.source_path, item.target_path)

    if not diff_lines:
        console.print("  [dim]No textual differences in index.md (may differ in other files)[/dim]")
        return

    diff_text = "\n".join(diff_lines)
    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"Diff: {item.slug}", border_style="magenta"))


def resolve_conflict(
    item: PostSyncItem,
    resolution: ConflictResolution,
    direction: str,
) -> SyncAction:
    """Determine the action to take for a conflicted post based on resolution strategy.

    Args:
        item: The conflicted PostSyncItem
        resolution: How to resolve the conflict
        direction: "pull" or "push"

    Returns:
        The resolved SyncAction (UPDATE or UNCHANGED for skip)
    """
    if resolution == ConflictResolution.SKIP:
        return SyncAction.UNCHANGED

    if resolution == ConflictResolution.THEIRS:
        # "theirs" = source. For pull, source is what we are pulling, so update.
        # For push, source is the remote side, so skip (don't overwrite it).
        return SyncAction.UPDATE if direction == "pull" else SyncAction.UNCHANGED

    # OURS = metafunctor. For push, metafunctor is what we are pushing, so update.
    # For pull, metafunctor is the local side, so skip (don't overwrite it).
    return SyncAction.UPDATE if direction == "push" else SyncAction.UNCHANGED
