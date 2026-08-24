---
name: harvesting-pitfalls
description: Turning friction from the current session into a durable rule, or correctly throwing it away — what counts as a pitfall, and whether it belongs in a CLAUDE.md node, a path-scoped rule, a skill, a hook, or nowhere. Use at the end-of-feature pause before committing, when the commit hook reports signals of a recurring pitfall, or when a session went badly and you want the lesson to survive it. Triggers on "harvest pitfalls", "what went wrong this session", "capture this as a rule", "make sure this doesn't happen again", "add this to CLAUDE.md so you remember".
---

# Harvest pitfalls

A session that hit real friction knows something the repo doesn't. This is how that becomes a rule —
or gets discarded, which is the more common correct answer.

You lived the session, so you have the one thing a transcript reader never recovers: **what you
assumed, and when you found out it was wrong.** That gap is the pitfall. The error message is just
where it surfaced.

## The bar

A pitfall is a **wrong assumption that will recur**. Not everything that cost time qualifies.

| Qualifies | Doesn't |
|---|---|
| You assumed a contract that wasn't true, and nothing in the source said otherwise | You misread code that was perfectly clear |
| The same fix failed twice because the real cause was somewhere you didn't look | A test went red once and the next edit fixed it — that's red-green working |
| A convention exists, is enforced socially, and is invisible in the code | You needed a fact you could have grepped in ten seconds |
| The correction had to be given twice before it stuck | You were corrected once and adjusted |
| A tool or command fails in a way specific to this repo's layout | A typo, a wrong path, an ordinary slip |

**Iteration is not a pitfall.** Most sessions produce nothing durable, and saying so in one line is a
complete and correct answer. A harvest that always finds something is manufacturing findings to
justify itself, and every fabricated rule costs context forever while protecting against nothing.

## Route it

Name the assumption in one sentence — *what you assumed, what was actually true* — then place it.

Work down the **`intent-layer` skill's *Where a rule belongs* table**. That table is the one home for
this decision and its five rows settle most pitfalls; the first row that fits wins.

If none of the five fits, a session leaves two kinds of residue that table doesn't carry, because
neither is a rule about the code:

| If | Destination | Because |
|---|---|---|
| It's a repeated permission prompt | **`settings.json` allowlist** | Not an intent-layer problem at all. |
| It's in-flight, dated, or a volatile ID | **Memory, or nowhere** | It will be false next month. |

## Writing the escalation hook

Routing sends most things to *drop* or *one line in a node*. The hook row is the one that
needs real work, so it's worth knowing the shape before you decide it's too expensive.

A `PreToolUse` hook is a script that reads a JSON event on stdin and exits 0. To **block**, print
`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
"permissionDecisionReason": "..."}}`. To **advise without blocking**, print `additionalContext`
instead — the tool still runs, so the model reads it after the fact.

Three rules that decide whether the hook survives contact:

- **Exit 0 on every path**, including malformed input. A hook that errors is a hook that gets removed.
- **Say nothing unless it matters.** Match narrowly — on the specific command, not on `Bash`.
- **Deny only what is genuinely unsafe.** Everything else should advise. A gate that fires on
  legitimate work gets disabled within a week, taking the real protection with it.

`hooks/intent_layer_check.py` in this plugin is a worked example of the advisory shape.

## Landing it

Put the change in the commit you were about to make (`git commit --amend --no-edit` if it already
ran — the hook speaks after the tool, and nothing is pushed yet).

Then say plainly what you captured and what you discarded. "Two signals, both ordinary iteration,
nothing captured" is a good outcome and should be reported as one, not padded.
