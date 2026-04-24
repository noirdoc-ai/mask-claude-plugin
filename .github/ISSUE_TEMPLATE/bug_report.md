---
name: Bug report
about: Something the plugin does wrong (wrong block, missed block, skill misbehaviour)
title: ""
labels: bug
assignees: ""
---

**For security-sensitive bugs** (guardrail bypass, config parsing flaws that let protected content through), do not open a public issue — use [private vulnerability reporting](https://github.com/nextaim-de/noirdoc-claude-plugin/security/advisories/new) instead. See [SECURITY.md](../../SECURITY.md).

## What happened

<!-- One-sentence summary of the misbehaviour. -->

## Reproduction

1. Workspace state (contents of `.noirdoc/config.toml`, redact any sensitive paths):
   ```toml
   ```
2. Tool call / prompt that triggered it:
3. Hook output (if any):

## Expected behaviour

<!-- What should have happened instead? -->

## Environment

- Plugin version: <!-- from `plugin.json` -->
- Claude Code version: <!-- claude --version -->
- `noirdoc --version`:
- Python version:
- OS:
