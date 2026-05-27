# noirdoc-claude-plugin

[![CI](https://github.com/nextaim-de/noirdoc-claude-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/nextaim-de/noirdoc-claude-plugin/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12 | 3.13](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)

**Privacy-preserving document workflow for Claude Code.** Redact PII on the way in, stage placeholder answers on the way out. Real names never enter Claude's context — the user reveals them in their own terminal, outside Claude Code. German-first, local by default.

Powered by [noirdoc](https://github.com/nextaim-de/noirdoc).

> **Status:** alpha (`0.1.x`). Behaviour and config may change before `1.0`.

## What it does

You ask Claude to summarize a German employment contract. Normally:

1. You: "Summarize `./incoming/vertrag-mueller.pdf`."
2. Claude reads the raw PDF — names, addresses, IBANs, Steuer-IDs all enter its context.
3. Claude's summary includes those real details. So does the transcript, and anything downstream.

With this plugin installed:

1. You: "Summarize `./incoming/vertrag-mueller.pdf`."
2. PreToolUse hook blocks the raw read.
3. The `noirdoc` skill takes over: runs `noirdoc redact` against the file, reads the clean copy (`<<PERSON_3>>`, `<<IBAN_CODE_1>>`…), writes the summary against those placeholders.
4. Claude shows you the placeholder summary inline and stages it at `.noirdoc/staged/<ts>.txt`. To see real names, you run `noirdoc reveal --namespace <ns> < .noirdoc/staged/<ts>.txt` in your own terminal — outside Claude Code. Real names appear in *your* terminal, never in Claude's transcript.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.12 or 3.13
- [`noirdoc`](https://pypi.org/project/noirdoc/) CLI — the plugin will offer to install it on first use. `noirdoc[full]` is recommended for German documents (~560 MB of ML weights).

## Install

Inside Claude Code:

```
/plugin marketplace add nextaim-de/noirdoc-claude-plugin
/plugin install noirdoc@nextaim
```

Restart Claude Code. The `noirdoc` skill and `/noirdoc-*` commands should appear.

To update later: `/plugin update noirdoc`.

### Local install (for development)

```bash
git clone https://github.com/nextaim-de/noirdoc-claude-plugin
# Then, inside Claude Code:
# /plugin install /path/to/noirdoc-claude-plugin
```

## First use

In a workspace with sensitive documents:

```
/noirdoc-setup
```

This walks you through: installing `noirdoc[full]` (with consent), picking a namespace, confirming default protected paths, and writing `.noirdoc/config.toml`.

From that point on, Claude will auto-route reads of protected paths through the round-trip workflow.

## Commands

Reveal is intentionally **not** a slash command. It runs in your own terminal, outside Claude Code, against placeholder files the assistant stages under `.noirdoc/staged/`. The skill's round-trip prints the exact `noirdoc reveal …` invocation for you to copy.

| Command | Purpose |
|---|---|
| `/noirdoc-setup` | First-run setup: install check, namespace, protected paths, config file. Idempotent. |
| `/noirdoc-redact <path>` | Redact a file into `.noirdoc/cache/`. |
| `/noirdoc-status` | Show CLI version, namespace, protected paths, cache size. |
| `/noirdoc-allow <path>` | Add a path to the guard's allowlist. Requires confirmation. |

## Configuration

`.noirdoc/config.toml` in your workspace:

```toml
[noirdoc]
namespace = "mandant-foo"

[noirdoc.guard]
enabled = true
protected_paths = [
  "./incoming/**",
  "./clients/**",
  "./contracts/**",
  "*.contract.*",
  "*.nda.*",
]
allowlist = []

[noirdoc.cache]
dir = ".noirdoc/cache"
```

- **`namespace`** — the noirdoc namespace for this workspace. One per workspace is the sensible default (keeps placeholders consistent across files).
- **`guard.enabled`** — set `false` to disable protection without uninstalling.
- **`guard.protected_paths`** — glob patterns (relative to this config's directory). Supports `prefix/**` for directory-wide protection and fnmatch globs against full paths and basenames.
- **`guard.allowlist`** — exceptions to `protected_paths`. Extend via `/noirdoc-allow`.
- **`cache.dir`** — where redacted copies live. Should be gitignored.

## Threat model — what this plugin does and does not protect

Be clear-eyed about what a Claude Code plugin can and cannot do. Sensitive content can enter Claude's context (and be sent to the Anthropic API) through several paths; the plugin closes some of them, not all.

### What the guard hook blocks

| Entry path | Covered? | Notes |
|---|---|---|
| `Read` / `Edit` / `Write` of a protected path | ✅ | Hook blocks; skill runs redact first, reads the clean copy. |
| `Grep` / `Glob` with `path` in a protected directory | ✅ | Same block mechanism. |
| `NotebookRead` / `NotebookEdit` of a notebook in a protected path | ✅ | `notebook_path` is checked. |
| `WebFetch` on `file://` URLs pointing at protected paths | ✅ | Local `file://` URLs are extracted and checked. |
| `Bash` referencing a clearly-path-shaped token (`cat ./incoming/x.pdf`) | ⚠️ Best-effort | Simple cases only. Pipes, process substitution, `$(...)`, globbing by the shell — **not parsed**. Use `/noirdoc-redact` first for complex flows. |
| Any tool touching `~/.noirdoc/` (the reversible mapping vault) | ✅ Unconditional | Resolved via `realpath` so `~`, absolute paths, symlinks, and `..` traversal all normalize. Independent of workspace config. Not allowlistable. |
| `Bash` invoking `noirdoc ns show <ns>` or `noirdoc lookup <pseudonym>` | ✅ Unconditional | Both subcommands print real-name data to stdout, which would otherwise land in tool-result context. Regex-matched; bypassed by aliases (see gaps). |
| `Bash` invoking the noirdoc Python SDK (`from noirdoc...`, `import noirdoc`) | ✅ Unconditional | The SDK reads the same reverse mapping that `ns show` exposes. Regex-matched against the literal `from`/`import` keywords; bypassable by encoded payloads or `__import__("noirdoc")`. |
| `Bash` invoking `noirdoc reveal` | ✅ Unconditional | Reveal writes real names to stdout. No carve-out for `>`-redirection — the policy is "no in-session reveal." Reveal is a human action, run by the user in a regular terminal against a staged placeholder file. Help/version forms (`-h`, `--help`, `--version`) remain queryable. |
| `Read` / `Edit` / `Grep` against `.noirdoc/staged/**` | ✅ Unconditional | The staged directory is one-way: the assistant writes here (placeholder-only answers), the user reveals from here outside the session. Reading it back would re-pull placeholder text into a fresh tool result. `Write` remains allowed so the round-trip can stage. |

### What the guard hook does NOT block

| Entry path | Why it's out of reach | Mitigation |
|---|---|---|
| User pastes raw PII into the chat | `PreToolUse` cannot see user prompts. See the "user-prompt scanning" section below for why this is deferred. | Redact the source file with `/noirdoc-redact` and paste from the clean copy. |
| `Grep` / `Glob` with no explicit `path` (defaults to workspace root) | Can surface snippets from protected files in tool output. | Add narrow `path=` arguments to searches on sensitive workspaces, or disable the tool for sensitive sessions. |
| MCP server tool outputs | MCP servers run in their own processes and return arbitrary text. | Only use MCP servers you trust on sensitive workspaces. |
| Subagent (`Agent` tool) results | Sub-agents can read content whose bytes then come back as a tool result to the parent. Plugin hooks should apply inside sub-agents, but assume nothing until verified. | Don't dispatch sub-agents onto protected paths without checking the subagent's config. |
| Content that's already in the session transcript | Every turn is replayed to the API on every subsequent request. There is no Claude Code hook to rewrite outbound API payloads. | Start a fresh session for a new sensitive context. `/compact` summarizes but does not redact. |
| WebFetch on `http(s)://` URLs that return PII | The plugin has no visibility into remote response bodies. | Treat remote fetches as just another source of user-provided text. |

### The fundamental limit

**Once content is in any turn of the conversation, it will be sent to the Anthropic API for every subsequent request in that session.** Claude Code provides no hook for rewriting outbound API payloads. A plugin can only prevent content from *entering* context in the first place; it cannot retroactively remove it.

If you need guaranteed in-flight scrubbing — where you can prove nothing sensitive left the machine regardless of what got into the transcript — that is not a plugin-layer problem. It requires a network proxy that intercepts and rewrites outbound API requests. **[Noirdoc Cloud](https://noirdoc.de)** is the proxy; this plugin is the local "catch what you can" layer. They complement each other.

### User-prompt scanning (deferred)

A `UserPromptSubmit` hook could scan the user's prompt for PII patterns before Claude sees it. This is not in v0.1. Two things make it harder than it looks:

- **Claude Code's UserPromptSubmit hook can block or append additional context, but cannot rewrite the prompt text.** So "run the prompt through noirdoc and replace the IBAN with a placeholder" is not possible at this hook point — the only clean action on a match is to refuse the prompt and ask the user to resubmit.
- **Quality pattern coverage requires either structural validators (IBAN MOD-97, Luhn for cards — narrow) or full NER (names, addresses — accurate but adds per-prompt latency from spaCy/Flair cold starts).** Shipping only the narrow validators would give a false sense of coverage; shipping NER turns every user turn into a ~100 ms+ round-trip through the noirdoc pipeline. Neither tradeoff was clearly right for v0.1.

The plan's current answer: the skill nudges the user to paste from redacted copies rather than from raw files, and for guaranteed in-flight scrubbing independent of what ends up in the transcript, point them at Noirdoc Cloud.

### Other caveats

- **PDF reveal is not supported** by noirdoc. You get a textual answer with real names restored, not a revealed PDF. See the [noirdoc README](https://github.com/nextaim-de/noirdoc#supported-formats) for the full round-trip support matrix.
- **PPTX and images** redact but don't round-trip on reveal.
- **Detection quality depends on noirdoc's upstream models.** For high-stakes documents, spot-check the redacted copy before trusting the output.
- **The namespace mapping is reversible.** `~/.noirdoc/namespaces/<namespace>/` holds the real→placeholder map. Treat it with the same care as a secrets directory. The guard hard-blocks, unconditionally and non-allowlistably: (a) any tool call touching a path inside `~/.noirdoc/`, (b) any Bash invocation of `noirdoc ns show`, `noirdoc lookup`, or `noirdoc reveal` (all three print real-name data to stdout), (c) any Bash invocation that imports the noirdoc Python SDK with literal `from noirdoc...` / `import noirdoc...` keywords (the SDK reads the same mapping data), and (d) any read-shaped tool call (`Read`/`Edit`/`Grep`/`Glob`/`NotebookRead`/`NotebookEdit`/`Bash`/`file://` `WebFetch`) against `.noirdoc/staged/**` (the assistant writes its placeholder-only answers there; reading them back would re-pull text into a fresh tool result). This closes the obvious exfil paths — filesystem reads of the vault, mapping-dump CLI subcommands, SDK one-liners, in-session reveal, and round-tripped staged content. The supported reveal path is for the user to run `noirdoc reveal --namespace <ns> < .noirdoc/staged/<ts>.txt` in a regular terminal **outside Claude Code** — real names appear there, the assistant's transcript never sees them.
- **Residual exfil gaps** (documented, not closed): a Python one-liner that *encodes* its noirdoc SDK access (base64-decoded `exec`, `__import__("noirdoc")`, dynamic attribute access) to evade the literal `from`/`import` regex; an aliased or env-indirected CLI invocation that evades the Bash regex (including aliased `noirdoc reveal`); a base64-encoded subshell that reads `.noirdoc/staged/` without naming the path literally. These are out of reach for a deterministic PreToolUse hook and belong to the defence-in-depth layer above the plugin (e.g., Noirdoc Cloud's outbound proxy).

## How it works

Three components, skill-first:

- **`noirdoc/skills/noirdoc/SKILL.md`** — the workflow brain. Claude reasons about when to redact, sequences the redact/read/reveal round-trip, walks the user through first-run setup.
- **`noirdoc/hooks/guard.py`** — tiny stdlib-only `PreToolUse` hook. Reads config, matches globs, blocks raw reads of protected paths. No noirdoc import, no content inspection, no tool-input mutation — just a deterministic gate.
- **`noirdoc/commands/noirdoc-*.md`** — thin slash commands that invoke the same primitives the skill uses.

The guard fails open: workspaces without `.noirdoc/config.toml` experience no blocks. Only the files you configure as protected are protected.

## Development

This repo uses the shared noirdoc tooling standard (`uv` + ruff/mypy). Common tasks go through `make`:

```bash
make install   # set up the dev environment
make check     # lint + format-check + typecheck + test — run before pushing
make test      # run the test suite (guard hook unit tests)
```

Run `make help` for the full list of targets (also: `make lint`, `make fmt`, `make typecheck`).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor flow.

## Project

- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, PR rules
- [SECURITY.md](SECURITY.md) — vulnerability reporting and scope
- [CHANGELOG.md](CHANGELOG.md) — release notes
- [docs/RELEASING.md](docs/RELEASING.md) — how maintainers cut a release

## License

MIT. See [LICENSE](LICENSE).

Built by [Nextaim](https://nextaim.de) · [noirdoc.de](https://noirdoc.de)
