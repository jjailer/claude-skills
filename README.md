# claude-skills

Personal Claude Code plugins, shared across my projects and with anyone contributing to them.

> [!WARNING]
> **This is a personal tool first.** It is shaped around how I work, and I change it whenever my
> habits change. Hook thresholds, skill wording, command names, and whole plugins can move, be
> renamed, or disappear — without notice, a deprecation window, or a migration note. There is no
> stability promise and no support commitment. You are welcome to use it; just size your
> expectations to that.
>
> **Nothing updates under you.** An installed plugin stays at the version you fetched until you
> update it yourself from the `/plugin` menu, so a breaking change here can't reach a machine that
> hasn't asked for it. If you want a stronger guarantee than "you choose when", fork it — every
> plugin here is small, and a fork you control beats a dependency I might rewrite on a Tuesday.

## Install

```bash
/plugin marketplace add jjailer/claude-skills
/plugin install intent-layer@jjc-claude-skills
/plugin install ruff-gate@jjc-claude-skills
/plugin install permission-log@jjc-claude-skills
/plugin install tdd@jjc-claude-skills
/plugin install commit-gate@jjc-claude-skills
```

## Plugins

### `intent-layer`

Keeps `CLAUDE.md` intent-layer nodes honest — the hierarchy of `CLAUDE.md` files that carries
contracts, traps, and the sanctioned choice alongside the code. A node carries only what a capable
model cannot re-derive from the source.

- **`/intent-layer:capturing-intent-layer [path]`** — the build. Establishes a layer on a repo that has none by
  interviewing you leaf-first, because the facts worth writing down are the ones only a person holds.
  Asks up front whether the repo's `CLAUDE.md` files are yours to commit; if they aren't, the layer
  lands in gitignored `CLAUDE.local.md` and supplements them.
- **`intent-layer` skill** — the doctrine. Where a node belongs, what earns a line in one, where a
  rule goes when a node isn't the answer, how hard to compress, and when to delete.
- **`/intent-layer:auditing-intent-layer [path]`** — the sweep, for drift the commit hook can't see. Both node variants enumerated, one reader per node,
  verdicts reported without editing.
- **`/intent-layer:harvesting-pitfalls [focus]`** — the triage. What a real pitfall looks like, and whether it
  belongs in a node, a path-scoped rule, a skill, or a hook.
- **Commit-time hook** — the trigger. On `git commit`, it reports nodes whose code changed without
  them, and flags a session showing signs of a recurring pitfall.

Both triggers are built to stay quiet: the node reminder spoke on 2 commits in 8 replayed over a
14-node repo's history, and the pitfall harvest needs two independent signals of real friction before
it says anything. Requires `python3` on `PATH`.

Full detail: [`plugins/intent-layer/README.md`](plugins/intent-layer/README.md).

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

### `permission-log`

A tally of your permission prompts. Every time Claude Code asks you to approve a tool call, or auto
mode blocks one, it appends one JSON line (event, mode, tool, session, directory, and a short
summary) to a local log, so you can count which calls keep asking and tune your allowlist from data
instead of memory.

- **Observes only.** It writes nothing to stdout and always exits 0, so it can never answer, deny,
  or add an error to the prompt it records.
- **Records where, not what.** Bash commands are redacted (`TOKEN=…`, `Bearer …`) and cut to 300
  characters. File tools log the path only, and other tools log their input *keys* only.
- **Counts prompts, not answers.** The event fires before you choose, so approve and deny aren't
  recorded. Calls approved silently (allow rules, the auto-mode classifier) never prompted and
  aren't logged; auto-mode denials are, as `PermissionDenied`.

```bash
jq -r '.tool_name' ~/.claude/plugins/data/permission-log-jjc-claude-skills/permission-log.jsonl | sort | uniq -c | sort -rn
```

Requires `python3`. Full detail, the log format, and known limits:
[`plugins/permission-log/README.md`](plugins/permission-log/README.md).

### `tdd`

Test-driven development calibrated to risk. Before writing a test, Claude picks a tier: **None**
(copy, config, presentation), **Regression** (one red test, the default), **Full** (money,
encryption, persisted data, concurrency, contracts), or **Refactor** (existing tests unedited).
The red-green-refactor loop then runs at that tier's rigor.

- **`tdd` skill** (`/tdd:tdd`): the tiers, the loop, naming the break a test catches, deriving
  expected values independently, where to put mocks, and a pre-done mutation check.

A workflow skill in your repo can route each issue type to a tier and link here for everything
else. No hooks; nothing runs.

Full detail: [`plugins/tdd/README.md`](plugins/tdd/README.md).

### `commit-gate`

Refuses `git commit` until your latest prompt approves one. A "go", "yes" or "commit it" since your
last prompt lets commits through. Any later prompt replaces it, and an edit-tool edit after a landed
commit asks for a fresh go. The review pause stops being something the agent has to remember.

- **Reads the prompt, not the transcript.** It hooks `prompt.submit` and `tool.call` in Claude
  Code's function-hook (mod) API, so it knows your last words without parsing a file. Background
  task notices and other sessions' messages never count as you.
- **A backstop, not a sandbox.** It string-matches `git … commit` in Bash commands. `bash -c`, a
  script or an alias gets past it.
- **Shows when it's waiting.** The status line reads `awaiting go` while the tree is dirty and
  nothing approves a commit.

The mod API is early access, so a Claude Code release can break it; `claude plugin test` runs its
suite against your installed engine. Full detail: [`plugins/commit-gate/README.md`](plugins/commit-gate/README.md).

## What this runs on your machine

Hooks execute on your machine with your permissions, so it's fair to want the list before installing:

- **No network.** No plugin here makes an HTTP call, sends telemetry, or reports anything anywhere.
  Everything is local `python3` and `git`, plus `commit-gate`'s in-process hooks module.
- **No writes to your repo.** `ruff-gate` never rewrites a file — it prints the `ruff` command that
  would. `intent-layer` only reports; the reminder and the harvest are text, not edits. `commit-gate`
  only refuses a commit and runs `git status`; its state lives in memory for the session.
- **It reads your session transcript.** The `intent-layer` commit hook scans this session's
  transcript under `~/.claude/projects/` to spot signs of a recurring pitfall, and keeps a small
  per-session state file under `~/.claude` so it speaks once instead of once per commit. That state
  lives outside your repo deliberately, so a harvest can never turn up in `git status`.
- **It writes a local log of your permission prompts.** `permission-log` appends one line per prompt
  to a file in its plugin data directory under `~/.claude`: the tool name, session id, working
  directory, and a redacted summary (a command, a file path, or input keys, never file contents).
  Nothing leaves your machine, and the file rotates at 5 MB.

## Backing out

- **Silence one gate:** `ruff-gate` respects `.claude/ruff-gate.off`, `RUFF_GATE=off`, and
  `"enabled": false` in `.claude/ruff-gate.json`. It is already silent in any repo with no ruff
  config.
- **Remove a plugin:** `/plugin uninstall intent-layer@jjc-claude-skills` (same shape for
  `ruff-gate`).
- **Remove the source:** `/plugin marketplace remove jjc-claude-skills`.

Uninstalling takes the hooks with it, and leaves nothing behind in your repos. The only residue is
the per-session state files under `~/.claude`, which expire on their own, and the `permission-log`
log, which Claude Code deletes with the plugin's data directory on uninstall.

## Credit

The Intent Layer concept originates with **Tyler Brandt at Intent Systems** —
[The Intent Layer](https://intent-systems.com/blog/intent-layer). The `intent-layer` plugin is an
independent implementation of that idea for Claude Code; any opinion in it that the original doesn't
hold is mine, not theirs.

## Developing

Keep the released plugins installed, and load your working tree over them for one session:

```bash
claude --plugin-dir ~/path/to/claude-skills/plugins
```

Every plugin under `plugins/` loads from disk as `<name>@inline` and replaces the installed copy of
the same name for that session only; every other session keeps running the release. Hook scripts
are re-read on each call, and `/reload-plugins` picks up changes to `hooks.json`, skills, and
manifests. The replacement is silent: `claude plugin list` still shows the marketplace copy as
enabled, so check `/plugin` for the `@inline` rows. Run `claude plugin validate plugins/<name>`
before pushing.

Don't `claude plugin marketplace add` a local checkout of this repo — it registers under the same
`jjc-claude-skills` name and replaces the GitHub marketplace on your machine.

## Contributing

Issues and PRs are welcome, and I'd rather hear that a hook was noisy than have you disable it
quietly — a gate that fires when it shouldn't is a bug worth reporting. That said, this is a
side-of-desk repo: replies may be slow, and I may decline a change that's right for your workflow
but wrong for the one this is built around. No hard feelings either way, and forking is always a
good answer.

## License

MIT — see [`LICENSE`](LICENSE). Use it, fork it, ship it inside something else; just keep the
copyright notice. The warranty disclaimer is the legal form of the warning at the top: this runs
hooks on your machine, and it comes with no guarantee that it won't get in your way.
