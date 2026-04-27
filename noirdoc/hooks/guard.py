#!/usr/bin/env python3
"""
noirdoc-claude-plugin — PreToolUse guard.

Reads a Claude Code tool-use event from stdin, walks up from the tool's cwd
looking for `.noirdoc/config.toml`, and blocks Read/Edit/Write/Bash tool calls
whose target paths match configured protected globs. Uses stdlib only; never
imports noirdoc. Fails open (passes through) when no config exists at all so
users who have not opted in experience no false positives. Once a config
exists, parse errors and schema violations fail closed — a tampered or
truncated config is more likely to be an attack/incident signal than a
benign edge case, and silently disabling the guard is the wrong default.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.toml"
NOIRDOC_DIR = ".noirdoc"
DEFAULT_NAMESPACE = "default"
# ~/.noirdoc/ holds the reversible real-name ↔ placeholder mapping. Reading any
# file under it would let Claude reverse every placeholder in the session.
# Blocked unconditionally, independent of workspace config and allowlist.
VAULT_DIRNAME = ".noirdoc"

# Conservative Bash tokenizer — only tokens that clearly look like filesystem
# paths are surfaced. Complex shell (pipes, process substitution, $(...)) is
# intentionally not parsed.
# shlex.split delivers a single token even when the path contains spaces (the
# user quoted it). Allow `.+` after the path-shape prefix so quoted-with-spaces
# paths still match. Bare-filename branch stays no-slash; spaces are tolerated
# there too, since a quoted "lorem ipsum.pdf" is still a path-like reference.
_PATH_TOKEN_RE = re.compile(
    r"^(?:\.{1,2}/|/|~/).+$"
    r"|^[^/]+\.(?:pdf|docx|xlsx|pptx|txt|csv|md|html|json|yaml|yml)$",
    re.IGNORECASE,
)

# Two noirdoc CLI subcommands leak real-name data to stdout and must not be
# invoked via Bash (the subprocess stdout becomes a tool result and lands in
# this session's context):
#   - `noirdoc ns show <ns>`    — dumps the full reverse mapping as JSON.
#   - `noirdoc lookup <pseudonym> --namespace <ns>` — prints the original
#     behind a single placeholder. Enumeration makes this a per-token leak.
# Best-effort regex — bypassed by aliases, env indirection, or Python imports
# of the SDK. Catches the obvious case where Claude invokes by name. The
# negative lookahead carves out the literal help/version forms only — flag-first
# invocations like `noirdoc ns show --json <ns>` and the argparse `--`
# end-of-options separator must still match (they leak just like the
# positional-first form).
_MAPPING_DUMP_RES = (
    re.compile(
        r"\bnoirdoc\s+ns\s+show\b(?!\s+(?:-h|--help|--version)(?:\s|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnoirdoc\s+lookup\b(?!\s+(?:-h|--help|--version)(?:\s|$))",
        re.IGNORECASE,
    ),
)

# Importing the noirdoc Python SDK from a Bash one-liner exposes the same
# real-name mapping data as `noirdoc ns show` (both go through the SDK's
# `PseudonymMapper`). Block the obvious one-liner case at the regex tier.
# Best-effort — bypassable by base64-encoded payloads, `__import__("noirdoc")`,
# or aliasing the package. Catches `python -c 'from noirdoc...'` /
# `python -c 'import noirdoc'` and the same via pypy, python3, etc.
_SDK_IMPORT_RES = (
    re.compile(r"\bfrom\s+noirdoc(?:\.\w+)*(?![\w-])", re.IGNORECASE),
    re.compile(r"\bimport\s+noirdoc(?:\.\w+)*(?![\w-])", re.IGNORECASE),
)

# Modifying `.noirdoc/config.toml` lets a prompt-injected Claude flip
# `guard.enabled = false` or push `**` into `allowlist`, neutralizing the
# workspace guard. Once a config exists, Edit/Write/NotebookEdit on it and any
# Bash command that references it literally are denied.
# Reads remain allowed (the Read tool is fine; the config has no PII), and the
# block does not apply when no config exists yet so that `/noirdoc-setup` can
# create one.
_CONFIG_LITERAL_RE = re.compile(r"\.noirdoc/config\.toml\b", re.IGNORECASE)

# Literal vault-pattern scan over the full Bash command string. shlex-based
# token extraction collapses subshell bodies (`bash -c "..."`, `eval "..."`,
# `python -c "..."`) into one opaque token, so the token-based vault check
# misses them. This regex re-scans the raw command and catches `~/.noirdoc/`,
# `$HOME/.noirdoc/`, `${HOME}/.noirdoc/`, and absolute home-dir paths ending
# in `/.noirdoc/`. Best-effort — defeated by base64-encoded payloads or
# character-by-character construction.
_VAULT_LITERAL_RE = re.compile(
    r"(?:^|[\s'\"`(=])"
    r"(?:~|\$HOME|\$\{HOME\}|/Users/[^/\s'\"`]+|/home/[^/\s'\"`]+)"
    r"/\.noirdoc(?:/|$|[\s'\"`])"
)


def find_config(start: Path) -> Path | None:
    """Walk up from `start` looking for `.noirdoc/config.toml`."""
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / NOIRDOC_DIR / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_config(config_path: Path) -> dict[str, Any] | None:
    """Return parsed TOML, or None if unreadable/malformed (caller fails open)."""
    try:
        with config_path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"noirdoc-guard: could not read {config_path}: {exc}", file=sys.stderr)
        return None


def _normalize(p: str) -> str:
    p = p.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return p


def match_pattern(rel_path: str, pattern: str) -> bool:
    """
    Match `rel_path` against `pattern`.

    Supports:
      - "prefix/**" — matches prefix itself and anything under it
      - fnmatch globs against the full relative path
      - fnmatch globs against the basename (for patterns like "*.contract.*")
    """
    rel = _normalize(rel_path)
    p = _normalize(pattern)

    if p.endswith("/**"):
        prefix = p[:-3]
        return rel == prefix or rel.startswith(prefix + "/")

    if fnmatch.fnmatch(rel, p):
        return True
    basename = rel.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(basename, p)


def is_protected(rel_path: str, protected: list[str], allowlist: list[str]) -> bool:
    """True iff `rel_path` matches any protected pattern and no allowlist pattern."""
    if not any(match_pattern(rel_path, pat) for pat in protected):
        return False
    if any(match_pattern(rel_path, pat) for pat in allowlist):
        return False
    return True


def extract_paths(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    """Return candidate filesystem paths that this tool call will touch.

    Covered tools:
      - Read / Edit / Write: `file_path`
      - NotebookRead / NotebookEdit: `notebook_path`
      - Grep / Glob: `path` (search root) — Note: when unspecified, Grep/Glob
        defaults to the workspace root and can surface content from protected
        files. Documented gap; users should avoid ungrounded greps on
        sensitive workspaces.
      - WebFetch: `url` if it uses `file://` scheme (local file via fetch);
        http(s) URLs are out of scope for this hook.
      - Bash: best-effort path-shaped token extraction.
    """
    if tool_name in ("Read", "Edit", "Write"):
        fp = tool_input.get("file_path")
        return [fp] if isinstance(fp, str) else []
    if tool_name in ("NotebookRead", "NotebookEdit"):
        fp = tool_input.get("notebook_path")
        return [fp] if isinstance(fp, str) else []
    if tool_name in ("Grep", "Glob"):
        fp = tool_input.get("path")
        return [fp] if isinstance(fp, str) else []
    if tool_name == "WebFetch":
        url = tool_input.get("url", "")
        if isinstance(url, str) and url.startswith("file://"):
            return [url[len("file://") :]]
        return []
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if not isinstance(cmd, str):
            return []
        try:
            tokens = shlex.split(cmd, posix=True)
        except ValueError:
            tokens = cmd.split()
        return [tok for tok in tokens if _PATH_TOKEN_RE.match(tok)]
    return []


def to_relative(path_str: str, workspace_root: Path) -> str:
    """Return `path_str` relative to `workspace_root`, or the original string if outside."""
    try:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = (workspace_root / p).resolve()
        else:
            p = p.resolve()
        return str(p.relative_to(workspace_root))
    except (ValueError, OSError):
        return path_str


def _vault_root() -> str | None:
    """Resolved absolute path of `~/.noirdoc`, or None if HOME is unresolvable."""
    try:
        home = os.path.expanduser("~")
        if not os.path.isabs(home):
            return None
        return os.path.realpath(os.path.join(home, VAULT_DIRNAME))
    except (OSError, ValueError):
        return None


def is_existing_workspace_config(path_str: str, cwd: str) -> bool:
    """True iff `path_str` resolves to the `.noirdoc/config.toml` that already
    governs `cwd` (via walk-up). Returns False when no config exists at any
    ancestor — that case is the bootstrap path for `/noirdoc-setup`.
    """
    config_path = find_config(Path(cwd))
    if config_path is None:
        return False
    try:
        expanded = os.path.expanduser(path_str)
        if not os.path.isabs(expanded):
            expanded = os.path.join(cwd, expanded)
        candidate = os.path.realpath(expanded)
        target = os.path.realpath(str(config_path))
    except (OSError, ValueError):
        return False
    return candidate == target


def detects_vault_reference(command: str) -> str | None:
    """Return the literal vault-shaped substring in `command`, or None.

    Catches subshell wrappers (`bash -c "cat ~/.noirdoc/..."`) and the
    `$HOME` / `${HOME}` forms that the token-based path extractor misses.
    Also matches the resolved absolute vault path verbatim — covers cases
    where Claude knows the user's home dir and uses the resolved form
    inside an opaque subshell.
    """
    m = _VAULT_LITERAL_RE.search(command)
    if m is not None:
        return m.group(0).strip(" \t'\"`(=")
    vault = _vault_root()
    if vault is not None and vault in command:
        return vault
    return None


def detects_config_modify(command: str, cwd: str) -> bool:
    """True iff a Bash `command` references `.noirdoc/config.toml` *and* a
    config already governs `cwd`.

    Conservative — denies reads too. Use the Read tool to inspect the config;
    Bash references stay opaque enough (redirects, subshells, here-docs) that
    we can't reliably distinguish read from write, so we deny uniformly.
    """
    if find_config(Path(cwd)) is None:
        return False
    return bool(_CONFIG_LITERAL_RE.search(command))


def is_vault_path(path_str: str, cwd: str) -> bool:
    """True iff `path_str` resolves to `~/.noirdoc` or anything underneath it.

    Handles `~` expansion, relative paths against `cwd`, symlinks, and `..`
    traversal via `os.path.realpath`.
    """
    vault = _vault_root()
    if vault is None:
        return False
    try:
        expanded = os.path.expanduser(path_str)
        if not os.path.isabs(expanded):
            expanded = os.path.join(cwd, expanded)
        candidate = os.path.realpath(expanded)
    except (OSError, ValueError):
        return False
    return candidate == vault or candidate.startswith(vault + os.sep)


def detects_mapping_dump(command: str) -> bool:
    """True iff `command` invokes a noirdoc subcommand that prints originals."""
    return any(pattern.search(command) for pattern in _MAPPING_DUMP_RES)


def detects_sdk_import(command: str) -> bool:
    """True iff `command` imports the noirdoc Python SDK (e.g. via `python -c`)."""
    return any(pattern.search(command) for pattern in _SDK_IMPORT_RES)


def build_mapping_dump_block_payload() -> dict[str, Any]:
    reason = (
        "Blocked: this command invokes a noirdoc subcommand that prints "
        "real-name data to stdout (`noirdoc ns show` dumps the full reverse "
        "mapping; `noirdoc lookup` returns the original behind a pseudonym). "
        "Bash tool output becomes a tool result in this session's context, so "
        "running these would put originals into the transcript — defeating "
        "redaction just as surely as reading the vault directly.\n"
        "\n"
        "This block is unconditional — independent of workspace config and "
        "allowlist. For a safe presence check, use `noirdoc ns list` (names "
        "only). To restore originals in an assistant response, use `noirdoc "
        "reveal` via the `/noirdoc-reveal` command — that is the intended, "
        "minimally-scoped reveal path. For raw inspection, the user can run "
        "these commands themselves outside Claude Code."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def build_sdk_import_block_payload() -> dict[str, Any]:
    reason = (
        "Blocked: this command imports the noirdoc Python SDK. The SDK reads "
        "the same reverse mapping that `noirdoc ns show` and `noirdoc lookup` "
        "expose — `from noirdoc.pseudonymization import PseudonymMapper` plus "
        "`get_mapping_summary()` returns full real-name data. Bash subprocess "
        "stdout becomes a tool result in this session's context, so running "
        "this would put originals into the transcript.\n"
        "\n"
        "This block is unconditional — independent of workspace config and "
        "allowlist. The intended path back to originals is `noirdoc reveal` on "
        "a specific piece of text via `/noirdoc-reveal`. For raw inspection of "
        "the mapping, the user can run such Python in a regular terminal "
        "outside Claude Code."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def build_malformed_config_block_payload(config_path: Path, detail: str) -> dict[str, Any]:
    reason = (
        f"Blocked: `{config_path}` exists but is malformed ({detail}). The "
        "noirdoc guard cannot decide what to protect from a config it cannot "
        "parse, so it fails closed — denying tool calls is safer than silently "
        "passing them through.\n"
        "\n"
        "Fix: ask the user to repair the file (or delete it to opt out of the "
        "guard entirely). Do not edit it from inside this Claude session — "
        "`.noirdoc/config.toml` modifications are blocked unconditionally."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def build_workspace_config_block_payload() -> dict[str, Any]:
    reason = (
        "Blocked: this tool call would modify `.noirdoc/config.toml`. The "
        "workspace config governs the noirdoc guard (which paths are protected, "
        "whether the guard is enabled at all). Letting Claude rewrite it from "
        "inside a session would let a prompt-injected turn flip "
        "`guard.enabled = false` or push `**` into `allowlist`, defeating the "
        "guardrail.\n"
        "\n"
        "This block is unconditional — it is not governed by `protected_paths` "
        "or `allowlist`. Reads via the Read tool remain allowed.\n"
        "\n"
        "If the user wants to extend the allowlist, they should edit "
        "`.noirdoc/config.toml` themselves in a regular terminal outside Claude "
        "Code. `/noirdoc-allow` prints the line to add but does not write it."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def build_vault_block_payload(matches: list[str]) -> dict[str, Any]:
    reason = (
        f"The following path(s) are inside the noirdoc vault (~/.noirdoc/): "
        f"{', '.join(matches)}.\n"
        "This directory holds the reversible real-name ↔ placeholder mapping for every "
        "redacted document in every namespace. Reading any file under it would let you "
        "reverse every placeholder in this session, defeating redaction entirely.\n"
        "\n"
        "This block is unconditional — it is not governed by workspace config and cannot "
        "be allowlisted. Do not attempt to bypass it.\n"
        "\n"
        "If you need to restore real names in a redacted text, run the noirdoc CLI via "
        "`/noirdoc-reveal`. It reveals inline without exposing the mapping itself."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def build_block_payload(namespace: str, matches: list[str]) -> dict[str, Any]:
    reason = (
        f"The following path(s) are noirdoc-protected: {', '.join(matches)}.\n"
        "Do not read them directly. Redact first, then read the clean copy:\n"
        "\n"
        f"  noirdoc redact --namespace {namespace} <path> -o .noirdoc/cache/<name>.<ext>\n"
        "\n"
        "Then retry with the redacted path. If this file genuinely does not contain\n"
        "personal data, ask the user before running /noirdoc-allow <path> — adding to\n"
        "the allowlist disables the guardrail for that path."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def evaluate(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pure decision function: return a block payload, or None to pass."""
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if isinstance(cmd, str) and detects_mapping_dump(cmd):
            return build_mapping_dump_block_payload()
        if isinstance(cmd, str) and detects_sdk_import(cmd):
            return build_sdk_import_block_payload()
        if isinstance(cmd, str) and detects_config_modify(cmd, cwd):
            return build_workspace_config_block_payload()
        if isinstance(cmd, str):
            literal = detects_vault_reference(cmd)
            if literal is not None:
                return build_vault_block_payload([literal])

    if tool_name in ("Edit", "Write", "NotebookEdit"):
        config_targets = [
            p for p in extract_paths(tool_name, tool_input) if is_existing_workspace_config(p, cwd)
        ]
        if config_targets:
            return build_workspace_config_block_payload()

    paths = extract_paths(tool_name, tool_input)

    vault_matches = [p for p in paths if is_vault_path(p, cwd)]
    if vault_matches:
        return build_vault_block_payload(vault_matches)

    config_path = find_config(Path(cwd))
    if config_path is None:
        return None

    config = load_config(config_path)
    if config is None:
        # File exists but didn't parse — fail closed. A workspace owner who
        # placed `.noirdoc/config.toml` expects the guard active; silent
        # bypass on a tampered or truncated file is the wrong default.
        return build_malformed_config_block_payload(config_path, "TOML parse error")

    section = config.get("noirdoc", {})
    if not isinstance(section, dict):
        # `[noirdoc]` missing or not a table → treat as opt-out. This is the
        # "I have a `.noirdoc/config.toml` for some other tool" case.
        return None

    guard = section.get("guard", {})
    if not isinstance(guard, dict):
        return build_malformed_config_block_payload(
            config_path,
            "`[noirdoc.guard]` is not a table",
        )
    if not guard.get("enabled", True):
        return None

    protected = guard.get("protected_paths", []) or []
    allowlist = guard.get("allowlist", []) or []
    if not isinstance(protected, list):
        return build_malformed_config_block_payload(
            config_path,
            "`noirdoc.guard.protected_paths` is not a list",
        )
    if not isinstance(allowlist, list):
        return build_malformed_config_block_payload(
            config_path,
            "`noirdoc.guard.allowlist` is not a list",
        )

    namespace = section.get("namespace", DEFAULT_NAMESPACE)
    if not isinstance(namespace, str):
        namespace = DEFAULT_NAMESPACE

    if not paths:
        return None

    workspace_root = config_path.parent.parent
    matches = [
        to_relative(p, workspace_root)
        for p in paths
        if is_protected(to_relative(p, workspace_root), protected, allowlist)
    ]
    if not matches:
        return None

    return build_block_payload(namespace, matches)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"noirdoc-guard: invalid stdin JSON: {exc}", file=sys.stderr)
        return 0

    decision = evaluate(payload)
    if decision is None:
        return 0

    print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
