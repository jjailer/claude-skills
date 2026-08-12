# claude-skills

Personal Claude Code plugins, shared across my projects and with anyone contributing to them.

## Install

```bash
/plugin marketplace add jjailer/claude-skills
/plugin install intent-layer@jjc-claude-skills
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
