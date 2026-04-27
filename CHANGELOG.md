# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] — 2026-04-27

Privacy fix: closes the gap between the README's "real names never enter
Claude's context" invariant and the round-trip's final step, which was
piping placeholder text through `noirdoc reveal` via Bash and capturing
stdout — putting real names into the tool result and from there into every
subsequent API request. Reveal is now a human action that runs outside
Claude Code; the assistant stages a placeholder-only answer and the user
runs `noirdoc reveal` in their own terminal. The `/noirdoc-reveal` slash
command is removed (BREAKING), since a command named "reveal" that no
longer reveals is misleading.

### Security
- **Reveal no longer runs in-session.** `noirdoc reveal` writes real names to
  stdout, and Bash subprocess stdout becomes a tool result in the session's
  context — so every prior call to `noirdoc reveal` from inside the assistant
  put originals into the transcript and replayed them on every subsequent API
  request. The README and skill claimed "real names never enter Claude's
  context" while the round-trip's final step was breaking that claim. Reveal
  is now a human action: the skill stages its placeholder-only answer to
  `.noirdoc/staged/<ts>.txt` and prints the exact `noirdoc reveal --namespace
  <ns> < <path>` command for the user to run in their own terminal, outside
  Claude Code. The guard hard-blocks `noirdoc reveal` in Bash unconditionally
  — no carve-out for `>`-redirection, since stderr / regressions / aliased
  wrappers can each silently reopen the leak. Help/version forms (`-h`,
  `--help`, `--version`) remain queryable.
- **`.noirdoc/staged/` is one-way.** `Read` / `Edit` / `Grep` / `Glob` /
  `NotebookRead` / `NotebookEdit` / `file://` `WebFetch` against any path
  under `.noirdoc/staged/**` are blocked unconditionally. `Write` remains
  allowed so the staging step can create the file. The block fires
  independent of workspace config (no `.noirdoc/config.toml` required).

### Removed
- **BREAKING: `/noirdoc-reveal` slash command removed.** A slash command
  named "reveal" that doesn't reveal is misleading, and under the new
  policy reveal can't run in-session at all. The skill's round-trip step 4
  produces and prints the exact terminal command for the user to run.

### Changed
- Block-reason copy in `build_mapping_dump_block_payload` and
  `build_sdk_import_block_payload` updated to point at the new
  staged + out-of-session reveal path instead of the removed
  `/noirdoc-reveal` command.
- Skill `noirdoc/skills/noirdoc/SKILL.md` round-trip step 4 rewritten to
  describe staging; vault subsection rewritten to describe the new "no
  in-session reveal" policy; setup step 4 also gitignores `.noirdoc/staged/`.

### Tests
- 107 → 119 unit tests. New `TestRevealBlock` (6 cases: leaky form blocked,
  redirected form still blocked, help/version pass, config-independent,
  workspace-config-present, hyphenated-substring false-positive guard) and
  `TestStagedDirBlock` (7 cases: Read/Edit/Grep blocked, Write passes,
  config-independent, absolute path normalization, cache directory still
  passes). `test_reveal_passes` removed (asserted the old leaky behaviour).

## [0.2.0] — 2026-04-27

Security audit pass. Four bypasses of guarantees the README/SECURITY.md
advertised as solid in 0.1.0 are now closed. The workspace-config guard
became an unconditional, non-allowlistable rule, which changes how
`/noirdoc-allow` works — see "Changed" below.

### Security
- **H1.** `noirdoc ns show` / `noirdoc lookup` mapping-dump block previously
  failed for any flag-first invocation: `noirdoc ns show --json <ns>` and
  `noirdoc lookup --namespace <ns> '<<PERSON_1>>'` both sailed past the
  `(?=[^\s-])` lookahead. The argparse `--` end-of-options separator did
  too. Replaced with a negative lookahead that only carves out `-h`,
  `--help`, and `--version` literally — every other invocation form is
  blocked, including bare `noirdoc ns show` with no args.
- **H2.** `.noirdoc/config.toml` was editable from inside a session, so a
  prompt-injected Claude could flip `guard.enabled = false` or push `**`
  into `allowlist` to neutralize the workspace guardrail. The hook now
  unconditionally denies `Edit` / `Write` / `NotebookEdit` of the workspace
  config and any `Bash` command that references it literally. The block
  only fires once a config exists, so `/noirdoc-setup` can still create a
  fresh one. Reads via the `Read` tool remain allowed (the config has no
  PII).
- **H3 + L4.** `shlex.split` collapses `bash -c "..."`, `sh -c "..."`, and
  `eval "..."` bodies into one opaque token, so the token-based vault check
  missed `bash -c "cat ~/.noirdoc/..."`. Added a literal vault-pattern
  scan over the full command string covering `~/.noirdoc/`,
  `$HOME/.noirdoc/`, `${HOME}/.noirdoc/`, absolute home-dir paths under
  `/Users/...` and `/home/...`, and a substring check against the resolved
  realpath of the vault.
- **M3.** Fail-open on a malformed `.noirdoc/config.toml` flipped to
  fail-closed. A workspace owner who placed the file expects the guard
  active; silent bypass on a tampered or truncated config was the wrong
  default. The "no config at all" bootstrap case stays fail-open. Schema
  errors — non-table `[noirdoc.guard]`, non-list `protected_paths` or
  `allowlist` — now return a deny payload pointing at the file with a
  short repair-or-delete message.

### Changed
- `/noirdoc-allow` no longer edits `.noirdoc/config.toml` directly (H2
  blocks that). The command now shows the user the new `allowlist` line
  and asks them to add it themselves in a regular terminal or editor,
  outside Claude Code. `/noirdoc-status` afterwards confirms the new
  entry is in effect.
- Module docstring in `noirdoc/hooks/guard.py` updated to reflect the
  new fail-closed-on-malformed posture.

### Tests
- 88 → 107 unit tests. New `TestWorkspaceConfigBlock` class; expanded
  `TestMappingDumpBlock` and `TestVaultBlock` with regression coverage
  for H1, H2, H3, L4; `TestEvaluate` malformed-config cases rewritten
  to assert deny.

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
  `/noirdoc-status`, `/noirdoc-allow` (note: `/noirdoc-reveal` was removed
  in [Unreleased]; see that entry). `/noirdoc-status` reports per-entity-type
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

[Unreleased]: https://github.com/nextaim-de/noirdoc-claude-plugin/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/nextaim-de/noirdoc-claude-plugin/releases/tag/v0.2.1
[0.2.0]: https://github.com/nextaim-de/noirdoc-claude-plugin/releases/tag/v0.2.0
[0.1.0]: https://github.com/nextaim-de/noirdoc-claude-plugin/releases/tag/v0.1.0
