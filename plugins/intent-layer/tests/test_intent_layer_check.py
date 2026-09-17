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

# Commands really run now, so they must run under the shell Claude Code's Bash
# tool uses — a command valid in zsh and rejected by sh is a difference the
# suite has to be able to see. Falls back to bash so this is not macOS-only.
SHELL = os.environ.get("SHELL") or "/bin/bash"

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

    def run(self, command="git commit -m x", cwd=None, response=None,
            event="PostToolUse", **fields):
        """Execute `command` for real, then hand the hook its PostToolUse payload.

        The command genuinely runs, so the commit the hook resolves is the one
        git actually made — the whole point of moving off PreToolUse.
        """
        where = str(cwd or self.root)
        proc = subprocess.run(
            command, shell=True, executable=SHELL, cwd=where,
            capture_output=True, text=True, check=False,
        )
        self.command_exit = proc.returncode
        body = proc.stdout + proc.stderr
        event_body = {
            "hook_event_name": event,
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": where,
            **fields,
        }
        # The two events carry the command's output in different fields, and
        # neither is the shape the docs describe. Captured from real payloads:
        # PostToolUse has tool_response and no error; PostToolUseFailure has
        # error and no tool_response at all.
        if response is not None:
            event_body["tool_response"] = response
        elif event == "PostToolUseFailure":
            event_body["error"] = f"Exit code {proc.returncode}\n{body}"
            event_body["is_interrupt"] = False
        else:
            event_body["tool_response"] = {
                "stdout": proc.stdout, "stderr": proc.stderr,
                "interrupted": False, "isImage": False, "noOutputExpected": False,
            }
        return self.invoke(json.dumps(event_body))

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
        self.emitted = payload["hookSpecificOutput"]
        return self.emitted["additionalContext"]


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


class CommitDetectionTest(RepoTestCase):
    """PostToolUse runs *after* the command, so the commit is a fact.

    Nothing here predicts what staging will do: the command really runs, and the
    hook resolves the commit git actually made. What is left to get wrong is
    *which* commit — or whether one happened at all.
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
        """The shape Claude uses most, resolved from git's own reported sha."""
        self.assertNames(self.repo.run("git add sub/a.py && git commit -m x"), self.SUB)

    def test_heredoc_message_is_no_longer_something_to_parse(self):
        """A multi-line message with an apostrophe, which used to break shlex.

        Failure mode: losing a commit because its *message* was unparseable.
        Post reads git's reported sha, so the body is never looked at.
        """
        command = (
            "git add sub/a.py && git commit -F - <<'EOF'\n"
            "fix: don't break it\n\nCo-Authored-By: x\nEOF\n"
        )
        self.assertNames(self.repo.run(command), self.SUB)

    def test_quiet_commit_prints_no_sha_and_still_fires(self):
        """`git commit -q` prints nothing at all.

        Failure mode: going silent on every quiet commit because detection
        depends on stdout that isn't there.
        """
        self.assertNames(self.repo.run("git add sub/a.py && git commit -q -m x"), self.SUB)

    def test_commit_that_lands_before_a_later_command_fails_still_fires(self):
        """The commit succeeded; the Bash call did not.

        Failure mode: a landed commit gets no reminder because the call exited
        non-zero and routed to PostToolUseFailure.
        """
        output = self.repo.run(
            "git add sub/a.py && git commit -m x && exit 9", event="PostToolUseFailure"
        )
        self.assertEqual(self.repo.command_exit, 9)
        self.assertNames(output, self.SUB)

    def test_failed_commit_says_nothing(self):
        """Nothing staged, so git refuses and no commit exists.

        Failure mode (the PreToolUse bug this move fixes): advising the model to
        update a node for a commit that never happened.
        """
        output = self.repo.run("git commit -m x", event="PostToolUseFailure")
        self.assertNotEqual(self.repo.command_exit, 0)
        self.assertSilent(output)

    def test_quiet_commit_that_failed_says_nothing(self):
        """No sha *and* nothing committed — the fallback must not reach for HEAD.

        Failure mode: falling back to HEAD whenever stdout lacks a sha, which
        would re-report the *previous* commit on every failed quiet commit.
        """
        self.repo.stage("sub/a.py")
        self.repo.git("commit", "-qm", "real")
        output = self.repo.run("git commit -q -m x", event="PostToolUseFailure")
        self.assertNotEqual(self.repo.command_exit, 0)
        self.assertSilent(output)

    def test_merge_commit_says_nothing(self):
        """Failure mode: double-reminding.

        A merge's own commits already fired the hook on the branch. Replay skips
        merges for the same reason, so firing here would also make the health
        check disagree with the hook.
        """
        self.repo.git("checkout", "-q", "-b", "side")
        self.repo.stage("sub/a.py")
        self.repo.git("commit", "-qm", "side work")
        self.repo.git("checkout", "-q", "-")
        self.repo.write("other/y.py", "changed\n", at=NEW)
        self.repo.commit("main work")
        self.assertSilent(self.repo.run("git merge --no-ff -m merge side"))

    def test_git_global_options_before_commit_are_still_a_commit(self):
        """`git -C dir commit` has no "git commit" substring at all."""
        self.repo.stage("sub/a.py")
        self.assertNames(self.repo.run("git -C sub commit -m x"), self.SUB)

    def test_things_that_merely_mention_git_commit_are_not_commits(self):
        """A false detection would name the last commit's files as if new."""
        self.repo.stage("sub/a.py")
        self.repo.git("commit", "-qm", "real")
        for command in (
            "git commit-tree HEAD^{tree} -m x",
            "git commit-graph write",
            'echo "git commit"',
            "grep -r 'git commit' . || true",
        ):
            with self.subTest(command=command):
                self.assertSilent(self.repo.run(command))

    def test_the_reminder_echoes_the_event_it_was_invoked_for(self):
        """Failure mode: additionalContext discarded for naming the wrong event."""
        for event in ("PostToolUse", "PostToolUseFailure"):
            with self.subTest(event=event):
                self.repo.write("sub/a.py", f"changed {event}\n", at=NEW)
                self.repo.run(f"git add sub/a.py && git commit -m {event}", event=event)
                self.assertEqual(self.repo.emitted["hookEventName"], event)


class ReminderWordingTest(RepoTestCase):
    """The commit already landed, so the instruction has to be reachable.

    Failure mode: telling the model to update the node "in this same commit"
    after the commit exists. The advice reads as satisfiable, so the update
    either lands as a separate commit or is skipped as impossible — and the node
    section's whole purpose is code and node arriving together.
    """

    def setUp(self):
        super().setUp()
        self.repo.write("sub/CLAUDE.md", "# sub\n", at=OLD)
        self.repo.write("sub/x.py", at=OLD)
        self.repo.commit()

    def test_a_committed_node_is_pointed_at_amend(self):
        self.repo.write("sub/x.py", "changed\n", at=NEW)
        output = self.repo.run("git add -A && git commit -m x")
        self.assertIn("--amend", output)
        self.assertNotIn("in this same commit", output)

    def test_a_local_node_is_not_told_to_beat_a_commit_that_happened(self):
        """A local node is gitignored, so no amend can carry it either.

        The instruction must still stop saying "before you commit", which by
        now names a moment that has passed.
        """
        self.repo.write("sub/CLAUDE.local.md", "# local\n", at=OLD)
        self.repo.write("sub/x.py", "changed\n", at=NEW)
        output = self.repo.run("git add -A && git commit -m x")
        self.assertIn("sub/CLAUDE.local.md", output)
        self.assertNotIn("before you commit", output)


class PayloadShapeTest(RepoTestCase):
    """`tool_response` for Bash is undocumented in shape, so accept several.

    Failure mode: the hook goes blind on every commit because the field arrived
    as a bare string, or a block list, where a dict was assumed. Each shape here
    carries the same real sha, so any shape the flattener drops goes silent.
    """

    def setUp(self):
        super().setUp()
        self.repo.write("sub/CLAUDE.md", "# sub\n", at=OLD)
        self.repo.write("sub/a.py", at=OLD)
        self.repo.commit()
        self.repo.write("sub/a.py", "changed\n", at=NEW)
        self.repo.stage("sub/a.py")
        result = self.repo.git("commit", "-m", "x")
        self.body = result.stdout + result.stderr
        self.assertIn("[", self.body, "git printed no summary line to parse")

    SUB = "sub/CLAUDE.md  <- sub/a.py"

    def event(self, response):
        return json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m x"},
            "tool_response": response,
            "cwd": str(self.repo.root),
        })

    def test_dict_with_text(self):
        self.assertNames(self.repo.invoke(self.event({"type": "text", "text": self.body})),
                         self.SUB)

    def test_bare_string(self):
        self.assertNames(self.repo.invoke(self.event(self.body)), self.SUB)

    def test_block_list(self):
        self.assertNames(
            self.repo.invoke(self.event([{"type": "text", "text": self.body}])), self.SUB
        )

    def test_split_stdout_stderr_fields(self):
        self.assertNames(
            self.repo.invoke(self.event({"stdout": self.body, "stderr": "", "exit_code": 0})),
            self.SUB,
        )

    def test_the_shape_bash_actually_sends(self):
        """Captured from a real PostToolUse payload, not from the docs."""
        self.assertNames(self.repo.invoke(self.event({
            "stdout": self.body, "stderr": "",
            "interrupted": False, "isImage": False, "noOutputExpected": False,
        })), self.SUB)

    def test_the_failure_events_shape_carries_no_tool_response_at_all(self):
        """PostToolUseFailure keeps the output in `error`, and omits the key.

        Failure mode: the second registration is dead code. Reading only
        `tool_response` finds nothing, the sha requirement rejects the event,
        and the `commit && later-failure` case it exists for never fires.
        """
        event = json.dumps({
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m x && exit 13"},
            "error": f"Exit code 13\n{self.body}",
            "is_interrupt": False,
            "cwd": str(self.repo.root),
        })
        self.assertNames(self.repo.invoke(event), self.SUB)

    def test_absent_tool_response_falls_back_to_head(self):
        """No response at all: the success event still means the commit landed."""
        self.assertNames(self.repo.invoke(self.event(None)), self.SUB)


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
