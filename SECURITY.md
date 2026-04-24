# Security Policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting:

**<https://github.com/nextaim-de/noirdoc-claude-plugin/security/advisories/new>**

Please do not open a public issue for security bugs. We will acknowledge reports as soon as we can and coordinate a fix and disclosure with you.

Useful things to include:
- A description of the issue and the impact you see.
- A minimal reproducer — the `.noirdoc/config.toml` and the tool call that triggered the behaviour.
- Plugin version (from `plugin.json`) and Claude Code version.
- `noirdoc --version` and Python version.

## Scope

This plugin is pre-1.0 and changes quickly. Security issues are taken seriously, but formal response-time SLAs and long-term support branches start at 1.0.

**In scope — bugs in the plugin itself:**
- Guardrail bypass: a tool call on a protected path that the `PreToolUse` hook should have blocked but didn't.
- Config parsing bugs that cause the hook to fail open when it should fail closed (and vice versa).
- Path-extraction bugs (e.g., tricky `Bash` command shapes that route protected content into Claude's context).
- Hook output handling that leaks raw config paths or workspace contents into an error message.

**Out of scope — upstream or architectural:**
- Detection quality — false negatives in `noirdoc redact`. These are quality issues upstream in [noirdoc-core](https://github.com/nextaim-de/noirdoc/blob/main/SECURITY.md); open an issue there with a test case.
- The documented architectural limits in [README.md — Threat model](README.md#threat-model--what-this-plugin-does-and-does-not-protect), including:
  - Content already in the transcript from earlier turns (API replay).
  - User prompts (`UserPromptSubmit` scanning is deferred — see README).
  - MCP server tool outputs, subagent results, and `http(s)://` `WebFetch` responses.
  - `Grep`/`Glob` with no explicit `path` argument.
- Social-engineering attacks on the first-run setup flow (e.g., a user who accepts an allowlist suggestion they shouldn't have).

## Supported versions

Until `1.0`, only the latest `main` and the latest tagged release receive security fixes.
