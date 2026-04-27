# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-27

First public release.

### Added
- `PreToolUse` guard hook (`noirdoc/hooks/guard.py`) that blocks reads of workspace-configured
  protected paths across `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob`, `NotebookRead`,
  `NotebookEdit`, and `file://` `WebFetch`. Stdlib-only, fails open when no
  `.noirdoc/config.toml` is present.
- Guard hook unconditionally blocks all tool access to `~/.noirdoc/` (the vault
  holding the reversible real-name ↔ placeholder mappings), resolved via
  `realpath` so `~` expansion, absolute paths, symlinks, and `..` traversal all
  normalize. Independent of workspace config; not allowlistable.
- Guard hook additionally blocks `Bash` invocations of `noirdoc ns show <ns>`
  and `noirdoc lookup <pseudonym>`. Both subcommands print real-name data to
  stdout, which would otherwise land in Claude's tool-result context and defeat
  redaction the same way as direct vault reads. `noirdoc ns list` and
  `noirdoc reveal` remain unblocked (names-only and intended-reveal-path).
- Guard hook blocks `Bash` invocations that import the noirdoc Python SDK with
  literal `from noirdoc…` or `import noirdoc…` keywords (e.g.
  `python -c 'from noirdoc.pseudonymization import PseudonymMapper'`). The SDK
  exposes the same reverse mapping that `ns show` does; closing the obvious
  one-liner case at the regex tier. Best-effort — bypassable by base64-encoded
  payloads, `__import__("noirdoc")`, or dynamic attribute access. The lookahead
  `(?![\w-])` ensures sibling packages like `noirdoc-cloud` and `noirdoctest`
  aren't false-positive matched.
- Guard hook uses `shlex.split` (POSIX mode) to tokenize Bash commands, so
  quoted paths with spaces (`cat "./incoming/x with spaces.pdf"`) are extracted
  as a single token and matched against protected globs. Falls back to
  `str.split()` on malformed quoting to preserve fail-open behavior.
- `noirdoc` skill (`noirdoc/skills/noirdoc/SKILL.md`) that sequences the redact → read-clean →
  reveal round-trip, handles first-run setup (namespace consent, `noirdoc[full]` install
  prompt, protected-paths confirmation), and recovers from hook blocks without looping.
- Slash commands: `/noirdoc-setup`, `/noirdoc-redact`, `/noirdoc-reveal`,
  `/noirdoc-status`, `/noirdoc-allow`. `/noirdoc-status` reports per-entity-type
  counts via `noirdoc ns summary <ns>` (counts only — no real-name data leaves
  the CLI), falling back to `ns list` when the namespace doesn't exist yet.
- Workspace config schema at `.noirdoc/config.toml` — `guard.enabled`,
  `guard.protected_paths`, `guard.allowlist`, `cache.dir`, per-workspace `namespace`.
- Self-hosted marketplace manifest (`.claude-plugin/marketplace.json`) with
  description, and plugin manifest (`noirdoc/.claude-plugin/plugin.json`), plus
  starter workspace config template (`noirdoc/templates/config.toml`).
- CI workflow (lint via pre-commit + pytest on Python 3.12 and 3.13).
- Developer tooling: `pyproject.toml` with ruff/mypy/pytest config,
  `.pre-commit-config.yaml` with ruff, gitleaks, and standard hygiene hooks.
- 81 unit tests covering glob matching, config parsing, tool-input extraction,
  allowlist precedence, vault hard-block, mapping-dump CLI block, SDK-import
  block, shlex tokenization, and end-to-end script integration via subprocess.
- Documented threat model in `README.md` — what the guard covers, what it doesn't, and
  the fundamental limit that plugin-layer hooks cannot retroactively scrub content
  already in the transcript.

[Unreleased]: https://github.com/nextaim-de/noirdoc-claude-plugin/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nextaim-de/noirdoc-claude-plugin/releases/tag/v0.1.0
