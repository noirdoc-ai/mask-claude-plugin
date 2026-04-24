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
4. Namespace summary for the configured namespace:
   ```bash
   noirdoc ns show <ns>
   ```
   Summarize the entity counts for the user; do NOT dump the raw mapping (it contains the original values).

If any step fails because the workspace isn't set up, say so plainly and suggest `/noirdoc-setup`.
