#!/usr/bin/env python3
"""Behavioural tests for intent_layer_check.py.

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

Every run gets a throwaway HOME. The hook reads transcripts from and writes
state under ~/.claude, and a test must never touch the real one.

Run: python3 -m unittest discover -s plugins/intent-layer/tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "intent_layer_check.py"

# Any fixed epoch. Files are stamped relative to it so "newer" and "older" are
# stated by the test rather than inferred from how long it took to run.
T0 = 1_700_000_000
OLD, NEW, NEWER = T0, T0 + 100, T0 + 200


class Repo:
    """A throwaway git repo, plus the hook invocation under test."""

    def __init__(self, root, home):
        self.root = Path(root)
        self.home = Path(home)
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

    def run(self, command="git commit -m x", cwd=None, **fields):
        """The hook's advisory text for a Bash `command`, or "" when silent."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd or self.root),
            **fields,
        }
        return self.invoke(json.dumps(event))

    def invoke(self, stdin, *args):
        """Run the hook with raw stdin; returns stdout (parsed for hook mode)."""
        result = subprocess.run(
            (sys.executable, str(HOOK), *args),
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.root,
            env={**os.environ, "HOME": str(self.home)},
        )
        self.exit_code = result.returncode
        self.stderr = result.stderr
        if args:
            return result.stdout
        if not result.stdout.strip():
            return ""
        payload = json.loads(result.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Resolved, because git reports the toplevel through symlinks (/var is
        # /private/var on macOS) and transcript paths must agree with it.
        base = Path(self._tmp.name).resolve()
        (base / "repo").mkdir()
        (base / "home").mkdir()
        self.repo = Repo(base / "repo", base / "home")

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
        self.assertEqual(self.repo.exit_code, 0, self.repo.stderr)

    def assertNames(self, output, *expected):
        self.assertEqual(self.implicated(output), list(expected))
        self.assertEqual(self.repo.exit_code, 0, self.repo.stderr)

    def redirected(self, output):
        return "gitignores CLAUDE.local.md" in output


class NodeSectionTest(RepoTestCase):
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

    def test_committing_from_a_subdirectory_still_resolves_nodes(self):
        """git reports staged paths root-relative but lists files cwd-relative.

        Mixing the two, and joining against the subdirectory as if it were the
        root, silently missed every node for any commit made below the top.
        """
        self.repo.write("sub/CLAUDE.md", "# sub\n", at=OLD)
        self.repo.write("sub/deep/a.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/deep/a.py", "changed\n", at=NEW)
        self.repo.stage("sub/deep/a.py")
        output = self.repo.run(cwd=self.repo.root / "sub")
        self.assertNames(output, "sub/CLAUDE.md  <- sub/deep/a.py")

    def test_non_ascii_path_still_resolves_its_node(self):
        """git quotes non-ASCII paths by default, which breaks textual resolution."""
        self.repo.write("sub/CLAUDE.md", "# sub\n", at=OLD)
        self.repo.write("sub/café.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/café.py", "changed\n", at=NEW)
        self.repo.stage("sub/café.py")
        self.assertNames(self.repo.run(), "sub/CLAUDE.md  <- sub/café.py")

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


class CommandShapeTest(RepoTestCase):
    """PreToolUse runs *before* the command, so the index alone is not the commit.

    Every case starts from a committed node over committed code, with the code
    then changed on disk but not staged — the state the hook actually sees when
    the staging happens in the same Bash call as the commit.
    """

    def setUp(self):
        super().setUp()
        self.repo.write("sub/CLAUDE.md", "# sub\n", at=OLD)
        self.repo.write("sub/a.py", at=OLD)
        self.repo.write("other/CLAUDE.md", "# other\n", at=OLD)
        self.repo.write("other/y.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/a.py", "changed\n", at=NEW)

    SUB = "sub/CLAUDE.md  <- sub/a.py"

    def test_add_then_commit_in_one_call(self):
        """The shape Claude uses most; the index is still empty when the hook runs."""
        self.assertNames(self.repo.run("git add sub/a.py && git commit -m x"), self.SUB)

    def test_heredoc_message_after_same_call_add(self):
        """Claude Code's default commit shape: a quoted heredoc with apostrophes."""
        command = (
            "git add sub/a.py && git commit -m \"$(cat <<'EOF'\n"
            "fix: don't break it\n\nCo-Authored-By: x\nEOF\n)\""
        )
        self.assertNames(self.repo.run(command), self.SUB)

    def test_add_all_then_commit(self):
        self.repo.write("sub/new.py", at=NEW)
        output = self.repo.run("git add -A && git commit -m x")
        self.assertNames(output, "sub/CLAUDE.md  <- sub/a.py (+1 more)")

    def test_cd_then_relative_add(self):
        """A relative pathspec is resolved from where the `cd` left the shell."""
        self.assertNames(self.repo.run("cd sub && git add a.py && git commit -m x"), self.SUB)

    def test_pathspec_commit(self):
        """`git commit <path>` stages its paths itself, at commit time."""
        self.assertNames(self.repo.run("git commit -m x sub/a.py"), self.SUB)

    def test_pathspec_commit_leaves_other_staged_files_out(self):
        """`git commit <path>` commits only that path; naming the rest is noise."""
        self.repo.write("other/y.py", "changed\n", at=NEW)
        self.repo.stage("other/y.py")
        self.assertNames(self.repo.run("git commit -m x sub/a.py"), self.SUB)

    def test_already_staged_file_still_counts_alongside_a_same_call_add(self):
        self.repo.write("other/y.py", "changed\n", at=NEW)
        self.repo.stage("other/y.py")
        output = self.repo.run("git add sub/a.py && git commit -m x")
        self.assertNames(output, "other/CLAUDE.md  <- other/y.py", self.SUB)

    def test_git_global_options_before_commit_are_still_a_commit(self):
        """`git -C dir commit` has no "git commit" substring at all."""
        self.repo.stage("sub/a.py")
        self.assertNames(self.repo.run("git -C sub commit -m x"), self.SUB)

    def test_things_that_merely_mention_git_commit_are_not_commits(self):
        """A false detection would name the staged change under the node."""
        self.repo.stage("sub/a.py")
        for command in (
            "git commit-tree HEAD^{tree} -m x",
            "git commit-graph write",
            'echo "git commit"',
            "grep -r 'git commit' .",
        ):
            with self.subTest(command=command):
                self.assertSilent(self.repo.run(command))

    def test_only_the_commits_own_all_flag_sweeps_tracked_files(self):
        """`-la` elsewhere in the command, or `-all` inside a message, is not `-a`.

        Nothing is staged, so the only way sub/a.py can be named is by wrongly
        reading the command as `git commit -a`. The last case is the control:
        a real `-am` cluster must still sweep it in.
        """
        for command in (
            "ls -la && git commit -m x",
            'git commit -m "fix -all"',
            "git commit --message=-a",
        ):
            with self.subTest(command=command):
                self.assertSilent(self.repo.run(command))
        self.assertNames(self.repo.run("git commit -am x"), self.SUB)


class MalformedInputTest(RepoTestCase):
    def test_malformed_events_exit_zero_silently(self):
        """A crashing hook surfaces a traceback on every Bash call it sees."""
        for stdin in (
            "null",
            "5",
            "[]",
            '"git commit"',
            '{"tool_name": "Bash", "tool_input": "git commit -m x"}',
            '{"tool_name": "Bash", "tool_input": {"command": 5}}',
            '{"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": 5}',
            '{"tool_name": "Bash", "tool_input": {"command": "git commit -m \'x"}}',
        ):
            with self.subTest(stdin=stdin):
                self.assertEqual(self.repo.invoke(stdin), "")
                self.assertEqual(self.repo.exit_code, 0, self.repo.stderr)


class Transcript:
    """A synthetic session transcript, appended to as a session would be."""

    def __init__(self, path, repo_root):
        self.path = Path(path)
        self.root = Path(repo_root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        self._n = 0

    def _add(self, *entries):
        with self.path.open("a") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def _tool(self, name, data, result, is_error):
        self._n += 1
        tid = f"t{self._n}"
        self._add(
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": tid, "name": name, "input": data}
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tid, "content": result,
                 "is_error": is_error}
            ]}},
        )

    def bash_error(self, command="make build --target x"):
        self._tool("Bash", {"command": command}, "Exit code 2\nboom", True)

    def correction(self, text="no, that's the wrong file"):
        self._n += 1
        self._add({"type": "user", "promptId": f"p{self._n}", "message": {"content": text}})

    def denial(self, tool="Write"):
        body = "The user doesn't want to proceed with this tool use. stop"
        self._tool(tool, {"file_path": str(self.root / "z.py")}, body, True)

    def edit(self, rel="src/app.py"):
        self._tool("Edit", {"file_path": str(self.root / rel)}, "ok", False)

    def red_pytest(self, test_id="tests/test_app.py::test_it"):
        self._tool(
            "Bash", {"command": "python3 -m pytest -q"},
            f"FAILED {test_id} - AssertionError\n1 failed", True,
        )

    def raw(self, *lines):
        with self.path.open("a") as handle:
            for line in lines:
                handle.write(line + "\n")


class HarvestTest(RepoTestCase):
    SESSION = "sess-1"

    def setUp(self):
        super().setUp()
        self.repo.write("README", at=OLD)
        self.repo.commit()
        self.transcript = Transcript(
            self.repo.home / ".claude" / "projects" / "slug" / f"{self.SESSION}.jsonl",
            self.repo.root,
        )

    def commit(self, command="git commit --amend --no-edit"):
        return self.repo.run(
            command,
            transcript_path=str(self.transcript.path),
            session_id=self.SESSION,
        )

    def harvested(self, output):
        return "signals of a recurring pitfall" in output

    def test_harvest_speaks_when_nothing_is_staged(self):
        """Harvest must not hide behind the node section's empty-index early return."""
        self.transcript.bash_error()
        self.transcript.bash_error()
        self.transcript.correction()
        self.transcript.correction()
        output = self.commit()
        self.assertTrue(self.harvested(output), f"expected a harvest, got {output!r}")

    def test_same_friction_does_not_refire_when_its_count_grows(self):
        """Dedupe keyed on "failed 2x" treats "failed 3x" as brand-new friction."""
        self.transcript.bash_error()
        self.transcript.bash_error()
        self.transcript.correction()
        self.transcript.correction()
        self.assertTrue(self.harvested(self.commit()))
        self.transcript.bash_error()
        self.transcript.correction()
        self.assertSilent(self.commit())

    def test_genuinely_new_friction_rearms(self):
        """Dedupe must not silence the rest of the session once it has fired."""
        self.transcript.bash_error()
        self.transcript.bash_error()
        self.transcript.correction()
        self.transcript.correction()
        self.assertTrue(self.harvested(self.commit()))
        self.transcript.denial()
        self.transcript.denial()
        for _ in range(6):
            self.transcript.edit()
        output = self.commit()
        self.assertTrue(self.harvested(output), f"expected a re-arm, got {output!r}")
        self.assertIn("denied", output)
        self.assertNotIn("errored", output)

    def test_a_failing_test_run_is_one_event_not_two(self):
        """Counting its non-zero exit too lets one red test clear a two-family bar."""
        self.transcript.red_pytest()
        self.transcript.edit()
        self.transcript.red_pytest()
        self.assertSilent(self.commit())

    def test_denying_a_plan_is_the_review_gate_not_friction(self):
        """Iterating on a plan was the largest source of false fires in replay."""
        for _ in range(3):
            self.transcript.denial("ExitPlanMode")
        self.transcript.correction()
        self.transcript.correction()
        self.assertSilent(self.commit())

    def test_malformed_transcript_lines_are_skipped_not_fatal(self):
        """A crash here would also take the node section down with it."""
        self.transcript.raw(
            "5",
            "[]",
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "q1", "name": "Edit", "input": "nope"},
                {"type": "tool_use", "id": "q2", "name": "Edit", "input": {"file_path": 7}},
                {"type": "tool_use", "id": ["q3"], "name": ["Bash"], "input": {"command": 7}},
            ]}}),
            json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": ["q3"], "content": [{"text": 5}],
                 "is_error": True},
                {"type": "tool_result", "tool_use_id": "q2", "content": "x", "is_error": True},
            ]}}),
        )
        self.transcript.bash_error()
        self.transcript.bash_error()
        self.transcript.correction()
        self.transcript.correction()
        output = self.commit()
        self.assertEqual(self.repo.exit_code, 0, self.repo.stderr)
        self.assertTrue(self.harvested(output), f"expected a harvest, got {output!r}")


class ReplayTest(RepoTestCase):
    def replay(self, *args):
        out = self.repo.invoke("", "--replay", *args)
        self.assertEqual(self.repo.exit_code, 0, self.repo.stderr)
        return json.loads(out)

    def test_replay_counts_commits_that_left_their_node_behind(self):
        self.repo.write("sub/CLAUDE.md", "# sub\n")
        self.repo.write("sub/a.py")
        self.repo.commit()
        self.repo.write("sub/a.py", "two\n")
        self.repo.commit()
        self.repo.write("sub/b.py", "three\n")
        self.repo.commit()
        result = self.replay()
        self.assertEqual(result["commits"], 3)
        self.assertEqual(result["fired"], 2)
        self.assertEqual(result["nodes"], {"sub/CLAUDE.md": 2})

    def test_replay_uses_the_hooks_root_rule(self):
        """A health check that disagreed with the hook would measure the wrong thing."""
        self.repo.write("deep/CLAUDE.md", "# deep\n")
        self.repo.write("deep/x.py")
        self.repo.commit()
        self.repo.write("top.py")
        self.repo.commit()
        result = self.replay()
        self.assertEqual((result["commits"], result["fired"]), (2, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
