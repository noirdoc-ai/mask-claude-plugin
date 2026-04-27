---
description: Show current noirdoc workspace configuration, namespace, protected paths, cache size, and CLI version
---

Report the current noirdoc state for this workspace. Run these checks and present the results as a compact table or bullet list:

1. `noirdoc --version` — CLI present? Which version?
2. Read `.noirdoc/config.toml` — does it exist?
   - `noirdoc.namespace`
   - `noirdoc.guard.enabled`
   - `noirdoc.guard.protected_paths` (full list)
   - `noirdoc.guard.allowlist` (full list)
3. `.noirdoc/cache/` size: `du -sh .noirdoc/cache/ 2>/dev/null`
4. Namespace summary (counts only — no real-name data):
   ```bash
   noirdoc ns summary <ns>
   ```
   Prints per-entity-type counts as JSON (e.g., `{"PERSON": 12, "IBAN_CODE": 3, "LOCATION": 7}`). The mapping itself never leaves the CLI. Report the counts inline.

   On non-zero exit (namespace doesn't exist yet), fall back to:
   ```bash
   noirdoc ns list
   ```
   If `<ns>` is absent from the list, report "Namespace mapping: not yet created (no redactions run)". This is the expected initial state — `~/.noirdoc/namespaces/<ns>/` is created on the first `/noirdoc-redact` run.

   **Never run `noirdoc ns show`, `noirdoc lookup`, `cat ~/.noirdoc/...`, `python -c 'from noirdoc...'`, or any other command whose stdout would contain real-name data.** The guard hook blocks these anyway; the point is not to attempt them. If the user needs to inspect the raw mapping, tell them to run `noirdoc ns show <ns>` themselves in a regular terminal outside Claude Code.

If any step fails because the workspace isn't set up (missing `.noirdoc/config.toml`), say so plainly and suggest `/noirdoc-setup`.
