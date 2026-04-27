---
description: Add a path or glob to the noirdoc guard allowlist, disabling protection for it
argument-hint: <path-or-glob>
---

Adding `$ARGUMENTS` to the `noirdoc.guard.allowlist` in `.noirdoc/config.toml` **disables the guardrail** for that path.

The guard hook denies any in-session edit of `.noirdoc/config.toml` (Edit/Write/Bash) — otherwise a prompt-injected turn could disable the guard on its own. Allowlisting therefore happens out of band.

Steps:

1. Confirm with the user in plain language:

   > "Adding `$ARGUMENTS` to the allowlist means the guard hook will let Claude read that path without redaction. Only do this for files you're sure contain no personal data. Proceed?"

2. If the user confirms, use the `Read` tool on `.noirdoc/config.toml` to show them the current `allowlist`. Then tell them to edit the file themselves — in a regular terminal, in their editor, or with the snippet below — and append `$ARGUMENTS` to the array:

   ```toml
   [noirdoc.guard]
   allowlist = [
     # …existing entries…
     "$ARGUMENTS",
   ]
   ```

   Example one-liner they can paste into a terminal (skips if already present):

   ```bash
   python3 -c '
   import tomllib, pathlib
   p = pathlib.Path(".noirdoc/config.toml")
   c = tomllib.loads(p.read_text())
   a = c.setdefault("noirdoc", {}).setdefault("guard", {}).setdefault("allowlist", [])
   if "$ARGUMENTS" not in a:
       a.append("$ARGUMENTS")
       # round-trip via a minimal TOML rewrite — adjust by hand if you keep comments
       lines = p.read_text().splitlines()
       # ...edit by hand if the file has comments you want to keep
   '
   ```

   In practice the cleanest path is: open `.noirdoc/config.toml` in your editor and add the line by hand.

3. After they confirm they've made the change, run `/noirdoc-status` to verify the new allowlist is in effect.

If the user does not confirm, or `.noirdoc/config.toml` doesn't exist (run `/noirdoc-setup` first), stop without taking any action.
