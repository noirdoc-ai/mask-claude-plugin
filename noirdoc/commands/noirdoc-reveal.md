---
description: Reveal noirdoc placeholders in a string back to real values using this workspace's namespace
argument-hint: [text — defaults to your previous assistant message]
---

Reveal placeholders (`<<PERSON_1>>`, `<<IBAN_CODE_1>>`, etc.) back to real values using the namespace from `.noirdoc/config.toml`.

Target text:

- If `$ARGUMENTS` is non-empty, reveal that string.
- Otherwise, reveal the text of your most recent assistant message (the one before this command).

Steps:

1. Verify `.noirdoc/config.toml` exists. If not, tell the user to run `/noirdoc-setup` first and stop.
2. Read the namespace from the config.
3. Pipe the target text through:
   ```bash
   echo "<target text>" | noirdoc reveal --namespace <ns>
   ```
   (`noirdoc reveal` reads stdin when no positional file argument is supplied.)
4. Show the revealed output to the user — clearly labeled as revealed so they know it contains real personal data.

Note: reveal is text-only. It does not un-redact files on disk.
