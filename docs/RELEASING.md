# Releasing noirdoc-claude-plugin

How to cut a release. The plugin is distributed via a git-hosted Claude Code
marketplace, not via PyPI — there is no artifact to build or upload. Tags are
the release mechanism; `/plugin install noirdoc@noirdoc` resolves to the tag
users install.

## Summary

- Tag `v0.1.0` → creates a GitHub Release with the matching `CHANGELOG.md` section.
- Tag `v0.1.0rc1` / `v0.1.0a1` / `v0.1.0.dev1` → same, marked as a pre-release.
- Version in `.claude-plugin/plugin.json` must match the tag. The release workflow verifies this and fails if they drift.

## Per-release checklist

1. **Update the changelog.** Move items under `## [Unreleased]` into a new
   `## [X.Y.Z] — YYYY-MM-DD` section. Keep an empty `## [Unreleased]` skeleton on top.
2. **Bump `version` in `.claude-plugin/plugin.json`** to match the tag you're about to push.
3. **Commit.** `git commit -am "chore(release): X.Y.Z"`
4. **Tag.** `git tag -a vX.Y.Z -m "vX.Y.Z"`
5. **Push.** `git push origin main --follow-tags`
6. **Watch the run.** GitHub → Actions → *Release*. The workflow will:
   - Verify `plugin.json` version matches the tag.
   - Extract the `## [X.Y.Z]` section from `CHANGELOG.md`.
   - Create a GitHub Release with that body.
7. **Smoke test.** In a fresh Claude Code workspace:
   ```
   /plugin marketplace add nextaim-de/noirdoc-claude-plugin
   /plugin install noirdoc@nextaim
   ```
   Restart Claude Code. Confirm `/noirdoc-status` responds and the skill surfaces on a prompt that mentions a sensitive path.

## Tag shape

Valid tags match `v<semver>` where `<semver>` is a [PEP 440](https://peps.python.org/pep-0440/)-style version string:

- `v0.1.0` — final release
- `v0.1.0rc1`, `v0.1.0a1`, `v0.1.0b2` — pre-release (marked as prerelease in the GitHub Release)
- `v0.1.0.dev1` — dev snapshot
- `v0.1.0.post1` — post-release fix

Invalid: `0.1.0` (missing `v`), `v0.1.0-beta` (hyphenated pre-release segments).

## Troubleshooting

**"Plugin version does not match tag" step fails.**
`.claude-plugin/plugin.json` has a different `version` than the tag. Bump the
manifest to match, retag (or push a new patch tag).

**GitHub Release notes are empty.**
The changelog section `## [<version>]` wasn't present or didn't match exactly
when the tag ran. Update `CHANGELOG.md`, retag. The workflow falls back to a
generic message if the section is missing; you can also edit the release body
after the fact.

**Users on a stale version.**
`/plugin update` in Claude Code refreshes installed plugins to the latest
marketplace version. Tell users to run it after a release.
