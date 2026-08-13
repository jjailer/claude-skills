# claude-skills

Personal Claude Code plugins, shared across my projects and with anyone contributing to them.

## Install

```bash
/plugin marketplace add jjailer/claude-skills
/plugin install intent-layer@jjc-claude-skills
/plugin install ruff-gate@jjc-claude-skills
```

## Plugins

### `intent-layer`

Keeps `CLAUDE.md` intent-layer nodes honest — the hierarchy of `CLAUDE.md` files that carries
contracts, traps, and the sanctioned choice alongside the code. A node carries only what a capable
model cannot re-derive from the source.

- **`intent-layer` skill** — the doctrine. Where a node belongs, what earns a line in one, how hard
  to compress, and when to delete.
- **`harvest-pitfalls` skill** — the triage. What a real pitfall looks like, and whether it belongs
  in a node, a path-scoped rule, a skill, or a hook.
- **Commit-time hook** — the trigger. On `git commit`, it reports nodes whose code changed without
  them, and flags a session showing signs of a recurring pitfall.
- **`/harvest-pitfalls`, `/audit-intent-layer`** — manual harvest, and an on-demand sweep for drift
  the commit hook can't see.

Both triggers are built to stay quiet: the node reminder spoke on 2 commits in 8 replayed over a
14-node repo's history, and the pitfall harvest needs two independent signals of real friction before
it says anything. Requires `python3` on `PATH`.

Full detail and credit for the original concept: [`plugins/intent-layer/README.md`](plugins/intent-layer/README.md).

### `ruff-gate`

Carries a ruff lint and format gate between repos. Install it once, globally: every repo that lints
with ruff gets a per-edit check and a turn-level gate, and every repo that doesn't gets nothing.

- **Per-edit hook** — `ruff check` on the Python file just written.
- **Stop hook** — `ruff check` and `ruff format --check` over the files the turn touched, holding the
  turn open until they pass. Never rewrites a file; it reports the command that would.
- **Silent unless the repo asked** — applicability is a ruff config found above the edited file, so
  the gate costs nothing in repos that don't lint with ruff. `.claude/ruff-gate.off`, `RUFF_GATE=off`,
  or `"enabled": false` switches it off where one exists.
- **Optional `.claude/ruff-gate.json`** — pin the ruff invocation, check whole directories instead of
  touched files, or drop the format check.

The governing rule is that a gate may only block you on work you are responsible for: by default it
checks what the turn touched, never the repo's pre-existing debt. Requires `python3` and `ruff`.

Full detail, configuration, and known limits: [`plugins/ruff-gate/README.md`](plugins/ruff-gate/README.md).
