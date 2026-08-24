#!/usr/bin/env python3
"""Behavioural tests for the node section of intent_layer_check.py.

Every case builds a real git repo and drives the hook through its actual stdin
contract, because that is where the logic lives: which node a path resolves to,
and whether that node counts as already updated. Unit-testing the resolver
alone would miss the half of the behaviour that depends on what git reports and
what is on disk.

Each test is tied to a failure mode worth naming, most of them a way the
reminder goes wrong rather than a way it goes right — firing forever on
something you cannot act on, falling back to the repo root on every commit, or
going quiet on a node that genuinely drifted. A hook that speaks too often gets
disabled, and one that speaks too little is not noticed at all.

mtimes are set explicitly rather than slept for: the local-node strike test
compares clocks, and a test that waits on the wall clock is both slow and
flaky about it.

Run: python3 hooks/test_intent_layer_check.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "intent_layer_check.py"

# Any fixed epoch. Files are stamped relative to it so "newer" and "older" are
# stated by the test rather than inferred from how long it took to run.
T0 = 1_700_000_000
OLD, NEW, NEWER = T0, T0 + 100, T0 + 200


class Repo:
    """A throwaway git repo, plus the one hook invocation under test."""

    def __init__(self, root):
        self.root = Path(root)
        self.git("init", "-q", ".")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")

    def git(self, *args):
        return subprocess.run(
            ("git", *args),
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def write(self, rel, text="x\n", at=NEW):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        os.utime(path, (at, at))
        return path

    def commit(self, message="c"):
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def stage(self, *rels):
        self.git("add", "--", *rels)

    def run(self):
        """The hook's advisory text for a `git commit`, or "" when silent."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m x"},
            "cwd": str(self.root),
        }
        result = subprocess.run(
            (sys.executable, str(HOOK)),
            input=json.dumps(event),
            capture_output=True,
            text=True,
            check=False,
        )
        self.exit_code = result.returncode
        if not result.stdout.strip():
            return ""
        payload = json.loads(result.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]


class NodeSectionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Repo(self._tmp.name)

    # -- helpers ---------------------------------------------------------
    def implicated(self, output):
        """The nodes the reminder named, as `node <- first file` strings."""
        return [
            line.strip()
            for line in output.splitlines()
            if line.startswith("  ") and " <- " in line
        ]

    def assertSilent(self, output):
        self.assertEqual(output, "", "expected no reminder")
        self.assertEqual(self.repo.exit_code, 0)

    def assertNames(self, output, expected):
        self.assertEqual(self.implicated(output), [expected])
        self.assertEqual(self.repo.exit_code, 0)

    def redirected(self, output):
        return "gitignores CLAUDE.local.md" in output

    # -- a committed layer, the behaviour that already existed -----------
    def test_committed_node_implicated_when_the_commit_leaves_it_alone(self):
        self.repo.write("other/CLAUDE.md", "# team\n", at=OLD)
        self.repo.write("other/y.py", at=OLD)
        self.repo.commit()
        self.repo.write("other/y.py", "changed\n", at=NEW)
        self.repo.stage("other/y.py")
        self.assertNames(self.repo.run(), "other/CLAUDE.md  <- other/y.py")

    def test_committed_node_struck_by_appearing_in_the_commit(self):
        self.repo.write("other/CLAUDE.md", "# team\n", at=OLD)
        self.repo.write("other/y.py", at=OLD)
        self.repo.commit()
        self.repo.write("other/y.py", "changed\n", at=NEW)
        self.repo.write("other/CLAUDE.md", "# team v2\n", at=NEW)
        self.repo.stage("other/y.py", "other/CLAUDE.md")
        self.assertSilent(self.repo.run())

    def test_silent_when_no_node_sits_above_the_change(self):
        self.repo.write("other/CLAUDE.md", "# team\n", at=OLD)
        self.repo.write("bare/deeper/z.py", at=OLD)
        self.repo.commit()
        self.repo.write("bare/deeper/z.py", "changed\n", at=NEW)
        self.repo.stage("bare/deeper/z.py")
        self.assertSilent(self.repo.run())

    def test_root_node_is_not_a_fallback_for_deep_paths(self):
        """Falling back would implicate the root on nearly every commit."""
        self.repo.write("CLAUDE.md", "# root\n", at=OLD)
        self.repo.write("deep/er/d.py", at=OLD)
        self.repo.commit()
        self.repo.write("deep/er/d.py", "changed\n", at=NEW)
        self.repo.stage("deep/er/d.py")
        self.assertSilent(self.repo.run())

    # -- a local layer ---------------------------------------------------
    def test_local_node_implicated_when_the_code_is_newer(self):
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("sub/x.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/CLAUDE.local.md", "# notes\n", at=OLD)
        self.repo.write("sub/x.py", "changed\n", at=NEW)
        self.repo.stage("sub/x.py")
        self.assertNames(self.repo.run(), "sub/CLAUDE.local.md  <- sub/x.py")

    def test_local_node_struck_by_being_newer_than_the_code(self):
        """It can never be in the commit, so the clock is the only evidence."""
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("sub/x.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/x.py", "changed\n", at=NEW)
        self.repo.write("sub/CLAUDE.local.md", "# updated\n", at=NEWER)
        self.repo.stage("sub/x.py")
        self.assertSilent(self.repo.run())

    def test_local_node_struck_when_the_two_share_an_mtime(self):
        """One editing pass can stamp both; `>=` is deliberate, not a slip."""
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("sub/x.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/x.py", "changed\n", at=NEW)
        self.repo.write("sub/CLAUDE.local.md", "# updated\n", at=NEW)
        self.repo.stage("sub/x.py")
        self.assertSilent(self.repo.run())

    def test_local_node_wins_a_directory_holding_both(self):
        """It loads last, and it is the one you can write."""
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("sub/CLAUDE.md", "# team\n", at=OLD)
        self.repo.write("sub/x.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/CLAUDE.local.md", "# notes\n", at=OLD)
        self.repo.write("sub/x.py", "changed\n", at=NEW)
        self.repo.stage("sub/x.py")
        self.assertNames(self.repo.run(), "sub/CLAUDE.local.md  <- sub/x.py")

    def test_deletions_fire_even_when_the_local_node_is_newest(self):
        """A `git rm` is when a node most likely has a tombstone to prune."""
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("sub/x.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/CLAUDE.local.md", "# newest\n", at=NEWER)
        self.repo.git("rm", "-q", "sub/x.py")
        self.assertNames(self.repo.run(), "sub/CLAUDE.local.md  <- sub/x.py")

    def test_root_local_node_reachable_from_top_level_files(self):
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("root.py", at=OLD)
        self.repo.commit()
        self.repo.write("CLAUDE.local.md", "# root local\n", at=OLD)
        self.repo.write("root.py", "changed\n", at=NEW)
        self.repo.stage("root.py")
        self.assertNames(self.repo.run(), "CLAUDE.local.md  <- root.py")

    def test_root_local_node_is_not_a_fallback_for_deep_paths(self):
        self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("deep/er/d.py", at=OLD)
        self.repo.commit()
        self.repo.write("CLAUDE.local.md", "# root local\n", at=OLD)
        self.repo.write("deep/er/d.py", "changed\n", at=NEW)
        self.repo.stage("deep/er/d.py")
        self.assertSilent(self.repo.run())

    # -- a node that is not yours to edit --------------------------------
    def _teammate_lands_a_node(self, local_mode):
        if local_mode:
            self.repo.write(".gitignore", "CLAUDE.local.md\n", at=OLD)
        self.repo.write("newdir/CLAUDE.md", "# theirs\n", at=OLD)
        self.repo.write("newdir/n.py", at=OLD)
        self.repo.commit()
        self.repo.write("newdir/n.py", "changed\n", at=NEW)
        self.repo.stage("newdir/n.py")

    def test_local_mode_redirects_to_the_sibling_not_yet_written(self):
        """Otherwise this fires forever: the named file is not yours to edit."""
        self._teammate_lands_a_node(local_mode=True)
        output = self.repo.run()
        self.assertNames(output, "newdir/CLAUDE.md  <- newdir/n.py")
        self.assertTrue(self.redirected(output), "expected the sibling redirect")

    def test_redirect_stops_once_the_sibling_exists(self):
        self._teammate_lands_a_node(local_mode=True)
        self.repo.write("newdir/CLAUDE.local.md", "# learned\n", at=NEWER)
        self.assertSilent(self.repo.run())

    def test_sibling_then_resolves_ahead_of_the_committed_node(self):
        self._teammate_lands_a_node(local_mode=True)
        self.repo.write("newdir/CLAUDE.local.md", "# learned\n", at=OLD)
        output = self.repo.run()
        self.assertNames(output, "newdir/CLAUDE.local.md  <- newdir/n.py")
        self.assertFalse(self.redirected(output), "redirect is for the seeding case only")

    def test_a_repo_that_commits_its_layer_never_sees_the_redirect(self):
        """The regression that matters: noise for everyone who doesn't need it."""
        self._teammate_lands_a_node(local_mode=False)
        output = self.repo.run()
        self.assertNames(output, "newdir/CLAUDE.md  <- newdir/n.py")
        self.assertFalse(self.redirected(output))


if __name__ == "__main__":
    unittest.main(verbosity=2)
