"""Run with: python3 -m unittest discover -s plugins/permission-log/tests

Every test here names a way the logger could be wrong. The ones it exists for
above all: it must never answer the prompt it is watching (no stdout, always
exit 0), and it must never copy file contents or secrets into a plain-text log.
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(TESTS, "..", "hooks", "permission_log.py"))

_spec = importlib.util.spec_from_file_location("permission_log", SCRIPT)
permission_log = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(permission_log)

SENTINEL = "SENTINEL-must-not-be-logged"


def event(tool_name, tool_input):
    """Every field a PermissionRequest event carries, not just the ones read."""
    return {
        "session_id": "sess-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/work/repo",
        "permission_mode": "default",
        "hook_event_name": "PermissionRequest",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = os.path.join(self.tmp, "data")
        self.log = os.path.join(self.data, "permission-log.jsonl")

    def run_hook(self, stdin, **env):
        environ = dict(os.environ)
        environ["CLAUDE_PLUGIN_DATA"] = self.data
        environ.update(env)
        environ = {k: v for k, v in environ.items() if v is not None}
        done = subprocess.run(
            [sys.executable, SCRIPT],
            input=stdin,
            text=True,
            capture_output=True,
            env=environ,
            check=False,
        )
        return done.returncode, done.stdout, done.stderr

    def send(self, payload, **env):
        return self.run_hook(json.dumps(payload), **env)

    def lines(self, path=None):
        with open(path or self.log) as fh:
            return [json.loads(line) for line in fh]

    def only_line(self):
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        return lines[0]


class NeverAnswersThePrompt(HookCase):
    """Stdout JSON can allow or deny the request; a non-zero exit is a hook error."""

    def test_a_logged_bash_prompt_prints_nothing_and_exits_zero(self):
        result = self.send(event("Bash", {"command": "git push"}))
        self.assertEqual(result, (0, "", ""))
        self.assertTrue(os.path.exists(self.log), "must log, or this proves nothing")

    def test_malformed_stdin_exits_zero_silently(self):
        self.assertEqual(self.run_hook("{not json"), (0, "", ""))

    def test_empty_stdin_exits_zero_silently(self):
        self.assertEqual(self.run_hook(""), (0, "", ""))

    def test_a_json_array_exits_zero_silently(self):
        self.assertEqual(self.run_hook('["Bash"]'), (0, "", ""))

    def test_non_dict_tool_input_exits_zero_silently(self):
        self.assertEqual(self.send(event("Bash", ["ls"])), (0, "", ""))

    def test_an_unwritable_log_dir_exits_zero_silently(self):
        blocker = os.path.join(self.tmp, "a-file")
        with open(blocker, "w") as fh:
            fh.write("not a directory")
        payload = event("Bash", {"command": "ls"})
        self.assertEqual(self.send(payload, CLAUDE_PLUGIN_DATA=blocker), (0, "", ""))


class WhatALineRecords(HookCase):
    def test_line_carries_session_cwd_tool_and_a_utc_timestamp(self):
        self.send(event("Bash", {"command": "git push"}))
        line = self.only_line()
        self.assertEqual(line["session_id"], "sess-1")
        self.assertEqual(line["cwd"], "/work/repo")
        self.assertEqual(line["tool_name"], "Bash")
        self.assertEqual(line["summary"], "git push")
        self.assertRegex(line["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")

    def test_line_records_which_event_and_permission_mode_produced_it(self):
        # An auto-mode ask-rule prompt and a default-mode prompt audit differently.
        payload = dict(event("Bash", {"command": "kill -0 1"}), permission_mode="auto")
        self.send(payload)
        line = self.only_line()
        self.assertEqual(
            (line["event"], line["permission_mode"]), ("PermissionRequest", "auto")
        )

    def test_an_auto_mode_denial_is_logged_as_its_own_event(self):
        # Auto mode blocks without a prompt; that is oversight the log must show.
        payload = dict(
            event("Bash", {"command": "rm -rf build"}),
            hook_event_name="PermissionDenied",
            permission_mode="auto",
        )
        self.send(payload)
        line = self.only_line()
        self.assertEqual(
            (line["event"], line["summary"]), ("PermissionDenied", "rm -rf build")
        )

    def test_the_log_is_readable_only_by_its_owner(self):
        # Commands can carry secrets the patterns miss; other users must not read them.
        self.send(event("Bash", {"command": "ls"}))
        self.assertEqual(os.stat(self.log).st_mode & 0o777, 0o600)

    def test_each_prompt_appends_rather_than_overwrites(self):
        self.send(event("Bash", {"command": "first"}))
        self.send(event("Bash", {"command": "second"}))
        self.assertEqual([x["summary"] for x in self.lines()], ["first", "second"])

    def test_missing_fields_still_log_a_line(self):
        # A prompt still happened; dropping it would undercount.
        self.send({"hook_event_name": "PermissionRequest"})
        line = self.only_line()
        self.assertIsNone(line["tool_name"])
        self.assertIsNone(line["session_id"])

    def test_a_non_dict_tool_input_still_logs_the_tool(self):
        # The broad except would otherwise swallow this and drop the line.
        self.send(event("mcp__x__y", ["positional"]))
        line = self.only_line()
        self.assertEqual((line["tool_name"], line["summary"]), ("mcp__x__y", []))

    def test_fallback_path_under_home_when_plugin_data_is_unset(self):
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        self.send(event("Bash", {"command": "ls"}), CLAUDE_PLUGIN_DATA=None, HOME=home)
        fallback = os.path.join(
            home, ".claude", "permission-log", "permission-log.jsonl"
        )
        self.assertEqual([x["summary"] for x in self.lines(fallback)], ["ls"])


class NoFileContents(HookCase):
    """A log of prompts must not become a second copy of every file written."""

    def assert_only_path_logged(self, tool_name, tool_input, path):
        self.send(event(tool_name, tool_input))
        with open(self.log) as fh:
            self.assertNotIn(SENTINEL, fh.read())
        self.assertEqual(self.only_line()["summary"], path)

    def test_write_logs_the_path_not_the_content(self):
        self.assert_only_path_logged(
            "Write", {"file_path": "/r/a.py", "content": SENTINEL}, "/r/a.py"
        )

    def test_edit_logs_the_path_not_the_strings(self):
        tool_input = {
            "file_path": "/r/a.py",
            "old_string": SENTINEL,
            "new_string": SENTINEL,
            "replace_all": False,
        }
        self.assert_only_path_logged("Edit", tool_input, "/r/a.py")

    def test_multiedit_logs_the_path_not_the_edits(self):
        tool_input = {
            "file_path": "/r/a.py",
            "edits": [{"old_string": SENTINEL, "new_string": SENTINEL}],
        }
        self.assert_only_path_logged("MultiEdit", tool_input, "/r/a.py")

    def test_notebook_edit_logs_the_notebook_path_not_the_source(self):
        tool_input = {"notebook_path": "/r/n.ipynb", "new_source": SENTINEL}
        self.assert_only_path_logged("NotebookEdit", tool_input, "/r/n.ipynb")

    def test_read_logs_the_path(self):
        self.assert_only_path_logged("Read", {"file_path": "/r/.env"}, "/r/.env")

    def test_unknown_tool_logs_its_keys_never_its_values(self):
        tool_input = {"customer": SENTINEL, "amount": 500}
        self.send(event("mcp__stripe__create_refund", tool_input))
        with open(self.log) as fh:
            self.assertNotIn(SENTINEL, fh.read())
        self.assertEqual(self.only_line()["summary"], ["amount", "customer"])

    def test_webfetch_logs_the_url(self):
        tool_input = {"url": "https://example.com/doc", "prompt": SENTINEL}
        self.assert_only_path_logged("WebFetch", tool_input, "https://example.com/doc")


class BashSummary(HookCase):
    def summary_of(self, command):
        self.send(event("Bash", {"command": command}))
        return self.only_line()["summary"]

    def test_assigned_secrets_are_redacted(self):
        self.assertEqual(
            self.summary_of("API_TOKEN=abc123 DB_PASSWORD=hunter2 make deploy"),
            "API_TOKEN=<redacted> DB_PASSWORD=<redacted> make deploy",
        )

    def test_a_quoted_secret_with_spaces_is_redacted_whole(self):
        # \S+ alone would stop at the space and leak "horse battery'".
        self.assertEqual(
            self.summary_of("export SECRET_KEY='correct horse battery' && run"),
            "export SECRET_KEY=<redacted> && run",
        )

    def test_a_bearer_token_is_redacted(self):
        self.assertEqual(
            self.summary_of('curl -H "Authorization: Bearer eyJhbGci.x.y" https://a'),
            'curl -H "Authorization: Bearer <redacted>" https://a',
        )

    def test_a_keychain_password_argument_is_redacted(self):
        self.assertEqual(
            self.summary_of("security add-generic-password -s svc -a me -w hunter2"),
            "security add-generic-password -s svc -a me -w <redacted>",
        )

    def test_a_curl_basic_auth_password_is_redacted_but_the_user_kept(self):
        self.assertEqual(
            self.summary_of("curl -u alice:s3cret https://a"),
            "curl -u alice:<redacted> https://a",
        )

    def test_a_basic_authorization_header_is_redacted(self):
        self.assertEqual(
            self.summary_of(
                'curl -H "Authorization: Basic YWxpY2U6czNjcmV0" https://a'
            ),
            'curl -H "Authorization: Basic <redacted>" https://a',
        )

    def test_a_space_separated_password_flag_is_redacted(self):
        self.assertEqual(
            self.summary_of("mysql --password hunter2 -h db"),
            "mysql --password <redacted> -h db",
        )

    def test_a_secret_in_a_fetched_url_query_is_redacted(self):
        self.send(event("WebFetch", {"url": "https://a.io/x?api_key=zzz"}))
        self.assertEqual(
            self.only_line()["summary"], "https://a.io/x?api_key=<redacted>"
        )

    def test_a_long_command_is_cut_to_300_characters(self):
        self.assertEqual(self.summary_of("a" * 400), "a" * 300)

    def test_a_secret_straddling_the_cut_is_still_redacted(self):
        # Redacting after the cut would leave the secret's head behind.
        command = "x" * 290 + " TOKEN=" + "s" * 50
        self.assertEqual(self.summary_of(command), "x" * 290 + " TOKEN=<re")

    def test_a_non_string_command_does_not_crash_the_line(self):
        self.send(event("Bash", {"command": None}))
        self.assertEqual(self.only_line()["summary"], "")


class Rotation(unittest.TestCase):
    """Driven in-process so the threshold can shrink from 5 MB to a few bytes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = os.path.join(self.tmp, "permission-log.jsonl")
        self.old = self.log + ".1"

    def fire(self, command):
        stdin = io.StringIO(json.dumps(event("Bash", {"command": command})))
        with (
            mock.patch.object(permission_log, "MAX_BYTES", 100),
            mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self.tmp}),
            mock.patch("sys.stdin", stdin),
        ):
            self.assertEqual(permission_log.main(), 0)

    def seed(self, path, size):
        with open(path, "w") as fh:
            fh.write("o" * (size - 1) + "\n")

    def summaries(self, path):
        with open(path) as fh:
            return [json.loads(line)["summary"] for line in fh]

    def test_a_log_over_the_threshold_moves_aside_before_appending(self):
        self.seed(self.log, 101)
        self.fire("new")
        with open(self.old) as fh:
            self.assertEqual(fh.read(), "o" * 100 + "\n")
        self.assertEqual(self.summaries(self.log), ["new"])

    def test_a_previous_rotation_is_replaced_not_kept(self):
        with open(self.old, "w") as fh:
            fh.write("oldest\n")
        self.seed(self.log, 101)
        self.fire("new")
        with open(self.old) as fh:
            self.assertEqual(fh.read(), "o" * 100 + "\n")

    def test_a_log_at_the_threshold_is_appended_to(self):
        self.seed(self.log, 100)
        self.fire("new")
        self.assertFalse(os.path.exists(self.old))
        with open(self.log) as fh:
            self.assertEqual(fh.read().count("\n"), 2)


if __name__ == "__main__":
    unittest.main()
