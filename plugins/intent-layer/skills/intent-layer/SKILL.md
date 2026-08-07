---
name: intent-layer
description: Authoring, auditing, and pruning CLAUDE.md intent-layer nodes — where a node belongs, what earns a line in one, how hard to compress, and when to delete. Use when creating a new CLAUDE.md, editing or reviewing an existing one, deciding whether a rule belongs in a node vs docs vs a skill, or when a commit changed contracts, patterns, or pitfalls that a node describes. Triggers on "add a CLAUDE.md", "create a node", "update the intent layer", "audit the CLAUDE.md files", "prune this node", "does this belong in CLAUDE.md", "the intent layer is stale", and on any commit touching code under a directory that has a CLAUDE.md.
---

# Intent layer

The Intent Layer is a hierarchy of `CLAUDE.md` files at semantic boundaries capturing implicit
knowledge: contracts, patterns, pitfalls. The goal is progressive disclosure — high-level context
first, deeper detail behind links.

A node is loaded into context every session that enters its directory. That is the budget every rule
below is protecting.

## Where nodes live

- Place them at **semantic boundaries** — where responsibilities shift, where contracts matter, where
  complexity warrants context. Not every folder.
- A node auto-loads only when an agent enters its directory. If the code is flat (no package
  directory for a domain), put a rich section with an anchor heading in the nearest parent node
  rather than inventing an empty directory. Lift it into its own node verbatim if the code is later
  packaged.
- **Micromodule nodes are low-ROI** — single-file utilities, constant tables, mixins. Defer them
  unless that surface is edited often.

## What goes in a node

Purpose, entry points, key contracts and invariants, patterns, anti-patterns and pitfalls,
dependencies, and downlinks to related nodes.

| Rule | Why |
|---|---|
| Capture the *what* and the *why* in 1–3 lines per item | Full specs belong in `docs/` behind a downlink. Don't inline them. |
| **Never duplicate across nodes** | Layer-specific nodes defer to a hub; the hub owns the rule and everywhere else links to it. One rule copied into five places becomes five places that disagree. |
| **Invariants, not narration** | A node states what is *true now*. A line that reads like a changelog entry — "X replaced the old Y", "renamed to kill the confusion", "moved from the old module", a commit SHA, a decision date — belongs in `docs/` or git. Ticket narration ages the instant the ticket ships; invariants don't. |
| **Never leave a tombstone** | Don't document that a symbol *was removed*. Nobody greps a name that no longer exists, so the obituary becomes the only place the dead name survives — and the node starts describing itself instead of the code. Removals are carried by git history. |
| **Skills own procedures; nodes own invariants** | A repeatable how-to belongs in a skill, loaded on demand. A node is loaded every session — spend that budget on constraints a reader can't derive, not steps they'll need occasionally. |

## Compression

- Target **~5–10:1** line-to-SLOC for layer nodes. Under-compression (~1:1) is the more common
  failure, and usually means the node is mirroring code instead of compressing intent.
- Heavy nodes are fine when the content is load-bearing — naming taxonomies, state-machine maps,
  idempotency rules. A 2k-token section that prevents recurring bugs beats a 200-token section
  nobody reads.
- A node **>2k tokens covering <500 SLOC** is a smell: either split it, or move much of it to `docs/`.
- **Cap the entry, not just the node.** Node-level ratios hide blob-level rot — a node can sit inside
  target while half of it is one 1,000-word bullet. No single bullet over **~80 words**; split it or
  move it.
- **Prefer tables to prose.** A missing table row is visible in a diff; a stale clause buried in a
  paragraph is not. Format is a rot-detection mechanism, not cosmetics — the nodes that survive
  audits cleanest are the ones written as tables.
- Don't restate what a reader gets free from `ls`, a module's export list, or its docstring. A
  hand-maintained file inventory will drift; point at the thing that maintains itself.

## Memory vs. intent layer

| Goes in a node | Goes in memory |
|---|---|
| Durable architectural facts, contracts, pitfalls — survives sessions, available to every agent | In-flight status, dated incidents, volatile IDs |

When promoting from memory, **trim the memory entry to a pointer** (`see <path>/CLAUDE.md`) so the
two can't drift. A memory entry that says "promoted to the intent layer" and then keeps a copy has
promoted nothing.

## Maintenance

- **Update on the commit that changes the code** if contracts changed, patterns or anti-patterns
  emerged, pitfalls were discovered, or dependencies shifted.
- **Prune on the same commit.** Every other rule here is additive; this one is subtractive, and
  without it nodes only ever grow. Delete a line the moment its subject is renamed, removed,
  generalized, or shipped. Doc entropy is accumulation, not drift.
- **Treat any specific file, line, test, flag, or date claim as a verification target before citing
  it.** Re-grep; don't trust. A node that names a file, symbol, or signature that no longer resolves
  is a **failure**, not untidiness — it sends a reader to something that doesn't exist and costs more
  than the line ever saved.
- **Re-verify periodically, not just on touch.** Rot is invisible from inside the node; the only test
  is re-grepping every concrete claim against the code. Audit a node when its diff exceeds ~30% since
  the last pass, or quarterly for high-churn ones. Fan the sweep out across parallel agents — it
  parallelizes almost perfectly by subtree.
- Add cross-references when dependencies exist; prefer downlinks over embedding.
