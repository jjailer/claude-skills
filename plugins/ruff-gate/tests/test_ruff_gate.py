"""Run with: python3 -m unittest discover -s plugins/ruff-gate/tests

Every test here names a way the gate could be wrong in a real repo. The two it
exists for above all: staying silent where ruff has no opinion, and reporting
only what the turn touched. Requires `ruff` on PATH.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(TESTS, "..", "hooks", "ruff_gate.py"))

_spec = importlib.util.spec_from_file_location("ruff_gate", SCRIPT)
ruff_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ruff_gate)

RUFF = '[tool.ruff]\nline-length = 88\n[tool.ruff.lint]\nselect = ["E", "F"]\n'
UNUSED_IMPORT = "import os\n"  # F401
CLEAN = "x = 1\n"
MISFORMATTED = "x = [1,  2]\n"  # lint-clean, format-dirty


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


@unittest.skipUnless(shutil.which("ruff"), "ruff is not on PATH")
class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "repo")
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.root)

    def path(self, name):
        return os.path.join(self.root, name)

    def config(self, **values):
        values.setdefault("command", ["ruff"])
        write(self.path(".claude/ruff-gate.json"), json.dumps(values))

    def hook(self, mode, payload, **env):
        environ = dict(os.environ)
        environ.pop("RUFF_GATE", None)
        environ["CLAUDE_PROJECT_DIR"] = self.root
        environ["CLAUDE_PLUGIN_DATA"] = self.data
        environ.update(env)
        done = subprocess.run(
            [sys.executable, SCRIPT, mode],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=environ,
        )
        return done.returncode, done.stderr

    def lint(self, name, **env):
        payload = {"session_id": "s1", "tool_input": {"file_path": self.path(name)}}
        return self.hook("lint", payload, **env)

    def gate(self, **env):
        return self.hook("gate", {"session_id": "s1"}, **env)


class Applicability(GateCase):
    """A globally enabled gate must cost nothing in a repo that never asked."""

    def test_repo_without_pyproject_is_silent(self):
        write(self.path("a.py"), UNUSED_IMPORT)
        self.assertEqual(self.lint("a.py"), (0, ""))

    def test_pyproject_without_ruff_section_is_silent(self):
        write(self.path("pyproject.toml"), '[project]\nname = "x"\n')
        write(self.path("a.py"), UNUSED_IMPORT)
        self.assertEqual(self.lint("a.py"), (0, ""))

    def test_an_ignored_repo_leaves_no_state_behind(self):
        # Installed globally, this runs in every session in every repo. The ones
        # it ignores must not each cost a file under the plugin's data dir.
        write(self.path("pyproject.toml"), '[project]\nname = "x"\n')
        write(self.path("a.py"), UNUSED_IMPORT)
        self.lint("a.py")
        self.gate()
        self.assertFalse(os.path.exists(os.path.join(self.data, "sessions")))

    def test_a_file_in_another_repo_is_left_to_that_repo(self):
        # Observed while building this plugin: a session launched in one repo
        # edited files in a second one, and the first repo's gate linted them
        # under its own rules. The other repo has a ruff config of its own, so
        # nothing but the project boundary keeps this gate off it.
        write(self.path("pyproject.toml"), RUFF)
        self.config()
        other = os.path.join(self.tmp, "other-repo")
        write(os.path.join(other, "pyproject.toml"), RUFF)
        write(os.path.join(other, "a.py"), UNUSED_IMPORT)

        payload = {
            "session_id": "s1",
            "tool_input": {"file_path": os.path.join(other, "a.py")},
        }
        self.assertEqual(self.hook("lint", payload), (0, ""))
        self.assertEqual(self.gate(), (0, ""), "nor may it reach the Stop gate")

    def test_off_marker_silences_a_violation_that_would_block(self):
        write(self.path("pyproject.toml"), RUFF)
        self.config()
        write(self.path("a.py"), UNUSED_IMPORT)
        code, err = self.lint("a.py")
        self.assertEqual(code, 2, "fixture must violate, or this proves nothing")
        self.assertIn("F401", err)

        write(self.path(".claude/ruff-gate.off"), "")
        self.assertEqual(self.lint("a.py"), (0, ""))

    def test_env_var_silences_a_violation_that_would_block(self):
        write(self.path("pyproject.toml"), RUFF)
        self.config()
        write(self.path("a.py"), UNUSED_IMPORT)
        self.assertEqual(self.lint("a.py")[0], 2)
        self.assertEqual(self.lint("a.py", RUFF_GATE="off"), (0, ""))

    def test_enabled_false_silences_a_violation_that_would_block(self):
        write(self.path("pyproject.toml"), RUFF)
        self.config()
        write(self.path("a.py"), UNUSED_IMPORT)
        self.assertEqual(self.lint("a.py")[0], 2)
        self.config(enabled=False)
        self.assertEqual(self.lint("a.py"), (0, ""))


class ToolchainFailure(GateCase):
    """Ruff being unhappy is not the same as the code being wrong.

    The shell version this replaced treated every nonzero exit as violations,
    so a repo where ruff could not run produced a hard block full of nonsense.
    """

    def setUp(self):
        super().setUp()
        write(self.path("pyproject.toml"), RUFF)
        write(self.path("a.py"), CLEAN)

    def test_ruff_usage_error_is_not_reported_as_violations(self):
        self.config(command=["ruff", "--no-such-flag"])
        self.assertEqual(self.lint("a.py"), (0, ""))
        self.assertEqual(self.gate(), (0, ""))

    def test_absent_binary_is_not_reported_as_violations(self):
        self.config(command=["ruff-does-not-exist"])
        self.assertEqual(self.lint("a.py"), (0, ""))
        self.assertEqual(self.gate(), (0, ""))


class SessionScope(GateCase):
    def setUp(self):
        super().setUp()
        write(self.path("pyproject.toml"), RUFF)
        self.config()

    def test_gate_is_silent_when_the_turn_touched_nothing(self):
        write(self.path("inherited.py"), UNUSED_IMPORT)
        self.assertEqual(self.gate(), (0, ""))

    def test_gate_reports_the_touched_file_and_not_inherited_debt(self):
        write(self.path("mine.py"), UNUSED_IMPORT)
        write(self.path("inherited.py"), UNUSED_IMPORT)
        self.lint("mine.py")
        code, err = self.gate()
        self.assertEqual(code, 2)
        self.assertIn("mine.py", err)
        self.assertNotIn("inherited.py", err)

    def test_gate_names_a_runnable_fix_command(self):
        write(self.path("mine.py"), UNUSED_IMPORT)
        self.lint("mine.py")
        self.assertIn("fix: ruff check --fix mine.py", self.gate()[1])

    def test_a_deleted_file_does_not_keep_the_turn_open(self):
        write(self.path("gone.py"), UNUSED_IMPORT)
        self.lint("gone.py")
        os.remove(self.path("gone.py"))
        self.assertEqual(self.gate(), (0, ""))

    def test_format_drift_is_reported_with_its_own_fix(self):
        write(self.path("mine.py"), MISFORMATTED)
        self.assertEqual(self.lint("mine.py"), (0, ""), "must be lint-clean")
        code, err = self.gate()
        self.assertEqual(code, 2)
        self.assertIn("--- format ---", err)
        self.assertIn("fix: ruff format mine.py", err)

    def test_format_false_drops_the_format_check_only(self):
        self.config(format=False)
        write(self.path("mine.py"), MISFORMATTED)
        self.lint("mine.py")
        self.assertEqual(self.gate(), (0, ""))


class NestedConfig(GateCase):
    """The assumption the whole session scope rests on.

    Ruff resolves config per file, rule selection included, so one invocation at
    the project root still holds a subtree file to the subtree's own rules. If
    that ever stopped being true, session scope would silently lint subtree
    files under the root's weaker rule set and this is what would catch it.
    """

    def setUp(self):
        super().setUp()
        root_cfg = '[tool.ruff]\nextend-exclude = ["sub"]\n'
        root_cfg += '[tool.ruff.lint]\nselect = ["E"]\n'
        write(self.path("pyproject.toml"), root_cfg)
        write(self.path("sub/pyproject.toml"), '[tool.ruff.lint]\nselect = ["F"]\n')
        write(self.path("sub/x.py"), UNUSED_IMPORT)
        self.config()

    def test_subtree_file_is_linted_under_the_subtree_rules(self):
        code, err = self.lint("sub/x.py")
        self.assertEqual(code, 2, "root selects E only; F401 must still be found")
        self.assertIn("F401", err)

    def test_gate_finds_it_too_despite_the_root_exclude(self):
        self.lint("sub/x.py")
        code, err = self.gate()
        self.assertEqual(code, 2)
        self.assertIn("F401", err)


class TreeScope(GateCase):
    """Only tree scope needs the directory list, because only traversal excludes."""

    def setUp(self):
        super().setUp()
        root_cfg = '[tool.ruff]\nextend-exclude = ["client", "server"]\n'
        root_cfg += '[tool.ruff.lint]\nselect = ["E", "F"]\n'
        write(self.path("pyproject.toml"), root_cfg)
        for name in ("client", "server"):
            write(self.path(name + "/pyproject.toml"), RUFF)
        write(self.path("contracts/x.py"), CLEAN)

    def test_discovery_finds_root_and_each_configured_subtree(self):
        found = ruff_gate.discover_dirs(self.root)
        self.assertEqual(found, [".", "client", "server"])

    def test_a_config_less_subdirectory_is_not_a_lint_root(self):
        self.assertNotIn("contracts", ruff_gate.discover_dirs(self.root))

    def test_tree_scope_reaches_a_subtree_the_root_run_excludes(self):
        self.config(scope="tree")
        write(self.path("client/a.py"), UNUSED_IMPORT)
        code, err = self.gate()
        self.assertEqual(code, 2)
        self.assertIn("client (lint)", err)
        self.assertIn("fix: cd client && ruff check --fix .", err)

    def test_tree_scope_ignores_what_the_turn_did_or_did_not_touch(self):
        self.config(scope="tree")
        write(self.path("contracts/inherited.py"), UNUSED_IMPORT)
        self.assertEqual(self.gate()[0], 2)


class Configuration(GateCase):
    def setUp(self):
        super().setUp()
        write(self.path("pyproject.toml"), RUFF)
        write(self.path("a.py"), CLEAN)

    def test_broken_config_says_so_instead_of_silently_defaulting(self):
        write(self.path(".claude/ruff-gate.json"), "{not json")
        code, err = self.gate()
        self.assertEqual(code, 2)
        self.assertIn("unreadable", err)

    def test_unknown_key_is_named(self):
        self.config(scpoe="tree")
        self.assertIn("scpoe", self.gate()[1])

    def test_absent_config_is_not_an_error(self):
        self.assertEqual(self.gate(), (0, ""))


class Units(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_governing_config_stops_at_the_project_root(self):
        write(os.path.join(self.tmp, "pyproject.toml"), RUFF)
        inner = os.path.join(self.tmp, "inner")
        leaf = os.path.join(inner, "a.py")
        write(leaf, CLEAN)
        self.assertIsNone(ruff_gate.governing_config(leaf, inner))
        self.assertEqual(ruff_gate.governing_config(leaf, self.tmp), self.tmp)

    def test_ruff_toml_counts_as_a_config(self):
        write(os.path.join(self.tmp, "ruff.toml"), "line-length = 88\n")
        self.assertTrue(ruff_gate.has_ruff_config(self.tmp))

    def test_a_pyproject_without_a_ruff_table_does_not(self):
        write(os.path.join(self.tmp, "pyproject.toml"), '[project]\nname = "x"\n')
        self.assertFalse(ruff_gate.has_ruff_config(self.tmp))


if __name__ == "__main__":
    unittest.main()
