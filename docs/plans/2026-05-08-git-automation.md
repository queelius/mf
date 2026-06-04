# Git Automation for mf

## Status: Draft

## Goal

Make `mf` commands that change content automatically commit those changes via git. The user gets a consistent rollback substrate without having to remember to commit after every action.

This is a single-author convenience layer, not a general team-collaboration system.

## Problem

1. The user does not consistently use git after `mf` actions, so finding the right state to revert to after a regrettable action requires ad-hoc grepping.
2. `mf series sync --push` and similar commands change content in two repos (metafunctor and a source repo) as one logical action, but git has no built-in way to pair commits across repos.
3. The existing `.mf/backups/<domain>/*.{pdf,html}` content backups duplicate git for files git already tracks. They were a poor man's git when consistent committing wasn't realistic.
4. The action log gap: even when the user does commit, there's no record of which `mf` command produced which commit, so "what did mf change recently?" is unanswerable without `git log` archaeology.

## Non-goals

- Replacing user-authored commits. `mf` only commits the changes `mf` produced.
- Coordinating with non-git VCS (no abstraction over hg/svn).
- Auto-pushing to remote. Commits stay local until the user pushes.
- Snapshot-based time-travel. `mf` relies on git history, not parallel snapshot trees.
- Rewriting history (no rebase, no amend, no force-push).

## Threat model

This system protects against:
- "I ran `mf series sync stepanov --push` and now I want to undo it."
- "I ran `mf papers ingest foo` and the artifact is wrong; what files did it touch?"
- "I want to know what `mf` has done in the last week."

It does not protect against:
- Disk failure. Use offsite git push for that.
- Database corruption. `safe_write_json` atomic writes already cover this.
- Cross-process races. `mf` is invoked sequentially by one user.

## Architecture

### Per-action commit lifecycle

Every content-touching `mf` command follows the same flow:

1. **Precondition check.** Inspect the working trees `mf` is about to touch (one or two depending on the command). For each:
   - If clean: proceed.
   - If dirty:
     - Default behavior: abort with a message naming the dirty paths and suggesting `git add -A && git commit` or `--commit-existing`.
     - With `--commit-existing`: stage and commit pre-existing changes with a `chore: pre-mf <command> snapshot` message. Then proceed.
     - With `--force`: skip the check entirely (escape hatch for unusual workflows).
2. **Mf action runs.** Produces content changes as it does today, in `--dry-run` it stops here without committing.
3. **Post-action commit.** Stage only the paths `mf` actually touched (tracked by the action) and commit with a structured message:

   ```
   mf <command>: <slug> <one-line summary>

   Run-ID: <uuid4>
   Action: <command> <args>
   Files: <count> changed
   ```

   The Run-ID trailer is stable across paired commits (see below).

4. **Cross-repo coordination.** Commands that touch two repos commit to both with the same Run-ID:
   - `series sync` (pull) commits in the metafunctor repo only.
   - `series sync --push` commits in the source repo only.
   - Future: a hypothetical bidirectional command would commit in both with one shared Run-ID, so `git log --grep=Run-ID:<id>` in either repo finds the paired commit reference.

5. **Action log append.** Each commit also appends one JSONL line to `.mf/action-log.jsonl` recording `{run_id, timestamp, command, args, repos: [{path, sha, files}]}`. This is the queryable audit trail; commits hold the actual diff.

### What lives where

| Layer | Holds | Source of truth for |
|-------|-------|---------------------|
| Git history (metafunctor and source repos) | full diff of every action | what changed |
| `.mf/action-log.jsonl` | structured record of every action | when, by which command, with what args |
| Commit message Run-ID trailer | uuid linking paired commits | finding the other half of a cross-repo action |

### Configuration

`.mf/config.yaml` gains a `git` section:

```yaml
git:
  auto_commit: true              # default true; false disables the whole layer
  require_clean_tree: true       # abort on dirty tree unless overridden
  message_prefix: "mf:"          # prepended to all messages
  signed_commits: false          # respect user's git signing config; do not enforce
  user_name: null                # null inherits from git config; override per-repo
  user_email: null
```

### CLI surface

Every content-touching command picks up:

- `--no-commit` (alias `-N`): skip the post-action commit. Changes are left in the working tree for the user to commit manually. Useful when batching multiple `mf` actions into one human commit.
- `--commit-existing`: stage and commit pre-existing dirt as the user's own work before running.
- `--force`: bypass the clean-tree precondition.

Plus three new top-level commands:

- `mf log [--since DATE] [--command CMD] [--slug SLUG] [--limit N]`: query `.mf/action-log.jsonl`. Shows run id, timestamp, command, summary.
- `mf show <run-id>`: show the action log entry plus the commit metadata for that run, including paired commits.
- `mf revert <run-id>`: print the `git revert` command(s) the user should run. Does not execute. The user retains the choice and review opportunity.

### Per-module behavior

| Command | Repos touched | Commits | Message stub |
|---------|--------------|---------|--------------|
| `series sync` (pull) | metafunctor | 1 | `mf series sync <slug>: pull, +N updated` |
| `series sync --push` | source repo | 1 | `mf series sync <slug>: push, +N updated` |
| `papers ingest <slug>` | metafunctor (`static/latex/`) | 1 | `mf papers ingest <slug>: artifacts refreshed` |
| `pubs pull <slug>` | metafunctor (`static/`) | 1 | `mf pubs pull <slug>: artifacts pulled` |
| `projects refresh` | metafunctor | 1 | `mf projects refresh: N projects updated` |
| `<module> generate` | metafunctor | 1 | `mf <module> generate: N pages` |
| `<module> set/unset/feature/tag` | none (DB only at write time) | deferred | see below |

DB-only commands (`set`, `unset`, `feature`, `tag`) update `.mf/<domain>_db.json` but produce no content changes. They could each commit immediately, but that produces noisy history. Two options to evaluate during pilot:

- **A) Auto-commit the DB JSON immediately.** Simple, every action gets its own commit. History gets noisy.
- **B) Coalesce.** A separate `mf db commit` command (or auto-flush at session end via a hook) commits all pending DB JSON changes together. Cleaner history, requires plumbing.

The pilot will start with (A) and switch to (B) if history noise becomes a real problem.

### Action log shape

`.mf/action-log.jsonl`, one JSON object per line:

```json
{
  "run_id": "01HZ8X4G7K2Y9Q1V3R5W6T8N0F",
  "timestamp": "2026-05-08T14:23:11Z",
  "command": "series sync",
  "args": {"slug": "stepanov", "push": false, "delete": false},
  "repos": [
    {
      "path": "/home/spinoza/github/repos/metafunctor",
      "sha_before": "a1b2c3d",
      "sha_after": "e4f5g6h",
      "files": ["content/post/stepanov-intro/index.md"]
    }
  ],
  "summary": "pull, 1 updated"
}
```

Open question: should this be committed or gitignored? Arguments either way are listed under Open Questions below.

## Migration plan for existing backups

Once auto-commit is in place and verified across at least one release cycle:

1. **Content backups** (`.mf/backups/papers/*.pdf`, `.mf/backups/papers/*.html`, similar for projects): redundant with git. Add `mf backup audit-redundant` that lists what's covered by git history. Add `mf backup migrate-to-git` that retires content backup directories after confirming git coverage.
2. **Database JSON backups** (`.mf/backups/<domain>/*.json`): stay for one release as belt-and-suspenders. Re-evaluate based on real recovery incidents (which should drop to near zero once auto-commit is reliable).
3. **The papers backup system** the user mentioned existing: audit it as the first step (per earlier conversation), then fold into this plan.

## Open questions

1. **`.mf/action-log.jsonl` committed or gitignored?**
   - **Committed:** part of the canonical record, survives across machines, visible in `git log -p .mf/action-log.jsonl`.
   - **Gitignored:** keeps the action log purely local, avoids merge conflicts on `action-log.jsonl` if `mf` is ever run from two machines, but the log doesn't survive a fresh checkout.
   - Default proposal: committed. The conflict risk is low for a single-author site, and the audit-trail value is high.

2. **Sub-module repos.** Some content lives in nested git repos (e.g., `papers/masked-series-companions/`). The clean-tree check needs to walk up to find the *right* repo for the touched paths. Use `git rev-parse --show-toplevel` per file rather than assuming the immediate parent.

3. **What if the user has signing required** but no key in CI/scripted contexts? Respect the user's git config; never override `commit.gpgSign`. If signing fails, surface the error and let the user fix it.

4. **`--no-commit` discoverability.** Should the command print a hint at the end like `# changes left uncommitted; run \`git add -A && git commit\` to save\`? Yes, low-cost, discoverable.

5. **DB-only commands in the action log.** Even if they don't commit, should they still append to the action log? Probably yes, so the log is the complete record of every `mf` action regardless of whether it produced a commit.

6. **Failure mid-action.** If the post-action commit fails (e.g., pre-commit hook rejects), what happens to the in-tree changes? Default: leave them in the working tree, surface the hook error, exit non-zero. The user can resolve and commit manually, or revert.

## Phasing

1. **Phase 1: pilot in `mf series`.** Add the precondition check, post-action commit, `--no-commit` / `--commit-existing` / `--force` flags, action-log writer. Pure addition; gated on the new config key, off by default for one release. Test against the dirty-tree edge cases.

2. **Phase 2: expand to `papers`, `pubs`, `projects`.** Lift the helpers into `mf.core.git`. Update each module's `commands.py` to wrap content-touching commands.

3. **Phase 3: action-log query commands** (`mf log`, `mf show`, `mf revert`). Pure read commands, slot into the read-only audit pattern.

4. **Phase 4: backup retirement.** `mf backup audit-redundant` and `mf backup migrate-to-git`, then deprecate content backup directories. Database JSON backups stay; revisit at end of phase 4.

5. **Phase 5: revisit DB-only commit policy.** If the noisy-history concern materializes, build the coalescing layer.

Each phase is independently shippable and falsifiable: phase 1 either makes single-repo sync feel safe enough that the user actually commits, or it doesn't, and we adjust before phase 2.

## Test plan

For each phase 1 surface:

- Clean tree, action runs, commit lands with the right message and Run-ID trailer.
- Dirty tree (default): action aborts; nothing is committed; action log is not appended to.
- Dirty tree with `--commit-existing`: pre-existing dirt is committed first under the user's identity, then the action runs and commits separately.
- Dirty tree with `--force`: action runs without a clean-tree check; resulting commit may include unrelated dirt (documented behavior).
- `--no-commit`: action runs; working tree shows changes; no commit; action log still gets an entry with `sha_after: null`.
- Cross-repo (when `series sync --push` is wired): both commits share the same Run-ID; `git log --grep=Run-ID:<id>` in either repo finds the trailer.
- Sub-module: action paths in a nested repo commit in the nested repo, not the parent.
- Hook failure: `pre-commit` rejects the commit; action log entry is still written with `sha_after: null` and `error: <message>`.

## Risks

1. **User's existing git workflow.** Some users curate commits manually and would find auto-commit invasive. Mitigation: `auto_commit: false` in config, `--no-commit` per-command, default is opt-in for the first release.
2. **History noisiness.** One commit per `mf` action may overwhelm `git log`. Mitigation: paired commits via Run-ID let `git log --grep` filter; coalescing for DB-only actions if it becomes a real problem.
3. **Cross-repo desync.** Sync operation succeeds in one repo, fails in the other. Mitigation: run the action in both repos before committing in either; if either fails, abort cleanly without committing anywhere. Idempotency of `mf` actions makes retry safe.
4. **Pre-commit hooks the user has.** The soul-voice em-dash hook in this very repo would reject any `mf`-generated commit message containing em-dashes. The auto-commit message format is em-dash-free by construction; verify in tests.
