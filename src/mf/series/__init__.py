"""Series management module for mf CLI.

Provides commands for managing content series and syncing
with external source repositories.
"""

from mf.series.commands import series
from mf.series.mkdocs import (
    copy_posts_to_mkdocs,
    execute_mkdocs_sync,
    generate_links_md,
    update_mkdocs_nav,
    validate_mkdocs_repo,
)
from mf.series.syncer import (
    ConflictResolution,
    PostSyncItem,
    SyncAction,
    SyncPlan,
    execute_sync,
    generate_diff,
    list_syncable_series,
    plan_pull_sync,
    plan_push_sync,
    print_conflict_diff,
)

__all__ = [
    "series",
    "SyncAction",
    "SyncPlan",
    "PostSyncItem",
    "ConflictResolution",
    "plan_pull_sync",
    "plan_push_sync",
    "execute_sync",
    "list_syncable_series",
    "generate_diff",
    "print_conflict_diff",
    "validate_mkdocs_repo",
    "copy_posts_to_mkdocs",
    "generate_links_md",
    "update_mkdocs_nav",
    "execute_mkdocs_sync",
]
