# permission-log

A tally of your permission prompts. Every time Claude Code asks you to approve a tool call — or, in
auto mode, blocks one without asking — this appends one JSON line saying which tool, in which
session, mode, and directory, aimed at what. After a week
you can count which calls keep asking and decide what belongs in your allowlist, based on data
instead of memory.

The organizing principle: **an observer must never become a participant.** The hook that sees a
permission prompt is also allowed to answer it, so this one is built to have no way of doing so.

## What a line looks like

```json
{"ts": "2026-09-29T17:40:00Z", "event": "PermissionRequest", "permission_mode": "auto", "session_id": "…", "cwd": "/work/repo", "tool_name": "Bash", "summary": "git push origin main"}
```

| Field | Content |
|---|---|
| `ts` | UTC, ISO-8601, to the second. |
| `event` | `PermissionRequest` (you were asked) or `PermissionDenied` (auto mode blocked it without asking). |
| `permission_mode`, `session_id`, `cwd`, `tool_name` | Copied from the event; `null` when the event lacks one. |
| `summary` | Depends on the tool, below. |

| Tool | `summary` |
|---|---|
| `Bash` | The command, secrets redacted, cut to 300 characters. |
| `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `Read` | The file path only. |
| `WebFetch` | The URL, redacted and cut the same way as a command. |
| Anything else (MCP tools included) | The sorted list of `tool_input` **keys**. Never the values. |

Redaction rewrites `NAME=value` to `NAME=<redacted>` whenever `NAME` contains `token`, `secret`,
`key`, or `password` (any case, quoted values matched whole); the value after a `--…password`,
`--…token`, or `--…secret` flag; `security …-generic-password … -w <x>`; the password half of
`curl -u user:pass`; and `Bearer <x>` / `Basic <x>`. It runs before the 300-character cut, so a
secret straddling the cut can't leave its head behind. The log file is created owner-only (0600).

## Where it goes

`${CLAUDE_PLUGIN_DATA}/permission-log.jsonl`, which under a marketplace install is
`~/.claude/plugins/data/permission-log-jjc-claude-skills/permission-log.jsonl`. When that variable is
unset, it falls back to `~/.claude/permission-log/permission-log.jsonl`. Never inside a repo.
Claude Code deletes the plugin data directory when you uninstall, so copy the log out first if you
want to keep it. When the file passes 5 MB, it
is renamed to `permission-log.jsonl.1` (replacing any earlier `.1`) and a fresh file starts, so the
log holds at most about 10 MB.

## The safety contract

On a `PermissionRequest` hook, a `decision` object in stdout JSON allows or denies the request. Exit
code 2 is *not* honored for this event, but any non-zero exit is reported as a hook error on the
prompt. So the script:

- **writes nothing to stdout or stderr**, on any path;
- **always exits 0**: malformed or empty stdin, a non-object payload, an unwritable log directory,
  and any unexpected exception all end in a silent exit 0. A lost log line is cheap; a hook that
  answers prompts, or clutters every one with an error, is not.

Each point is a test in `tests/test_permission_log.py`.

## Reading it

Set `LOG` to the file first. `CLAUDE_PLUGIN_DATA` is set only inside the hook, not in your shell; if
the path above doesn't match, `find ~/.claude -name permission-log.jsonl` will locate the file.

```bash
# prompts by tool
jq -r '.tool_name' "$LOG" | sort | uniq -c | sort -rn

# Bash prompts by first word of the command
jq -r 'select(.tool_name == "Bash") | .summary | split(" ")[0]' "$LOG" | sort | uniq -c | sort -rn
```

Without `jq`:

```bash
python3 -c 'import collections,json,sys; rows=[json.loads(l) for l in open(sys.argv[1])]; print(collections.Counter(r["tool_name"] for r in rows).most_common()); print(collections.Counter(r["summary"].split(" ")[0] for r in rows if r["tool_name"]=="Bash").most_common())' "$LOG"
```

The first word is a rough grouping: `cd x && git push` counts as `cd`, and a leading
`TOKEN=<redacted>` assignment counts as itself.

## Known limits

- **It sees what reached you, not what was waved through.** `PermissionRequest` fires whenever a
  prompt is shown — including in `auto` mode when an `ask` rule forces one (verified live: the event
  arrives with `permission_mode: "auto"`). A call an allow rule, the auto-mode classifier, or a
  `PreToolUse` hook approved silently never prompted, so it isn't logged; neither is anything under
  `dontAsk` or `bypassPermissions`. An auto-mode classifier *denial* fires `PermissionDenied`
  instead, and is logged with that `event`.
- **It records the prompt, not your answer.** The event fires before you choose, and nothing later
  reports the choice back, so a line means "this asked", not "this was approved" or "denied".
- **Redaction is a pattern, not a guarantee.** It catches the shapes listed above. A secret passed
  as a short flag (`-p hunter2`), inside a JSON body, or under a name without one of the trigger
  words goes into the log as written. The log is owner-only, but treat it like shell history.
- **Registration happens at session start.** `hooks.json` is read once when a session begins, so an
  install or update needs a restart before it logs anything; edits to the script apply on the next
  call.
- **The installed copy is the last pushed commit.** A marketplace install runs a cached copy of the
  repo as of its last push, not your working tree.

## Tests

```bash
python3 -m unittest discover -s plugins/permission-log/tests
```

Requires `python3` only. The payloads are hand-built, so the suite can pass against an event shape
Claude Code doesn't actually send: after an install, trigger one real prompt and check that a line
appears.
