# Before the code exists

The **greenfield** branch of Phase 0. It replaces chunking and the campaign loop; campaign state still
applies, and so does the close-out report, minus the commit-rate replay (there is no history to
replay).

A node written ahead of its code is the one case where nothing is derivable, so almost everything the
SME says qualifies. That is also what makes it dangerous: there is no source to check it against.

**Write commitments, not descriptions.**

| Dangles | Holds |
|---|---|
| "This directory will own payment retries" | "Everything touching Stripe goes through here — a `stripe` import anywhere else is a bug" |

A description of the future must be re-verified the day the code arrives, and nobody will. A
commitment is falsified by the code rather than by the node — so when the two diverge, the node is
right and the code is wrong. Present tense, always: state what is *allowed*, never what *will exist*.

**A boundary the SME cannot state a rule for does not get a directory.** If the only thing true about
it is its name, there is nothing to write down and the directory is a guess that someone will have to
delete.

## The four steps

**Do not run `/init`.** There is nothing to initialize from, and a generated root node would look
authoritative while saying nothing the SME chose.

**G1 — Elicit.** No code, so no evidence-earned questions — the citation table under *The interview*
is unavailable here. Ask what is being built, which boundaries are already intended, and, per
boundary, the one rule that must hold there.

**G2 — Approve.** Present the boundaries and their rules as a table and **stop for approval.** This
list is the greenfield chunk map, and the same checkpoint applies: fixing it later means re-asking.

**G3 — Scaffold.** Create one node per approved boundary (writing the node creates its directory),
commitments only, present tense, in the variant Phase 0 settled. Then write the root node from intent
alone: what this project is, the boundaries and their rules, downlinks to each.

**G4 — Hand off.** In committed mode, say explicitly that `/init` should be run later, once there is
code and tooling to describe; it will find these nodes and layer under them. In local mode, don't —
`/init` writes a committed root node.
