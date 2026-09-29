#!/usr/bin/env python3
"""Append one JSON line per permission prompt or auto-mode denial; never influence either.

A PermissionRequest hook can answer the prompt it observes: a decision object
in stdout JSON allows or denies it. A logger must never do that, so this script
writes nothing to stdout or stderr, and it exits 0 on every path, failures
included, because any other exit shows up as a hook error on the prompt it
was only meant to watch. A lost log line is cheap; noise on every prompt is not.

The log is plain text that outlives the session, so it records where a tool
pointed and never what it carried: a path for file tools, keys for unknown
tools, and a redacted, truncated command for Bash.
"""

import datetime
import json
import os
import re
import sys

MAX_BYTES = 5 * 1024 * 1024
SUMMARY_CHARS = 300
LOG_NAME = "permission-log.jsonl"
PATH_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit", "Read"})

# A quoted value is matched whole; \S+ alone would stop at the first space
# inside it and leak the rest.
ASSIGNED_SECRET = re.compile(
    r"""(?i)\b(\w*(?:token|secret|key|password)\w*)=("[^"]*"|'[^']*'|\S+)"""
)
AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[^\s\"']+")
KEYCHAIN_PASSWORD = re.compile(
    r"(\bsecurity\s+\S+-generic-password\b[^;&|\n]*?\s-w\s+)\S+"
)
CURL_USER_PASSWORD = re.compile(r"(\s-u\s+[^\s:]+:)\S+")
PASSWORD_FLAG = re.compile(r"(?i)(--\w*(?:password|token|secret)\w*\s+)(?!-)\S+")


def log_path():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser(
        "~/.claude/permission-log"
    )
    return os.path.join(base, LOG_NAME)


def redact(text):
    text = ASSIGNED_SECRET.sub(r"\1=<redacted>", text)
    text = KEYCHAIN_PASSWORD.sub(r"\1<redacted>", text)
    text = CURL_USER_PASSWORD.sub(r"\1<redacted>", text)
    text = PASSWORD_FLAG.sub(r"\1<redacted>", text)
    return AUTH_SCHEME.sub(r"\1 <redacted>", text)


def clip(text):
    """Redacted before the cut, so a secret straddling it can't leave its head."""
    return redact(text if isinstance(text, str) else "")[:SUMMARY_CHARS]


def summarize(tool_name, tool_input):
    if tool_name == "Bash":
        return clip(tool_input.get("command"))
    if tool_name in PATH_TOOLS:
        return tool_input.get("file_path") or tool_input.get("notebook_path")
    if tool_name == "WebFetch":
        return clip(tool_input.get("url"))
    return sorted(str(key) for key in tool_input)


def record(event):
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event.get("hook_event_name"),
        "permission_mode": event.get("permission_mode"),
        "session_id": event.get("session_id"),
        "cwd": event.get("cwd"),
        "tool_name": tool_name,
        "summary": summarize(tool_name, tool_input),
    }


def append(path, line):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if os.path.getsize(path) > MAX_BYTES:
            os.replace(path, path + ".1")
    except FileNotFoundError:
        pass
    # Owner-only: a command can carry a secret the patterns above miss.
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as fh:
        fh.write(line + "\n")


def main():
    # Broad on purpose: an uncaught exception exits 1 with a traceback, which
    # Claude Code reports as a hook error on a prompt this hook only watches.
    try:
        try:
            event = json.load(sys.stdin)
        except ValueError:
            event = {}
        if not isinstance(event, dict):
            event = {}
        append(log_path(), json.dumps(record(event)))
    except Exception:  # noqa: BLE001, S110
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
