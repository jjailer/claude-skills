---
name: intent-layer
description: Authoring, auditing, and pruning CLAUDE.md intent-layer nodes — where a node belongs, what earns a line in one, how hard to compress, and when to delete. Use when creating a new CLAUDE.md, editing or reviewing an existing one, deciding whether a rule belongs in a node vs a path-scoped rule vs a skill vs a hook, or when a commit changed contracts, traps, or dependencies that a node describes. Triggers on "add a CLAUDE.md", "create a node", "update the intent layer", "audit the CLAUDE.md files", "prune this node", "does this belong in CLAUDE.md", "the intent layer is stale", and on any commit touching code under a directory that has a CLAUDE.md.
---

# Intent layer

The Intent Layer is a hierarchy of `CLAUDE.md` nodes at semantic boundaries carrying what a capable
model **cannot re-derive from the code**: contracts, traps, and the sanctioned choice. The goal is
progressive disclosure — high-level context first, deeper detail behind links.

Three facts set every rule below.

| Fact | Consequence |
|---|---|
| **Load** — nodes *above* the working directory load in full at launch. A subtree node loads only when Claude reads a file under it, and is not re-injected after `/compact`. | A leaf node costs less than a root node and is less reliable — it can vanish mid-session. Anything that must always hold belongs higher up. |
| **Advisory** — a node is context delivered as a user message, not enforced configuration. There is no guarantee of compliance. | A rule that *must* hold is not a wording problem. It is a hook. |
| **Derivable** — the WHAT is searchable. | Spend the budget on the WHAT NOT and the WHY. |

## The three tiers

| Tier | Loads | Owns |
|---|---|---|
| `CLAUDE.md` node | ancestors at launch, subtree on read | non-derivable invariants, contracts, traps |
| `.claude/rules/*.md`, no frontmatter | at launch, same priority as `.claude/CLAUDE.md` | a long root node's topics split into files — organization, without changing what loads |
| `.claude/rules/*.md` with `paths:` frontmatter | when Claude reads a matching file | rules that glob across the tree rather than belonging to one directory |
| Skill | on demand | repeatable procedures |

**Two more node locations.** `CLAUDE.local.md` at the project root loads right after `CLAUDE.md` and
is gitignored — a personal preference belongs there, not in the team's node. The managed-policy node
(`/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS) loads before everything and cannot be
excluded; you read it, you don't author it. And an ancestor node that loads but doesn't apply — the
monorepo case — is a settings problem, not a writing one: `claudeMdExcludes` in
`.claude/settings.local.json` drops it by glob.

**Escalation.** A rule Claude ignores under pressure is not a wording problem — write a `PreToolUse`
hook. Anthropic: *"To block an action regardless of what Claude decides, use a PreToolUse hook
instead."* Emphasis is not the escalation path. `IMPORTANT` on a load-bearing line the first time it
is written does buy adherence; adding it to a line already being ignored buys nothing, and if every
rule is important then none are.

`paths:` scoping has known gaps — reported loading globally, and firing on Read but not Write. Confirm
it actually fires before putting something load-bearing behind it.

## Where nodes live

- Place them at **semantic boundaries** — where responsibilities shift, where contracts matter, where
  complexity warrants context. Not every folder.
- If the code is flat (no package directory for a domain), put a rich section with an anchor heading in
  the nearest parent node rather than inventing an empty directory. Lift it into its own node verbatim
  if the code is later packaged.

Five cheap signals say where a boundary actually is. None decides alone; they agree more often than not.

| Signal | Reads as a boundary when |
|---|---|
| **Manifest** — `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml` | The directory declares its own dependencies. Someone already drew this line; don't redraw it somewhere else. |
| **Size** — non-generated source bytes | Roughly 80KB–256KB, the range where a node compresses something. Under it, merge up: a node costs more than it saves. Over it, split at the largest children. |
| **Coupling** — how often two directories change in the same commit | They mostly change apart. Two directories that always change together are one boundary wearing two names, and two nodes there will contradict each other. |
| **Cohesion** — imports crossing the boundary against imports staying inside | Most stay inside. A directory that mostly imports outward is a *layer*, not a boundary; one node covers both. |
| **Tests** — does it own its own | It does. A directory with no tests of its own rarely owns a contract, and a node there has little to state. |

Exclude lockfiles, `vendor/`, `node_modules/`, generated code, fixtures, snapshots, and migrations
before measuring any of it. They inflate size, they poison co-change — a lockfile touches on nearly
every commit — and they carry no intent.

## What goes in a node

Purpose, key contracts and invariants, traps, the sanctioned choice where alternatives exist,
non-obvious dependencies, and downlinks to related nodes.

| Rule | Why |
|---|---|
| **Derivable? Cut it.** | A rule a capable model re-derives from the source hasn't earned the budget. Write the WHAT NOT and the WHY; the WHAT is a grep away. If it must hold anyway, it's a hook, not a line. |
| **A pattern earns a line only when the code shows several and not which one is correct** | "Repositories return domain objects, never ORM rows" is a rule. "Services live in `services/`" is an `ls`. The case that needs this is a repo mid-migration: both patterns are live in the code and nothing in the source says which to write next. |
| Capture the *what* and the *why* in 1–3 lines per item | Full specs belong in `docs/` behind a downlink. Don't inline them. |
| **Never duplicate across nodes** | Layer-specific nodes defer to a hub; the hub owns the rule and everywhere else links to it. Copies don't just drift — when two rules contradict, Claude picks one arbitrarily. |
| **Invariants, not narration** | A node states what is *true now*. A line that reads like a changelog entry — "X replaced the old Y", "renamed to kill the confusion", a commit SHA, a decision date — belongs in `docs/` or git. Ticket narration ages the instant the ticket ships; invariants don't. |
| **Never leave a tombstone** | Don't document that a symbol *was removed*. Nobody greps a name that no longer exists, so the obituary becomes the only place the dead name survives — and the node starts describing itself instead of the code. Removals are carried by git history. |
| **Skills own procedures; nodes own invariants** | A repeatable how-to belongs in a skill, loaded on demand. Spend a node's budget on constraints a reader can't derive, not steps they'll need occasionally. |

**When unsure, keep it — and never cut a prohibition for reading as generic.** Every rule above
pushes one way, and the cut pressure will happily take a load-bearing line with it. "Never push to
main" is derivable-looking, generic-looking, and load-bearing exactly when nobody is checking.
Safety-critical prohibitions and agent directives are keep-always; a borderline line stays until
whoever owns it says otherwise.

## Compression

- Target **under 200 lines** per node. A guideline, not a cap — a large or complex surface can justify
  more, and nothing truncates a long node. But longer files measurably reduce adherence: Claude starts
  ignoring rules that are present.
- Growing past it is a **routing question** before it is a writing problem. Move procedures to a skill,
  file-shaped rules to `.claude/rules/`, enforcement to a hook.
- Don't restate anything a search would find — `ls`, an export list, a docstring, a type signature, a
  config file, a test name, the manifest. A hand-maintained inventory drifts; point at the thing that
  maintains itself.
- Heavy is fine when the content is load-bearing — naming taxonomies, state-machine maps, idempotency
  rules. Weigh a section against what it prevents, not against its size.

## Memory vs. intent layer

| Goes in a node | Goes in memory |
|---|---|
| Durable architectural facts, contracts, traps — survives sessions, available to every agent | In-flight status, dated incidents, volatile IDs |

When promoting from memory, **trim the memory entry to a pointer** (`see <path>/CLAUDE.md`) so the two
can't drift. A memory entry that says "promoted to the intent layer" and then keeps a copy has promoted
nothing.

## Maintenance

- **Update on the commit that changes the code** if contracts changed, traps were discovered, the
  sanctioned choice moved, or dependencies shifted.
- **Prune on the same commit.** Every other rule here is additive; this one is subtractive, and without
  it nodes only ever grow. Delete a line the moment its subject is renamed, removed, generalized, or
  shipped. Doc entropy is accumulation, not drift.
- **Prefer claims that can't dangle.** Naming a file, symbol, or signature is a claim you now own and
  must re-verify on every change. Describing the constraint instead leaves nothing to verify, and it
  survives the rename that would have broken the citation.
- **Harvest what went wrong.** At the end-of-feature pause, route the session's real pitfalls into the
  right tier — see the `harvest-pitfalls` skill.
- **Run `/audit-intent-layer`** when you suspect drift the commit hook can't see. The hook only catches
  code changing under a node. A node also rots when something *outside* its directory moves — a shared
  contract, a dependency's API, a rule generalized elsewhere — and nothing fires for that.
- **Run `/capture-intent-layer`** when there is no layer to maintain yet, or when one root node is
  carrying what should be several. Placing a whole layer at once is an interview, not an edit — the
  facts worth writing are the ones only a person holds.
- Add cross-references when dependencies exist; prefer downlinks over embedding.
