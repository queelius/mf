# Tool Orchestration Guide

This document explains how `mf`, `repoindex`, and `crier` work together to manage the metafunctor.com site. It's written for Claude Code to understand when and how to use each tool.

## Tool Overview

| Tool | Role | Data Flow |
|------|------|-----------|
| **repoindex** | Source of truth for repos | Read-only queries, events, package status |
| **mf** | Site content management | Transforms data → Hugo content |
| **crier** | Content distribution | Publishes content → external platforms |

```
repoindex (data source)
    ↓ query/events
mf (transform)
    ↓ generate content
Hugo site (metafunctor.com)
    ↓ select posts
crier (distribute)
    ↓ publish
Platforms (dev.to, Bluesky, etc.)
```

## When to Use Each Tool

### repoindex - "What's happening with my repos?"

Use repoindex when the user wants to:
- See recent activity across repos
- Find repos by language, topic, or tags
- Check for new package releases (PyPI, CRAN, npm)
- Get repo metadata without hitting GitHub API

```bash
# Recent activity
repoindex events --since 7d --pretty --stats

# With GitHub releases and PRs
repoindex events --github --pypi --since 7d --pretty

# Find repos
repoindex query "language == 'Python'" --pretty
repoindex query "package.published == true" --pretty

# Check status
repoindex status --pretty
```

### mf - "Manage my site content"

Use mf when the user wants to:
- Process a new LaTeX paper
- Update project pages
- Check paper staleness
- Query the paper/project databases

```bash
# Papers
mf papers list                     # List all papers
mf papers stats                    # Database statistics
mf papers sync                     # Check for stale papers
mf papers process /path/to.tex     # Process new paper
mf papers generate                 # Regenerate Hugo content

# Projects
mf projects list                   # List projects
mf projects list --featured        # Featured projects only
mf projects stats                  # Database statistics
mf projects import --user queelius # Import from GitHub
mf projects refresh                # Refresh from GitHub
mf projects fields                 # List valid project fields
mf projects set <slug> <field> <value>  # Set a field
mf projects feature <slug>         # Toggle featured
mf projects hide <slug>            # Toggle hidden
mf projects tag <slug> --add <tag> # Manage tags

# Papers (field operations)
mf papers fields                   # List valid paper fields
mf papers set <slug> <field> <value>  # Set a field
mf papers feature <slug>           # Toggle featured
mf papers tag <slug> --add <tag>   # Manage tags

# Series (field operations)
mf series fields                   # List valid series fields
mf series set <slug> <field> <value>  # Set a field
mf series feature <slug>           # Toggle featured
mf series tag <slug> --add <tag>   # Manage tags

# Publications
mf pubs sync                       # Sync to paper database

# Backup management
mf backup status                   # Show backup statistics
mf backup list                     # List recent backups
mf backup clean                    # Clean old backups (30+ days)
mf backup clean --dry-run          # Preview cleanup
mf backup rollback paper_db        # Restore from backup

# Configuration
mf config show --all               # Show all settings
mf config set backup.keep_days 14  # Change retention
```

### crier - "Share my content"

Use crier when the user wants to:
- Cross-post a blog post
- Announce a new paper or release
- Share content to social platforms

```bash
# Publish to platforms
crier publish post.md --to devto --to bluesky --to mastodon

# List configured platforms
crier platforms

# List published articles
crier list devto
```

## Common Workflows

### 1. "What's new this week?"

```bash
# Check repo activity
repoindex events --since 7d --github --pypi --pretty --stats

# If projects need updating
mf projects refresh --older-than 168  # 7 days in hours
```

### 2. "Process a new paper"

```bash
# 1. Process the LaTeX
mf papers process /path/to/paper.tex --slug my-paper

# 2. Verify it's in the database
mf papers show my-paper

# 3. (Optional) Write announcement post in content/post/
# 4. Cross-post if desired
crier publish content/post/2024-01-new-paper/index.md --to devto --to bluesky
```

### 3. "Update project pages after releases"

```bash
# 1. Check for recent PyPI/CRAN releases
repoindex events --pypi --cran --since 7d --pretty

# 2. Refresh affected projects
mf projects refresh --slug affected-project

# 3. Or refresh all stale projects
mf projects refresh --older-than 24
```

### 4. "Announce a new PyPI release"

```bash
# 1. Verify the release
repoindex events --pypi --since 1d --pretty

# 2. Refresh project page
mf projects refresh --slug package-name

# 3. Write announcement (in content/post/)
# 4. Cross-post
crier publish content/post/2024-01-release/index.md --to devto --to bluesky --to mastodon
```

### 5. "Cross-post a blog article"

```bash
# 1. List recent posts
ls -la content/post/ | tail -10

# 2. Publish to configured platforms
crier publish content/post/2024-01-my-post/index.md --to devto --to hashnode --to bluesky

# 3. Verify
crier list devto
```

### 6. "Find and update stale projects"

```bash
# 1. Check which projects have recent commits but stale site pages
repoindex events --type commit --since 7d --pretty

# 2. Compare with mf project sync times
mf projects list --json | jq 'sort_by(.last_synced)'

# 3. Refresh stale ones
mf projects refresh --older-than 24
```

### 7. "Manage backups"

```bash
# 1. Check backup status
mf backup status

# 2. Clean up old backups (uses configured retention)
mf backup clean --dry-run    # Preview first
mf backup clean              # Actually clean

# 3. If something went wrong, rollback
mf backup rollback paper_db        # Restore most recent
mf backup rollback paper_db -i 1   # Or second most recent

# 4. Adjust retention settings if needed
mf config set backup.keep_days 14    # Keep backups for 14 days
mf config set backup.keep_count 5    # Keep at least 5 backups
```

## Data Flow Patterns

### Projects: repoindex → mf → Hugo

repoindex is authoritative for repo metadata. mf should ideally consume repoindex data:

```bash
# Current: mf hits GitHub API directly
mf projects import --user queelius

# Future enhancement: mf could read from repoindex
# repoindex query "owner == 'queelius'" --json-full | mf projects import --from-stdin
```

For now, use repoindex for queries/discovery, mf for content generation.

### Papers: LaTeX → mf → Hugo

Papers flow through mf exclusively:

```
paper.tex → mf papers process → /static/latex/slug/ + paper_db.json
                              → mf papers generate → /content/papers/slug/
```

### Distribution: Hugo content → crier → Platforms

Any markdown with frontmatter can be cross-posted:

```
content/post/*/index.md → crier publish → dev.to, Hashnode, Bluesky, etc.
```

## Database Locations

| Database | Purpose | Tool |
|----------|---------|------|
| `scripts/paper_db.json` | Paper metadata + source tracking | mf |
| `scripts/projects_db.json` | Project manual overrides | mf |
| `scripts/projects_cache.json` | GitHub API cache | mf |
| `scripts/mf/config.json` | mf settings (backup retention, etc.) | mf |
| `scripts/backups/` | Paper database backups | mf |
| `scripts/projects_backup/` | Projects database backups | mf |
| `~/.config/repoindex/` | Repo metadata store | repoindex |
| `~/.config/crier/config.json` | Platform credentials | crier |

## Environment Variables

```bash
GITHUB_TOKEN      # Higher API rate limits for mf and repoindex
MF_SITE_ROOT      # Override Hugo site root detection
```

## Tips for Claude Code

1. **Start with repoindex for discovery**: Before updating projects, check what's actually changed with `repoindex events`.

2. **Use mf for site-specific operations**: Paper processing, project page generation, database queries.

3. **Use crier for distribution**: After content is ready, cross-post to platforms.

4. **Prefer dry-run first**: Both mf and crier support `--dry-run` to preview changes.

5. **Check platform configuration**: `crier platforms` shows which are configured before attempting to publish.

6. **Query before bulk operations**: Use `mf papers list` or `mf projects list` with filters before running sync/refresh.
