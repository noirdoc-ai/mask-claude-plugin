# Contributing to noirdoc-claude-plugin

Thanks for your interest. This plugin is early — behaviour and config shape may change before `1.0` — but contributions are welcome, especially around hook coverage, skill prompts, and first-run UX.

If your change is about PII detection itself (new recognizers, upstream model
behaviour, redact/reveal formats), it probably belongs in [noirdoc-core](https://github.com/nextaim-de/noirdoc) rather than here. This repo is the Claude Code integration layer; it shells out to the `noirdoc` CLI and does not reimplement detection.

## Prerequisites

- Python 3.12 or 3.13 (for running hook scripts and tests)
- [Claude Code](https://claude.com/claude-code) (to test the plugin end-to-end)
- The [`noirdoc`](https://pypi.org/project/noirdoc/) CLI — `pip install 'noirdoc[full]'` if you want to exercise the round-trip workflow

## Dev setup

```bash
git clone https://github.com/nextaim-de/noirdoc-claude-plugin
cd noirdoc-claude-plugin
pip install pytest ruff pre-commit
pre-commit install
```

The plugin itself has **no Python runtime dependencies** — the hooks use stdlib only (tomllib, fnmatch, pathlib). `pyproject.toml` exists purely to configure dev tooling (pytest, ruff, mypy); nothing ships on PyPI.

## Running tests

```bash
pytest                    # 48 tests, all fast (no ML models loaded)
```

Tests cover the `PreToolUse` guard hook. The skill, commands, and round-trip behaviour are exercised via manual end-to-end testing — see "Testing the plugin end-to-end" below.

## Lint and formatting

```bash
pre-commit run --all-files
```

Runs ruff (check + format), gitleaks, trailing-whitespace, yaml/json validators, and basic hygiene hooks. CI enforces the same config.

## Testing the plugin end-to-end

The unit tests cover the hook, not the skill. To test the full workflow:

```bash
# From a separate workspace with a sensitive document:
/plugin install /path/to/noirdoc-claude-plugin
/noirdoc-setup
# Ask Claude to summarize a file under ./incoming/; confirm the round-trip runs.
```

## Pull requests

- Keep PRs small and focused.
- Every PR that touches the hook or skill logic includes a test.
- Update `CHANGELOG.md` under `## [Unreleased]` with a one-line entry in the appropriate subsection (`### Added`, `### Changed`, `### Fixed`).
- If the change affects user-visible behaviour, update `README.md` and `noirdoc/skills/noirdoc/SKILL.md` accordingly.
- CI must be green before review.

## Releasing

Only maintainers cut releases. The flow is tag-driven — see [docs/RELEASING.md](docs/RELEASING.md) for the per-release checklist.

## Reporting bugs

Open an issue at <https://github.com/nextaim-de/noirdoc-claude-plugin/issues>. Include:
- Claude Code version
- `noirdoc --version`
- Python version and OS
- The `.noirdoc/config.toml` you were using (redact any sensitive paths)
- The tool call that misbehaved and what you expected instead

For security-sensitive bugs, see [SECURITY.md](SECURITY.md) — do not open a public issue.
