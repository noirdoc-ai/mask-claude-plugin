---
description: Add a path or glob to the noirdoc guard allowlist, disabling protection for it
argument-hint: <path-or-glob>
---

Append `$ARGUMENTS` to the `noirdoc.guard.allowlist` in `.noirdoc/config.toml`.

This **disables the guardrail** for that path. Before making the edit, confirm with the user in plain language:

> "Adding `$ARGUMENTS` to the allowlist means the guard hook will let Claude read that path without redaction. Only do this for files you're sure contain no personal data. Proceed?"

If the user confirms:

1. Read `.noirdoc/config.toml`.
2. Parse the `noirdoc.guard.allowlist` array.
3. Append `$ARGUMENTS` if not already present (idempotent).
4. Write the file back, preserving the rest of the config.
5. Confirm the change with the new allowlist contents.

If the user does not confirm, or the config file doesn't exist, stop without modifying anything.
