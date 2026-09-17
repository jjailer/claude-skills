---
name: intent-layer
description: Authoring and pruning CLAUDE.md intent-layer nodes — where a node belongs, what earns a line in one, how hard to compress, and when to delete. Use when creating a new CLAUDE.md, editing or reviewing an existing one, deciding whether a rule belongs in a node vs a path-scoped rule vs a skill vs a hook, or when the commit hook reports a node its commit didn't update. Triggers on "add a CLAUDE.md", "create a node", "update the intent layer", "prune this node", "does this belong in CLAUDE.md", "where should this rule live". For a repo with no layer yet, suggest the user run /intent-layer:capturing-intent-layer instead.
---

# Intent layer

The Intent Layer is a hierarchy of `CLAUDE.md` nodes at semantic boundaries carrying what a capable
model **cannot re-derive from the code**: contracts, traps, and the sanctioned choice. The goal is
progressive disclosure — high-level context first, deeper detail behind links.

Three facts set every rule below.

| Fact | Consequence |
|---|---|
| **Load** — nodes *above* the working directory load in full at launch. A subtree node loads only when Claude reads a file under it, and is not re-injected after `/compact`. | A leaf node costs less than a root node and is less reliable — it can vanish mid-session. Anything that must always hold belongs higher up. |
| **Advisory** — a node is context delivered as a user message, not enforced configuration. There is no guarantee of compliance. | See *Escalation*. |
| **Derivable** — the WHAT is searchable. | Spend the budget on the WHAT NOT and the WHY. |

## The tiers

| Tier | Loads | Owns |
|---|---|---|
| `CLAUDE.md` node | ancestors at launch, subtree on read | non-derivable invariants, contracts, traps |
| `.claude/rules/*.md`, no frontmatter | at launch, same priority as `.claude/CLAUDE.md` | a long root node's topics split into files — organization, without changing what loads |
| `.claude/rules/*.md` with `paths:` frontmatter | when Claude reads a matching file | rules that glob across the tree rather than belonging to one directory |
| Skill | on demand | repeatable procedures |

Something not loading the way this table says — a managed-policy node, an ancestor that doesn't
apply, a `paths:` rule that won't fire — read `references/loading.md`.

## Where a rule belongs

The tiers above say what each destination *is*. This says which one a given rule goes to — it is the
one home for that decision, and everything routing into the layer works down it. **The first row that
fits wins.**

| If the rule | Goes to | Because |
|---|---|---|
| Is something a capable model reading the source would get right on its own, and is not a prohibition or agent directive | **Nowhere. Drop it.** | The WHAT is a grep away. Always-loaded context is not free, and a line restating the code is pure cost with no upside. |
| Must hold even when there is pressure to skip it | **`PreToolUse` hook** | See *Escalation*. |
| Is a repeatable multi-step procedure | **Skill** | Loaded on demand, so it costs nothing to the sessions that don't need it. Skills own procedures; nodes own invariants. |
| Applies to a file *type* across the tree rather than to one directory | **`.claude/rules/*.md` with `paths:`** | Globs by pattern instead of by location — but confirm it fires (`references/loading.md`). |
| Is a non-derivable invariant, contract, or trap owned by one area | **Nearest node** | 1–3 lines, invariant not narration, one home. The rest of this skill is about writing that line. |

Callers screen before this table rather than extending it: a row appended after the last one is
unreachable, because nearly anything non-derivable fits *nearest node*. `harvesting-pitfalls` screens
out session leftovers with its own pre-filters before it starts here.

**Escalation.** A node is advisory: a rule Claude ignores under pressure is not a wording problem, and
writing it more forcefully changes nothing — write a `PreToolUse` hook. Anthropic: *"To block an
action regardless of what Claude decides, use a PreToolUse hook instead."* `IMPORTANT` on a
load-bearing line the first time it is written does buy adherence; adding it to a line already being
ignored buys nothing, and if every rule is important then none are.

**When the node isn't yours to commit**, the layer goes to gitignored `CLAUDE.local.md` under the same
bar. Read `references/local-nodes.md` — *When the node isn't yours* — before writing or reviewing one.

## Where nodes live

- Place them at **semantic boundaries** — where responsibilities shift, where contracts matter, where
  complexity warrants context. Not every folder.
- If the code is flat (no package directory for a domain), put a rich section with an anchor heading in
  the nearest parent node rather than inventing an empty directory. Lift it into its own node verbatim
  if the code is later packaged.

Five cheap signals say where a boundary actually is. None decides alone; they agree more often than not.

| Signal | Reads as a boundary when |
|---|---|
| **Manifest** — `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, `*.csproj` | The directory declares its own dependencies. Someone already drew this line; don't redraw it somewhere else. |
| **Size** — non-generated source bytes | Roughly 80KB–256KB, the range where a node compresses something. Under it, merge up: a node costs more than it saves. Over it, split at the largest children. |
| **Coupling** — how often two directories change in the same commit | They mostly change apart. Two directories that always change together are one boundary wearing two names, and two nodes there will contradict each other. |
| **Cohesion** — imports crossing the boundary against imports staying inside | Most stay inside. A directory that mostly imports outward is a *layer*, not a boundary; one node covers both. |
| **Tests** — does it own its own | It does. A directory with no tests of its own rarely owns a contract, and a node there has little to state. |

**Exclude before measuring any of it:** lockfiles, `vendor/`, `node_modules/`, generated code,
fixtures, snapshots, and migrations — plus markdown and config when measuring size. They inflate
size, they poison co-change — a lockfile touches on nearly every commit — and they carry no intent.
In git commands, pass them as `':(exclude)…'` pathspecs so the counts and the co-change agree.

## What goes in a node

Purpose, key contracts and invariants, traps, the sanctioned choice where alternatives exist,
non-obvious dependencies, and downlinks to related nodes.

| Rule | Why |
|---|---|
| **Derivable? Cut it.** | A rule a capable model re-derives from the source hasn't earned the budget. Write the WHAT NOT and the WHY; the WHAT is a grep away. |
| **A pattern earns a line only when the code shows several and not which one is correct** | "Repositories return domain objects, never ORM rows" is a rule. "Services live in `services/`" is an `ls`. The case that needs this is a repo mid-migration: both patterns are live in the code and nothing in the source says which to write next. |
| Capture the *what* and the *why* in 1–3 lines per item | Full specs belong in `docs/` behind a downlink. Don't inline them. |
| **Never duplicate across nodes** | Copies don't just drift — when two rules contradict, Claude picks one arbitrarily. A fact shared by descendants **moves** to their nearest common ancestor and needs no pointer, because an ancestor already loads with them. A fact a *sideways* subtree depends on stays in its hub, and the dependent node links to it. |
| **Invariants, not narration** | A node states what is *true now*. A line that reads like a changelog entry — "X replaced the old Y", "renamed to kill the confusion", a commit SHA, a decision date — belongs in `docs/` or git. Ticket narration ages the instant the ticket ships; invariants don't. |
| **Never leave a tombstone** | Don't document that a symbol *was removed*. Nobody greps a name that no longer exists, so the obituary becomes the only place the dead name survives — and the node starts describing itself instead of the code. Removals are carried by git history. |

**When unsure, keep it — and never cut a prohibition for reading as generic.** Every rule above
pushes one way, and the cut pressure will happily take a load-bearing line with it. "Never push to
main" is derivable-looking, generic-looking, and load-bearing exactly when nobody is checking.
Safety-critical prohibitions and agent directives are keep-always; a borderline line stays until
whoever owns it says otherwise.

## Compression

- Target **under 200 lines** per node. A guideline, not a cap — a large or complex surface can justify
  more, and nothing truncates a long node. But longer files measurably reduce adherence: Claude starts
  ignoring rules that are present.
- Growing past it is a **routing question** before it is a writing problem — work down *Where a rule
  belongs* for whatever should move out.
- Don't restate anything a search would find — `ls`, an export list, a docstring, a type signature, a
  config file, a test name, the manifest. A hand-maintained inventory drifts; point at the thing that
  maintains itself.
- Heavy is fine when the content is load-bearing — naming taxonomies, state-machine maps, idempotency
  rules. Weigh a section against what it prevents, not against its size.

## Memory vs. intent layer

| Goes in a node | Goes in memory |
|---|---|
| Durable architectural facts, contracts, traps — survives sessions, available to every agent | In-flight status, dated incidents, volatile IDs |

A local node is not memory either: memory is cross-project and surfaces on relevance, while a local
node is this-repo and loads by the same rules as any other node.

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
  right tier — see the `harvesting-pitfalls` skill.
- **Audit for drift the commit hook can't see** with the `auditing-intent-layer` skill
  (`/intent-layer:auditing-intent-layer`). The hook only catches code changing under a node. A node
  also rots when something *outside* its directory moves — a shared contract, a dependency's API, a
  rule generalized elsewhere — and nothing fires for that.
- **Suggest the user capture a whole layer** with `/intent-layer:capturing-intent-layer` — it is
  user-invoked only, since it writes files — when there is no layer to maintain yet, or when one root
  node is carrying what should be several. Placing a whole layer at once is an interview, not an edit.
- Add cross-references when dependencies exist; prefer downlinks over embedding.
