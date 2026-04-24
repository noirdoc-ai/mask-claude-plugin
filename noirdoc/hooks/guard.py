#!/usr/bin/env python3
"""
noirdoc-claude-plugin — PreToolUse guard.

Reads a Claude Code tool-use event from stdin, walks up from the tool's cwd
looking for `.noirdoc/config.toml`, and blocks Read/Edit/Write/Bash tool calls
whose target paths match configured protected globs. Uses stdlib only; never
imports noirdoc. Fails open (passes through) when no config exists or config
is malformed, so users who have not opted in experience no false positives.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.toml"
NOIRDOC_DIR = ".noirdoc"
DEFAULT_NAMESPACE = "default"

# Conservative Bash tokenizer — only tokens that clearly look like filesystem
# paths are surfaced. Complex shell (pipes, process substitution, $(...)) is
# intentionally not parsed.
_PATH_TOKEN_RE = re.compile(
    r"^(?:\.{1,2}/|/|~/)[^\s]+$"
    r"|^[^\s/]+\.(?:pdf|docx|xlsx|pptx|txt|csv|md|html|json|yaml|yml)$",
    re.IGNORECASE,
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
        return [tok for tok in cmd.split() if _PATH_TOKEN_RE.match(tok)]
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

    config_path = find_config(Path(cwd))
    if config_path is None:
        return None

    config = load_config(config_path)
    if config is None:
        return None

    section = config.get("noirdoc", {})
    if not isinstance(section, dict):
        return None

    guard = section.get("guard", {})
    if not isinstance(guard, dict) or not guard.get("enabled", True):
        return None

    protected = guard.get("protected_paths", []) or []
    allowlist = guard.get("allowlist", []) or []
    if not isinstance(protected, list) or not isinstance(allowlist, list):
        return None

    namespace = section.get("namespace", DEFAULT_NAMESPACE)
    if not isinstance(namespace, str):
        namespace = DEFAULT_NAMESPACE

    paths = extract_paths(tool_name, tool_input)
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
