# ruff-gate

A ruff gate that travels. Install it once, globally, and every repo that lints with ruff gets a
per-edit check and a turn-level gate — while every repo that doesn't gets nothing at all.

The organizing principle: **a gate may only block you on work you are responsible for.** A gate that
reports inherited debt is one you learn to disable, and then you have no gate.

## Components

| Piece | What it does | When it costs anything |
|---|---|---|
| `lint` hook (PostToolUse) | Runs `ruff check` on the Python file just written, and records it as touched. | Only when that file has violations. |
| `gate` hook (Stop) | Runs `ruff check` and `ruff format --check` over the files the turn touched, and holds the turn open until they pass. | Only when something is unclean. |

Neither hook ever rewrites a file. Every report ends with the command that would.

## It is silent unless the repo asked

Applicability is decided by the repo, not by you remembering to configure it:

```
a ruff config above the edited file?   no  → exit 0, silently
                                       yes → .claude/ruff-gate.off, RUFF_GATE=off,
                                             or "enabled": false → exit 0
                                             otherwise            → run
```

"A ruff config" means `ruff.toml`, `.ruff.toml`, or a `pyproject.toml` containing a `[tool.ruff…]`
table, found by walking up from the file to the project root. The opt-out lives in the script because
Claude Code offers no way to switch off a single plugin hook from a project — `disableAllHooks` is
all-or-nothing.

## Configuration

Optional, at `.claude/ruff-gate.json` in the repo. Every key has a default; an unknown key or
malformed JSON is reported rather than silently ignored.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | `false` is the committed equivalent of the `.off` marker. |
| `scope` | `"session"` | `"session"` checks the files this turn touched. `"tree"` checks whole directories, inherited debt included. |
| `format` | `true` | `false` drops `ruff format --check`, keeping the lint check. |
| `dirs` | discovered | Directories for `scope: "tree"`. Discovery takes the root plus any depth-one subdirectory with its own ruff config. |
| `command` | probed | Pin the invocation, e.g. `["uv", "run", "ruff"]`. Probing prefers `uv run ruff` when it resolves, then `ruff` on `PATH`. |

Pinning `command` is worth doing in a uv project: `uv run ruff` and the `ruff` on `PATH` are often
different versions, and two versions disagree about formatting in ways neither run can settle.

## Two things about ruff that shaped this

Both were measured, and the second is widely assumed backwards:

1. **Ruff resolves configuration per file**, walking up from the file itself — rule *selection*
   included, and resolved rather than merged into the parent's. A subtree with its own stricter
   config is held to it no matter where ruff was invoked from.
2. **Excludes govern directory traversal and nothing else.** `extend-exclude = ["client"]` at the
   root makes `ruff check .` skip that directory, but `ruff check client/a.py` still lints it, under
   `client`'s own rules, even with `--force-exclude`.

Together these mean the default scope needs exactly one invocation at the project root with explicit
paths, and each file is still judged by the config that owns it. Only `scope: "tree"` needs a
directory list, because traversal is the only thing an exclude touches.

## Known limits

- **It sees the edit tools, not the filesystem.** A file changed by a `Bash` heredoc, `sed`, or a
  `git` operation is not recorded and will not be checked. Use `scope: "tree"` where that matters.
- **Ruff's own failures are silent, by design.** A missing binary, a bad flag, or an unparseable
  config makes ruff exit 2 or above; that is reported as nothing rather than as violations, because a
  broken toolchain rendered as lint errors is a wall of nonsense that invites fixing the wrong thing.
  If the gate has gone quiet where you expected it, check `ruff --version` first.
- **Discovery for `scope: "tree"` goes one level deep.** Anything deeper needs an explicit `dirs`.

## Session state

The touched-file list lives in `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json`, falling back to
`~/.claude/ruff-gate/`. Never inside the repo being checked — a gate has no business dirtying a
working tree it doesn't own. Entries older than seven days are swept, since an abandoned session
never reaches a Stop.

## Tests

```bash
python3 -m unittest discover -s plugins/ruff-gate/tests
```

Requires `python3` and `ruff` on `PATH`.
