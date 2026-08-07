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
contracts, patterns, and pitfalls alongside the code.

Two pieces that work together:

- **`intent-layer` skill** — the doctrine. Where a node belongs, what earns a line in one, how hard
  to compress, and when to delete. Loads on demand when you create, edit, or audit a `CLAUDE.md`, so
  it costs nothing the rest of the time. Invoke manually with `/intent-layer`.
- **Commit-time hook** — the trigger. On `git commit`, it reports any node whose directory has
  changed code that the same commit doesn't touch.

The hook is built to stay quiet. It says nothing when a commit updates code and its node together,
nothing when the change sits under no node, and nothing about the repo root unless a top-level file
changed — a root node nominally sits above everything, and a reminder that always fires is one you
learn to ignore. Replayed over a 14-node repo's history it spoke on 2 commits in 8.

Requires `python3` on `PATH`.
