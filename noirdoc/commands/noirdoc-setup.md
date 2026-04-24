---
description: Set up noirdoc for this workspace (install check, namespace, protected paths, config file)
---

Run the first-run setup flow documented in the `noirdoc` skill. The goal is to leave this workspace ready to use the round-trip redact/reveal workflow.

Steps (invoke the skill's "First-run setup" section for the full detail):

1. Check `noirdoc --version`. If missing, ask the user for consent and run `pip install 'noirdoc[full]' && noirdoc models pull` (warn about the ~560 MB download).
2. Suggest a namespace based on the current directory name and confirm with the user.
3. Write `.noirdoc/config.toml` from the template at `${CLAUDE_PLUGIN_ROOT}/templates/config.toml`, substituting the chosen namespace.
4. Confirm the default protected-path list (`./incoming/**`, `./clients/**`, `./contracts/**`, `*.contract.*`, `*.nda.*`). Edit before writing if the user wants a different set.
5. If this is a git repo, ensure `.noirdoc/cache/` is in `.gitignore`.
6. Surface the privacy note: the namespace mapping at `~/.noirdoc/namespaces/<namespace>/` is reversible and should be treated as sensitive.

If `.noirdoc/config.toml` already exists, confirm with the user before overwriting.
