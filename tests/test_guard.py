"""Tests for hooks/guard.py (the PreToolUse blocker)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import guard
import pytest

HOOK_SCRIPT = Path(__file__).parent.parent / "noirdoc" / "hooks" / "guard.py"

DEFAULT_CONFIG = """\
[noirdoc]
namespace = "test-ns"

[noirdoc.guard]
enabled = true
protected_paths = [
  "./incoming/**",
  "./clients/**",
  "./contracts/**",
  "*.contract.*",
  "*.nda.*",
]
allowlist = []

[noirdoc.cache]
dir = ".noirdoc/cache"
"""


# ---------- fixtures ----------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A tmp workspace with `.noirdoc/config.toml` containing the default config."""
    (tmp_path / ".noirdoc").mkdir()
    (tmp_path / ".noirdoc" / "config.toml").write_text(DEFAULT_CONFIG)
    (tmp_path / "incoming").mkdir()
    (tmp_path / "clients").mkdir()
    (tmp_path / "safe").mkdir()
    return tmp_path


def write_config(workspace: Path, contents: str) -> None:
    (workspace / ".noirdoc" / "config.toml").write_text(contents)


def payload(tool_name: str, tool_input: dict, cwd: Path) -> dict:
    return {"tool_name": tool_name, "tool_input": tool_input, "cwd": str(cwd)}


# ---------- match_pattern ----------


class TestMatchPattern:
    def test_directory_glob_matches_descendants(self) -> None:
        assert guard.match_pattern("incoming/foo.pdf", "./incoming/**")
        assert guard.match_pattern("incoming/sub/bar.pdf", "./incoming/**")
        assert guard.match_pattern("incoming", "./incoming/**")

    def test_directory_glob_does_not_match_sibling(self) -> None:
        assert not guard.match_pattern("incoming-other/foo.pdf", "./incoming/**")
        assert not guard.match_pattern("clean/foo.pdf", "./incoming/**")

    def test_basename_glob_matches(self) -> None:
        assert guard.match_pattern("docs/foo.contract.pdf", "*.contract.*")
        assert guard.match_pattern("foo.contract.pdf", "*.contract.*")

    def test_basename_glob_no_false_positive(self) -> None:
        assert not guard.match_pattern("docs/contract.pdf", "*.contract.*")
        assert not guard.match_pattern("contracts.pdf", "*.contract.*")

    def test_leading_dotslash_tolerated(self) -> None:
        assert guard.match_pattern("./incoming/foo.pdf", "incoming/**")
        assert guard.match_pattern("incoming/foo.pdf", "./incoming/**")

    def test_backslash_normalized(self) -> None:
        assert guard.match_pattern("incoming\\foo.pdf", "./incoming/**")


# ---------- is_protected ----------


class TestIsProtected:
    PROTECTED = ["./incoming/**", "*.nda.*"]

    def test_match_without_allowlist(self) -> None:
        assert guard.is_protected("incoming/a.pdf", self.PROTECTED, [])

    def test_no_match(self) -> None:
        assert not guard.is_protected("safe/a.pdf", self.PROTECTED, [])

    def test_allowlist_wins(self) -> None:
        assert not guard.is_protected(
            "incoming/public.pdf",
            self.PROTECTED,
            ["incoming/public.pdf"],
        )

    def test_allowlist_glob_wins(self) -> None:
        assert not guard.is_protected(
            "incoming/public/a.pdf",
            self.PROTECTED,
            ["incoming/public/**"],
        )


# ---------- extract_paths ----------


class TestExtractPaths:
    def test_read(self) -> None:
        assert guard.extract_paths("Read", {"file_path": "/abs/path.pdf"}) == ["/abs/path.pdf"]

    def test_edit(self) -> None:
        assert guard.extract_paths("Edit", {"file_path": "/abs/path.pdf"}) == ["/abs/path.pdf"]

    def test_write(self) -> None:
        assert guard.extract_paths("Write", {"file_path": "/abs/path.pdf"}) == ["/abs/path.pdf"]

    def test_read_missing_filepath(self) -> None:
        assert guard.extract_paths("Read", {}) == []

    def test_read_non_string_filepath(self) -> None:
        assert guard.extract_paths("Read", {"file_path": 42}) == []

    def test_bash_with_relative_path(self) -> None:
        paths = guard.extract_paths("Bash", {"command": "cat ./incoming/foo.pdf"})
        assert paths == ["./incoming/foo.pdf"]

    def test_bash_with_absolute_path(self) -> None:
        paths = guard.extract_paths("Bash", {"command": "cat /tmp/foo.pdf"})
        assert paths == ["/tmp/foo.pdf"]

    def test_bash_with_bare_filename_ext(self) -> None:
        paths = guard.extract_paths("Bash", {"command": "cat foo.contract.pdf"})
        assert "foo.contract.pdf" in paths

    def test_bash_without_path_like_tokens(self) -> None:
        assert guard.extract_paths("Bash", {"command": "ls -la"}) == []

    def test_bash_missing_command(self) -> None:
        assert guard.extract_paths("Bash", {}) == []

    def test_grep_with_path(self) -> None:
        assert guard.extract_paths(
            "Grep",
            {"pattern": "foo", "path": "./incoming"},
        ) == ["./incoming"]

    def test_grep_without_path_passes_through(self) -> None:
        # Grep without `path` defaults to workspace root — documented gap.
        assert guard.extract_paths("Grep", {"pattern": "foo"}) == []

    def test_glob_with_path(self) -> None:
        assert guard.extract_paths(
            "Glob",
            {"pattern": "*.pdf", "path": "./clients"},
        ) == ["./clients"]

    def test_notebook_read(self) -> None:
        assert guard.extract_paths(
            "NotebookRead",
            {"notebook_path": "/abs/book.ipynb"},
        ) == ["/abs/book.ipynb"]

    def test_notebook_edit(self) -> None:
        assert guard.extract_paths(
            "NotebookEdit",
            {"notebook_path": "/abs/book.ipynb", "cell_id": "x"},
        ) == ["/abs/book.ipynb"]

    def test_webfetch_file_scheme(self) -> None:
        assert guard.extract_paths(
            "WebFetch",
            {"url": "file:///abs/doc.pdf"},
        ) == ["/abs/doc.pdf"]

    def test_webfetch_http_ignored(self) -> None:
        assert (
            guard.extract_paths(
                "WebFetch",
                {"url": "https://example.com/foo.pdf"},
            )
            == []
        )

    def test_unknown_tool_ignored(self) -> None:
        assert guard.extract_paths("SomeNewTool", {"foo": "bar"}) == []

    def test_bash_quoted_path_with_spaces(self) -> None:
        """shlex.split keeps a quoted path with spaces as a single token."""
        paths = guard.extract_paths(
            "Bash",
            {"command": 'cat "./incoming/x with spaces.pdf"'},
        )
        assert paths == ["./incoming/x with spaces.pdf"]

    def test_bash_single_quoted_path_with_spaces(self) -> None:
        paths = guard.extract_paths(
            "Bash",
            {"command": "cat './incoming/x with spaces.pdf'"},
        )
        assert paths == ["./incoming/x with spaces.pdf"]

    def test_bash_malformed_quoting_falls_back(self) -> None:
        """Unclosed quote → shlex raises ValueError → fall back to str.split()."""
        # Should not raise; result may be empty, but the call must succeed.
        paths = guard.extract_paths(
            "Bash",
            {"command": 'cat "./incoming/unclosed'},
        )
        # str.split() yields ['cat', '"./incoming/unclosed'] — the second token
        # starts with `"` so the path regex doesn't match. We just need
        # graceful behavior, not a specific match.
        assert isinstance(paths, list)


# ---------- evaluate ----------


class TestEvaluate:
    def test_no_config_passes(self, tmp_path: Path) -> None:
        assert (
            guard.evaluate(
                payload("Read", {"file_path": str(tmp_path / "anything.pdf")}, tmp_path),
            )
            is None
        )

    def test_match_blocks(self, workspace: Path) -> None:
        result = guard.evaluate(
            payload("Read", {"file_path": str(workspace / "incoming" / "foo.pdf")}, workspace),
        )
        assert result is not None
        decision = result["hookSpecificOutput"]
        assert decision["hookEventName"] == "PreToolUse"
        assert decision["permissionDecision"] == "deny"
        assert "incoming/foo.pdf" in decision["permissionDecisionReason"]
        assert "test-ns" in decision["permissionDecisionReason"]

    def test_non_matching_path_passes(self, workspace: Path) -> None:
        assert (
            guard.evaluate(
                payload("Read", {"file_path": str(workspace / "safe" / "notes.md")}, workspace),
            )
            is None
        )

    def test_disabled_guard_passes(self, workspace: Path) -> None:
        write_config(
            workspace,
            DEFAULT_CONFIG.replace("enabled = true", "enabled = false"),
        )
        assert (
            guard.evaluate(
                payload("Read", {"file_path": str(workspace / "incoming" / "foo.pdf")}, workspace),
            )
            is None
        )

    def test_allowlist_overrides(self, workspace: Path) -> None:
        write_config(
            workspace,
            DEFAULT_CONFIG.replace("allowlist = []", 'allowlist = ["./incoming/public.pdf"]'),
        )
        assert (
            guard.evaluate(
                payload(
                    "Read",
                    {"file_path": str(workspace / "incoming" / "public.pdf")},
                    workspace,
                ),
            )
            is None
        )

    def test_malformed_toml_passes(self, workspace: Path) -> None:
        write_config(workspace, "this is = not valid = toml = [[")
        assert (
            guard.evaluate(
                payload("Read", {"file_path": str(workspace / "incoming" / "foo.pdf")}, workspace),
            )
            is None
        )

    def test_missing_noirdoc_section_passes(self, workspace: Path) -> None:
        write_config(workspace, "[other]\nvalue = 1\n")
        assert (
            guard.evaluate(
                payload("Read", {"file_path": str(workspace / "incoming" / "foo.pdf")}, workspace),
            )
            is None
        )

    def test_protected_paths_not_a_list_passes(self, workspace: Path) -> None:
        write_config(
            workspace,
            '[noirdoc]\nnamespace = "x"\n'
            '[noirdoc.guard]\nenabled = true\nprotected_paths = "not a list"\n',
        )
        assert (
            guard.evaluate(
                payload("Read", {"file_path": str(workspace / "incoming" / "foo.pdf")}, workspace),
            )
            is None
        )

    def test_bash_matching_path_blocks(self, workspace: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "cat ./incoming/foo.pdf"}, workspace),
        )
        assert result is not None
        assert "incoming/foo.pdf" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_bash_non_matching_passes(self, workspace: Path) -> None:
        assert (
            guard.evaluate(
                payload("Bash", {"command": "ls -la"}, workspace),
            )
            is None
        )

    def test_nested_cwd_finds_parent_config(self, workspace: Path) -> None:
        nested = workspace / "some" / "deep" / "dir"
        nested.mkdir(parents=True)
        result = guard.evaluate(
            payload(
                "Read",
                {"file_path": str(workspace / "incoming" / "foo.pdf")},
                nested,
            ),
        )
        assert result is not None

    def test_grep_on_protected_dir_blocks(self, workspace: Path) -> None:
        result = guard.evaluate(
            payload(
                "Grep",
                {"pattern": "Müller", "path": str(workspace / "incoming")},
                workspace,
            ),
        )
        assert result is not None
        assert "incoming" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_glob_on_protected_dir_blocks(self, workspace: Path) -> None:
        result = guard.evaluate(
            payload(
                "Glob",
                {"pattern": "*.pdf", "path": str(workspace / "clients")},
                workspace,
            ),
        )
        assert result is not None

    def test_notebook_read_on_protected_dir_blocks(self, workspace: Path) -> None:
        target = workspace / "incoming" / "analysis.ipynb"
        result = guard.evaluate(
            payload("NotebookRead", {"notebook_path": str(target)}, workspace),
        )
        assert result is not None

    def test_webfetch_local_file_blocks(self, workspace: Path) -> None:
        target = workspace / "incoming" / "foo.pdf"
        result = guard.evaluate(
            payload("WebFetch", {"url": f"file://{target}"}, workspace),
        )
        assert result is not None

    def test_webfetch_remote_url_passes(self, workspace: Path) -> None:
        assert (
            guard.evaluate(
                payload(
                    "WebFetch",
                    {"url": "https://example.com/public.pdf"},
                    workspace,
                ),
            )
            is None
        )

    def test_basename_pattern_blocks(self, workspace: Path) -> None:
        target = workspace / "safe" / "mandant.nda.docx"
        result = guard.evaluate(
            payload("Read", {"file_path": str(target)}, workspace),
        )
        assert result is not None
        assert "mandant.nda.docx" in result["hookSpecificOutput"]["permissionDecisionReason"]


# ---------- vault block (unconditional) ----------


class TestVaultBlock:
    """`~/.noirdoc/` is unreachable regardless of workspace config or allowlist.

    Tests fake `HOME` via monkeypatch so the vault lives in tmp.
    """

    def _fake_home(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> Path:
        home = tmp_path / "home"
        home.mkdir()
        vault = home / ".noirdoc"
        (vault / "namespaces" / "mandant-foo").mkdir(parents=True)
        (vault / "namespaces" / "mandant-foo" / "map.json").write_text("{}")
        monkeypatch.setenv("HOME", str(home))
        return vault

    def test_read_of_mapping_file_blocks_without_workspace_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        vault = self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(
            payload(
                "Read",
                {"file_path": str(vault / "namespaces" / "mandant-foo" / "map.json")},
                tmp_path,
            ),
        )
        assert result is not None
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "~/.noirdoc/" in reason
        assert "unconditional" in reason.lower()

    def test_read_of_vault_root_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        vault = self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(payload("Read", {"file_path": str(vault)}, tmp_path))
        assert result is not None

    def test_read_with_tilde_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(
            payload(
                "Read",
                {"file_path": "~/.noirdoc/namespaces/mandant-foo/map.json"},
                tmp_path,
            ),
        )
        assert result is not None

    def test_bash_cat_of_mapping_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        vault = self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": f"cat {vault}/namespaces/mandant-foo/map.json"},
                tmp_path,
            ),
        )
        assert result is not None

    def test_grep_in_vault_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        vault = self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(
            payload(
                "Grep",
                {"pattern": "Müller", "path": str(vault / "namespaces")},
                tmp_path,
            ),
        )
        assert result is not None

    def test_sibling_dir_not_blocked(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """`~/.noirdoc-notes/` must not match `~/.noirdoc/` by prefix."""
        home = tmp_path / "home"
        home.mkdir()
        sibling = home / ".noirdoc-notes"
        sibling.mkdir()
        (sibling / "readme.md").write_text("safe")
        monkeypatch.setenv("HOME", str(home))
        result = guard.evaluate(
            payload("Read", {"file_path": str(sibling / "readme.md")}, tmp_path),
        )
        assert result is None

    def test_allowlist_does_not_override_vault_block(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Workspace allowlist must not reach into the vault."""
        (tmp_path / ".noirdoc").mkdir()
        (tmp_path / ".noirdoc" / "config.toml").write_text(
            '[noirdoc]\nnamespace = "x"\n'
            "[noirdoc.guard]\nenabled = true\n"
            'protected_paths = ["./incoming/**"]\n'
            'allowlist = ["~/.noirdoc/**"]\n',
        )
        vault = self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(
            payload(
                "Read",
                {"file_path": str(vault / "namespaces" / "mandant-foo" / "map.json")},
                tmp_path,
            ),
        )
        assert result is not None

    def test_disabled_workspace_guard_still_blocks_vault(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """`guard.enabled = false` disables workspace protection, not the vault block."""
        (tmp_path / ".noirdoc").mkdir()
        (tmp_path / ".noirdoc" / "config.toml").write_text(
            '[noirdoc]\nnamespace = "x"\n[noirdoc.guard]\nenabled = false\n',
        )
        vault = self._fake_home(monkeypatch, tmp_path)
        result = guard.evaluate(
            payload(
                "Read",
                {"file_path": str(vault / "namespaces" / "mandant-foo" / "map.json")},
                tmp_path,
            ),
        )
        assert result is not None

    def test_relative_traversal_into_vault_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        vault = self._fake_home(monkeypatch, tmp_path)
        nested = tmp_path / "deep" / "nested"
        nested.mkdir(parents=True)
        rel = os.path.relpath(str(vault / "namespaces" / "mandant-foo" / "map.json"), str(nested))
        result = guard.evaluate(payload("Read", {"file_path": rel}, nested))
        assert result is not None

    def test_non_vault_path_with_fake_home_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        self._fake_home(monkeypatch, tmp_path)
        target = tmp_path / "safe" / "notes.md"
        target.parent.mkdir()
        target.write_text("ok")
        result = guard.evaluate(payload("Read", {"file_path": str(target)}, tmp_path))
        assert result is None


# ---------- mapping-dump command block ----------


class TestMappingDumpBlock:
    """Bash invocations of noirdoc subcommands that leak originals are blocked
    unconditionally — the block fires without any workspace config."""

    def test_ns_show_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "noirdoc ns show mandant-foo"}, tmp_path),
        )
        assert result is not None
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "noirdoc ns show" in reason or "noirdoc ns list" in reason

    def test_lookup_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "noirdoc lookup '<<PERSON_1>>' --namespace mandant-foo"},
                tmp_path,
            ),
        )
        assert result is not None

    def test_ns_show_extra_spaces_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "noirdoc  ns   show   mandant-foo"}, tmp_path),
        )
        assert result is not None

    def test_ns_show_with_absolute_binary_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "/usr/local/bin/noirdoc ns show mandant-foo"},
                tmp_path,
            ),
        )
        assert result is not None

    def test_ns_show_help_passes(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "noirdoc ns show --help"}, tmp_path),
        )
        assert result is None

    def test_lookup_help_passes(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "noirdoc lookup --help"}, tmp_path),
        )
        assert result is None

    def test_ns_list_passes(self, tmp_path: Path) -> None:
        """`ns list` only prints namespace names and must not be blocked."""
        result = guard.evaluate(
            payload("Bash", {"command": "noirdoc ns list"}, tmp_path),
        )
        assert result is None

    def test_reveal_passes(self, tmp_path: Path) -> None:
        """`reveal` is the intended output channel and must not be blocked here."""
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "echo '<<PERSON_1>> signed.' | noirdoc reveal --namespace foo"},
                tmp_path,
            ),
        )
        assert result is None

    def test_redact_passes(self, tmp_path: Path) -> None:
        """`redact` outputs placeholder content only."""
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "noirdoc redact --namespace foo ./incoming/x.pdf"},
                tmp_path,
            ),
        )
        # May be blocked for the ./incoming/ path under workspace config, but
        # must not hit the mapping-dump block.
        if result is not None:
            reason = result["hookSpecificOutput"]["permissionDecisionReason"]
            assert "mapping" not in reason.lower() or "noirdoc-protected" in reason.lower()

    def test_ns_show_substring_in_unrelated_command_passes(self, tmp_path: Path) -> None:
        """A command that mentions the words but doesn't invoke noirdoc is fine."""
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "echo 'do not run noirdoc-ns-show-foo in prod'"},
                tmp_path,
            ),
        )
        assert result is None


# ---------- SDK-import block ----------


class TestSDKImportBlock:
    """Bash invocations that import the noirdoc Python SDK leak the same data
    as `noirdoc ns show`. Blocked unconditionally, fires without workspace config."""

    def test_python_dash_c_from_noirdoc_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload(
                "Bash",
                {
                    "command": (
                        "python -c 'from noirdoc.pseudonymization import "
                        'PseudonymMapper; print(PseudonymMapper.load("ns"))\''
                    ),
                },
                tmp_path,
            ),
        )
        assert result is not None
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "noirdoc Python SDK" in reason

    def test_python_dash_c_import_noirdoc_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "python -c 'import noirdoc'"}, tmp_path),
        )
        assert result is not None

    def test_pypy3_from_noirdoc_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": 'pypy3 -c "from noirdoc.detectors import X"'},
                tmp_path,
            ),
        )
        assert result is not None

    def test_dotted_submodule_blocked(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "python -c 'from noirdoc.sdk import redact'"},
                tmp_path,
            ),
        )
        assert result is not None

    def test_case_insensitive(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload("Bash", {"command": "python -c 'IMPORT NOIRDOC'"}, tmp_path),
        )
        assert result is not None

    def test_noirdoc_cloud_does_not_match(self, tmp_path: Path) -> None:
        """`noirdoc-cloud` is a different package; the regex's `(?![\\w-])`
        lookahead must reject it."""
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "python -c 'from noirdoc-cloud import client'"},
                tmp_path,
            ),
        )
        assert result is None

    def test_noirdoctest_does_not_match(self, tmp_path: Path) -> None:
        """`noirdoctest` is a hypothetical package starting with `noirdoc` but
        continuing as a word — must not trip the import block."""
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "python -c 'from noirdoctest import t'"},
                tmp_path,
            ),
        )
        assert result is None

    def test_noirdoc_underscore_does_not_match(self, tmp_path: Path) -> None:
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "python -c 'import noirdoc_other'"},
                tmp_path,
            ),
        )
        assert result is None

    def test_cli_redact_passes(self, tmp_path: Path) -> None:
        """`noirdoc redact` is a CLI invocation, no `import` or `from` keyword."""
        result = guard.evaluate(
            payload(
                "Bash",
                {"command": "noirdoc redact --namespace foo input.pdf -o out.pdf"},
                tmp_path,
            ),
        )
        # May still pass through (no path under protected_paths in tmp_path),
        # but must not hit the SDK-import block.
        if result is not None:
            reason = result["hookSpecificOutput"]["permissionDecisionReason"]
            assert "noirdoc Python SDK" not in reason

    def test_python_module_invocation_passes(self, tmp_path: Path) -> None:
        """`python -m noirdoc.cli` is a CLI invocation via -m, not an import
        statement — the regex looks for `from`/`import` keywords specifically."""
        result = guard.evaluate(
            payload("Bash", {"command": "python -m noirdoc.cli --help"}, tmp_path),
        )
        assert result is None


# ---------- integration: script CLI ----------


class TestScriptIntegration:
    def test_script_passes_without_config(self, tmp_path: Path) -> None:
        proc = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(
                payload(
                    "Read",
                    {"file_path": str(tmp_path / "foo.pdf")},
                    tmp_path,
                ),
            ),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    def test_script_blocks_on_match(self, workspace: Path) -> None:
        proc = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=json.dumps(
                payload(
                    "Read",
                    {"file_path": str(workspace / "incoming" / "foo.pdf")},
                    workspace,
                ),
            ),
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert proc.returncode == 0
        decision = json.loads(proc.stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_script_survives_bad_stdin(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert proc.returncode == 0
