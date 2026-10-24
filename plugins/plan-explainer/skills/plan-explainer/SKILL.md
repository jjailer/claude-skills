---
name: plan-explainer
description: Teach the plan while you write it — an `## Explainer` appendix in the plan file that walks the relevant code and the design decisions with keyed Mermaid diagrams, in technical language with a plain-language gloss in parentheses. A hook renders it to a dark-mode-legible page when the plan goes up for approval; after approval it is published as an Artifact. Use in plan mode for any non-trivial plan, before calling ExitPlanMode, and when the user asks to "explain the plan", "diagram the design", or "teach me how this works".
---

# plan-explainer

The plan says what will change. The explainer says **how the code works today, and why the plan
changes it this way** — for a reader who wants to learn the system, not just approve the diff.

## When

Write one when the plan touches more than one file, adds a contract, or makes a decision with a
road not taken. Skip it for routine work: a rename, a one-line fix, a config tweak. An explainer on
every plan teaches the reader to skim them.

## Where

Append it to the plan file as the **last** section, under `## Explainer: <Name>`, where the name
is two to four words in title case that name the change (`## Explainer: Crash Toggle Row`). The
name becomes the page's and the Artifact's title; a bare `## Explainer` falls back to a trimmed
plan heading, which reads as a sentence. The renderer takes everything from that heading to the
next `#` or `##` heading outside a code fence, so use `###` and deeper inside it. Plan mode lets
you write only the plan file; the hook does the rest when you call ExitPlanMode, and removes the
old page if a re-plan drops the section.

## Shape

Four parts, in this order. Leave out a part that has nothing true to say.

1. **`### Code map`** — the files and symbols this plan touches, and the ones it depends on, as one
   diagram. Then two or three sentences on the structure it shows.
2. **`### How it flows`** — the runtime path the change sits on: a `sequenceDiagram` for calls across
   components, a `stateDiagram-v2` for a lifecycle, a `flowchart` for branching logic. One diagram
   per question; two flows get two diagrams.
3. **`### Design decisions`** — one `####` per decision: what was chosen, over what, and why. Name
   the transferable principle ("this is an instance of *mechanism vs. policy*") so the reader
   recognises it next time.
4. **`### Glossary`** — a table of the terms of art the explainer used, each with a one-line plain
   definition. Only terms a reader new to this codebase would need.

## Diagrams

- **One question per diagram, about 15 nodes at most.** A diagram that answers two questions answers
  neither.
- **Prefer `flowchart TD`.** The page column is narrow; a left-to-right chain of more than four
  nodes runs off it and has to be scrolled sideways.
- **Real names.** Nodes carry the real symbol or file (`render_fragment()`, `hooks/render.py`), never
  a paraphrase ("the renderer"). Edge labels say what passes along the edge.
- **Colour by role, never by hand.** Tag `flowchart` and `stateDiagram-v2` nodes with these classes
  (no other diagram type takes them) — the page supplies colours checked for contrast in both
  themes and draws the key for you:

  | Class | Means |
  |---|---|
  | `:::new` | added by this plan |
  | `:::changed` | modified by this plan |
  | `:::existing` | unchanged; shown for context |
  | `:::external` | outside this codebase: a library, service or person |
  | `:::data` | a stored record, file or table |

  Do not write `classDef`, `style`, `linkStyle` or an `%%{init}%%` block: a hand-picked colour reads
  in one theme only.
- **Key what the roles don't cover.** If a diagram uses more than one arrow style (`-->` vs `-.->`)
  or a shape that carries meaning, add a one-line key directly under the block:
  *Key: solid arrow = direct call; dotted arrow = event.* Sequence diagrams take no role classes, so
  their key, if any, is this line.

## Language

- **Technical term first, plain gloss in parentheses, on first use only:** "the hook is
  *idempotent* (safe to run twice: the second run changes nothing)". Glossing every occurrence
  turns the page into noise. A term that needs more than a clause goes in the glossary instead.
- **Cite `file:symbol`**, never line numbers, which go stale.
- **Say how sure you are** when a claim rests on inference rather than code you read.
- Prose explains what the diagram cannot: the why, the constraint, the trade-off. Don't narrate a
  diagram node by node.

## After approval

The hook wrote `<plan stem>.artifact.html` beside the plan file. Before starting the work:

1. Copy it into the session's scratchpad directory (the Artifact tool publishes only from the
   working directory or the scratchpad). With no scratchpad, ask before copying it into the
   working directory, since it would land in the user's repo.
2. Publish it with the Artifact tool: `icon: "diagram"`, and a one-sentence `description` of what
   the plan changes. Keep it private.
3. Give the user the link in one line.

Re-planned and approved again? Publish to the same file path, so the link stays the same.
