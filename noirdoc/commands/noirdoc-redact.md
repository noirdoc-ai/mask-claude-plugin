---
description: Redact a local file via noirdoc, placing the clean copy in .noirdoc/cache/
argument-hint: <path>
---

Redact the file at `$ARGUMENTS` using the namespace from `.noirdoc/config.toml`.

Steps:

1. Verify `.noirdoc/config.toml` exists. If not, run `/noirdoc-setup` first (do not prompt — just tell the user and stop).
2. Read the `noirdoc.namespace` value from the config.
3. Compute a 12-char sha256 hash of the input path to name the clean copy (`.noirdoc/cache/<hash>.<ext>`).
4. Ensure `.noirdoc/cache/` exists.
5. Run:
   ```bash
   noirdoc redact --namespace <ns> "$ARGUMENTS" -o .noirdoc/cache/<hash>.<ext>
   ```
6. Report the path of the clean copy to the user. Do **not** read the original file afterwards.

If the user wants to also summarize/analyze/translate, this command does not do that — follow the round-trip workflow in the `noirdoc` skill from this point onward.
