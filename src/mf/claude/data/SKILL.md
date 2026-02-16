---
name: mf
description: Use mf (metafunctor) to manage papers, projects, and content for the Hugo static site. Invoke for paper processing, project syncing, content linking, database queries, and backup operations.
---

# mf - Metafunctor Site Management

A CLI toolkit for managing the metafunctor.com Hugo static site. Syncs external sources (LaTeX papers, GitHub projects) to Hugo content.

## Quick Reference

```bash
# Papers - Process LaTeX and generate Hugo pages
mf papers process path/to/paper.tex    # Process a LaTeX file
mf papers sync                         # Sync all papers from database
mf papers list                         # List papers in database
mf papers generate                     # Regenerate Hugo content
mf papers fields                       # List valid paper fields
mf papers set <slug> <field> <value>   # Set paper field (--regenerate)
mf papers feature <slug>               # Toggle featured (--off, --regenerate)
mf papers tag <slug> --add <tag>       # Manage tags (--add/--remove/--set)

# Projects - Import from GitHub and generate pages
mf projects import --user queelius     # Import repos from GitHub
mf projects refresh                    # Update from GitHub API
mf projects generate                   # Generate Hugo content
mf projects list                       # List projects
mf projects fields                     # List valid project fields
mf projects set <slug> <field> <value> # Set project field (--regenerate)
mf projects feature <slug>             # Toggle featured (--off, --regenerate)
mf projects hide <slug>                # Toggle hidden (--off, --regenerate)
mf projects tag <slug> --add <tag>     # Manage tags (--add/--remove/--set)

# Content - Link posts to projects
mf content match-projects              # Find and link content to projects
mf content about <project>             # Find content about a project
mf content list-projects               # List projects with content counts

# Series - Manage content series
mf series list                         # List all series
mf series show stepanov                # Show series details
mf series sync stepanov                # Pull posts from source repo
mf series sync stepanov --push         # Push posts to source repo
mf series add stepanov content/post/   # Add post to series
mf series remove stepanov content/post # Remove post from series
mf series scan                         # Scan for series usage
mf series fields                       # List valid series fields
mf series set <slug> <field> <value>   # Set series field
mf series feature <slug>               # Toggle featured (--off)
mf series tag <slug> --add <tag>       # Manage tags (--add/--remove/--set)

# Backup - Manage database backups
mf backup list                         # List available backups
mf backup status                       # Show backup health
mf backup rollback paper_db            # Restore from backup

# Config - Settings management
mf config show                         # Show configuration
mf config set <key> <value>            # Set a value

# Analytics - Insights and relationship discovery
mf analytics summary                   # Full analytics overview
mf analytics projects                  # Projects ranked by content count
mf analytics gaps                      # Projects without linked content
mf analytics tags                      # Tag usage distribution
mf analytics timeline                  # Content activity over time
mf analytics suggestions               # Content-project link recommendations

# Integrity - Database health checks
mf integrity check                     # Run integrity checks
mf integrity fix --dry-run             # Preview fixes
mf integrity orphans                   # Find orphaned entries

# Extended Content Audit
mf content audit --list-checks         # Show available checks
mf content audit --extended            # Run all extended checks
mf content audit --check required_fields,stale_drafts
```

## Command Groups

| Command | Purpose |
|---------|---------|
| `mf papers` | LaTeX paper processing and Hugo page generation |
| `mf projects` | GitHub project import, metadata caching, content generation |
| `mf series` | Content series management and sync with external repos |
| `mf content` | Link Hugo content to projects via `linked_project` taxonomy |
| `mf analytics` | Content analytics, insights, and relationship discovery |
| `mf integrity` | Database consistency checking and repair |
| `mf backup` | Database backup management and rollback |
| `mf config` | Configuration management |
| `mf init` | Initialize .mf/ directory structure |
| `mf claude` | Manage this Claude Code skill |

## Global Options

- `-v, --verbose` - Enable verbose output
- `-n, --dry-run` - Preview changes without making them

## Project Structure

mf uses `.mf/` directory for its data:

```
.mf/
  paper_db.json           # Paper metadata database
  projects_db.json        # Project overrides and settings
  series_db.json          # Series metadata and sync state
  config.yaml             # Configuration
  cache/
    projects.json         # GitHub API cache (gitignored)
  backups/
    papers/               # Paper database backups
    projects/             # Projects database backups
    series/               # Series database backups
```

## Key Concepts

### Paper Database
Papers are tracked in `paper_db.json` with metadata like title, abstract, authors, tags, and source tracking (for LaTeX processing).

### Project Database
Projects have two layers:
1. **Cache** (`cache/projects.json`) - GitHub API data, auto-refreshed
2. **Overrides** (`projects_db.json`) - Manual metadata like `featured`, `hide`, `rich_project`

### Rich Projects
Projects marked `rich_project: true` get branch bundles with subsections:
- `content/projects/<slug>/_index.md` (main page)
- `content/projects/<slug>/docs/_index.md`
- `content/projects/<slug>/tutorials/_index.md`
- etc.

### Series Database
Series are thematic collections of posts tracked in `series_db.json`. Series can:
- Sync posts from external source repositories
- Track associations to papers, media, and external links
- Have landing pages in `content/series/<slug>/_index.md`

Series with `source_dir` configured can sync posts bidirectionally:
```bash
mf series sync stepanov           # Pull from ~/github/alpha/stepanov
mf series sync stepanov --push    # Push to source repo
```

### Content Linking
Use `linked_project` taxonomy (NOT `projects`) to link posts to projects:
```yaml
# In post front matter
linked_project:
  - "likelihood.model"
  - "algebraic.mle"
```

Use `series` field to add posts to a series:
```yaml
# In post front matter
series:
  - "stepanov"
  - "the-long-echo"
```

## Analytics & Insights

The analytics commands help understand content-project relationships:

- **`mf analytics summary`** - Get a complete overview of your site's content relationships
- **`mf analytics gaps`** - Find projects that need more content coverage
- **`mf analytics suggestions`** - Discover content that mentions projects but doesn't link to them

Use analytics when you want to:
- Identify projects that lack documentation/posts
- Find opportunities to link existing content to projects
- Understand tag usage patterns and content velocity

## Database Integrity

The integrity commands ensure database consistency:

- **`mf integrity check`** - Validates all databases for consistency issues
- **`mf integrity fix`** - Auto-fixes safe issues (stale cache, orphaned sync state)
- **`mf integrity orphans`** - Finds database entries without content files

Run `mf integrity check` periodically (e.g., weekly) to catch issues early. Common issues:
- Cache entries for deleted projects
- Sync state referencing removed posts
- Missing content files for database entries

## Extended Content Audit

The extended audit system provides pluggable content quality checks:

```bash
mf content audit --list-checks    # Show all available checks
mf content audit --extended       # Run all extended checks
mf content audit --check required_fields --severity error
```

Available checks include:
- `required_fields` - Validates required front matter
- `date_format` - Checks date field formats
- `stale_drafts` - Finds drafts older than threshold
- And more (use `--list-checks` to see all)

## Tips

1. **Always use `--dry-run` first** to preview changes
2. **Run `mf backup status`** to check backup health
3. **Run `mf integrity check` periodically** to catch database issues
4. **Use `mf analytics gaps`** to find content opportunities
5. **Use slugs not paths** in taxonomy fields
6. **Validate before committing**: `hugo --gc --minify`

## Additional Resources

- For complete command reference, see [COMMANDS.md](COMMANDS.md)
- For step-by-step workflows, see [WORKFLOWS.md](WORKFLOWS.md)
