---
name: plan-explainer
description: Teach the plan while you write it — an `## Explainer` appendix in the plan file that walks the relevant code and the design decisions (the roads not taken, and the named patterns behind them) with keyed, verbosely labelled Mermaid diagrams, in technical language with a plain-language gloss in parentheses. A hook renders it to a dark-mode-legible page when the plan goes up for approval; it is published as an Artifact only on request. Use in plan mode for any non-trivial plan, before calling ExitPlanMode, and when the user asks to "explain the plan", "diagram the design", or "teach me how this works".
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

Five parts, in this order. Leave out a part that has nothing true to say. The reader wants to come
away a better engineer, not just informed about this diff: the decisions and takeaways are where
that happens, so spend the words there. Scale depth to the plan: a two-file change may earn one
decision and no quiz; padding teaches the reader to skim.

1. **`### Code map`** — the files and symbols this plan touches, and the ones it depends on, as one
   diagram; over the node cap, drop dependencies before touched files. Then two or three sentences
   on the structure it shows. End with **Read first:** the two or three files to open first, in
   order, each with what to look for in it.
2. **`### How it flows`** — the runtime path the change sits on: a `sequenceDiagram` for calls across
   components, a `stateDiagram-v2` for a lifecycle, a `flowchart` for branching logic. One diagram
   per question; two flows get two diagrams.
3. **`### Design decisions`** — the forks in the road, each as a small decision record:

   ```markdown
   #### Keep the key instead of deleting it
   - **Chose:** what the plan does.
   - **Over:** each real alternative, and in one line why it loses *here*.
   - **Pattern:** the established name (with its gloss), and its source if you are sure of it.
   - **Flip signal:** the concrete condition under which the road not taken would win.
   ```

   Keep the `- ` bullets: Markdown joins consecutive lines into one paragraph, so without them the
   fields render as a single run-on block.

   - **No real alternative, no decision.** If nothing credible was passed over, cut the entry.
   - **Up to four in full.** Give the most instructive forks the full record; put the rest under
     `#### Smaller calls`, one line each. Never invent a fork to fill the section.
   - **Pattern only when a real one fits** — *make-before-break*, *mechanism vs. policy*,
     *graceful degradation*: names the reader can search for. No established name fits? Drop the
     line rather than stretch one, or label your own wording "informally, …". Cite the book, paper
     or doc that names it only when you are sure; omit the source rather than guess.
4. **`### Takeaways`** — one to three lessons that generalise *past this codebase*, one sentence
   each, saying where else the reader will meet them ("you'll see this again wherever two writers
   share one file"). Don't restate a decision's **Pattern:** line; say what to carry away from it.
   Then one or two **check yourself** questions with the answer folded away, so the reader recalls
   before reading (*retrieval practice*: recalling an idea fixes it better than re-reading it):

   ```markdown
   <details><summary>Check yourself: why does only <code>save_profile()</code> move threads?</summary>

   The answer, in markdown, after a blank line.

   </details>
   ```

   Ask about the decisions the explainer taught, not a fact it never stated. Inside `<summary>`,
   Markdown does not render: write `<code>` instead of backticks.
5. **`### Glossary`** — a table with one row for every term glossed inline, so the reader has one
   place to review them. The row may say more than the inline gloss did.

## Diagrams

- **One question per diagram, about 12 nodes at most.** A diagram that answers two questions answers
  neither. Say the question on the line directly above the block:
  `**Question this answers:** what runs when the plan goes up for approval?`
- **Fit the column.** The page is narrow and Mermaid wraps a label only at `<br/>`. In a flowchart
  prefer `TD` to `LR`, and keep about three nodes side by side; in a sequence diagram, break a
  long participant alias with `<br/>`.
- **Verbose labels: the real symbol, then its role**, on two lines of about six words each. The
  symbol is what the reader searches for; the role line lets them read the diagram without the
  code. Never a paraphrase alone ("the renderer"). **Label every edge** with what passes along it:
  the data, the call, or the event. The syntax differs by diagram type, and one type's syntax is
  an error in another:

  - `flowchart` — node `R["render.py: main()<br/>cuts out the Explainer"]`; edge
    `R -->|"section text, as JSON"| T`.
  - `stateDiagram-v2` — node `state "Player.save_profile()<br/>asks for a save" as Ask`; edge
    `Ask --> Defer : called off the main thread`.
  - `sequenceDiagram` — participant `participant W as TitleScreen._load<br/>(worker thread)`;
    message `W->>P: set_api_key() asks for a save`.

- **Colour by role, never by hand.** Tag `flowchart` and `stateDiagram-v2` nodes with these classes
  (no other diagram type takes them) — the page supplies colours checked for contrast in both
  themes and draws the key for you. In a flowchart, append `:::new` to the node; in a state
  diagram, write `class Ask new` on its own line.

  | Class | Means |
  |---|---|
  | `:::new` | added by this plan |
  | `:::changed` | modified by this plan |
  | `:::existing` | unchanged; shown for context |
  | `:::external` | outside this codebase: a library, service or person |
  | `:::data` | a stored record, file or table |

  Do not write `classDef`, `style`, `linkStyle` or an `%%{init}%%` block: a hand-picked colour reads
  in one theme only.
- **Key everything the role colours don't.** The page draws the role key; you write a key line
  directly under any diagram that uses anything else — a second arrow style (`-.->` in a flowchart;
  `-->>` replies beside `->>` calls in a sequence diagram), a shape that carries meaning (diamond,
  cylinder, stadium), or a subgraph. Spell each out in full words: *Key: solid arrow = direct call;
  dotted arrow = event fired later; diamond = a branch on the result; cylinder = a file on disk.*

## Language

- **Gloss every term of art in parentheses at its first appearance in prose — no exceptions:**
  "the hook is *idempotent* (safe to run twice: the second run changes nothing)". The gloss says
  what the term *means*, not just what it stands for: *GIL* (global interpreter lock: only one
  thread runs Python bytecode at a time). Glossing every later occurrence turns the page into
  noise, so gloss once; the glossary holds the rest.
- **What counts as a term of art:** pattern names, acronyms, a library's or framework's own
  concepts (*Kivy's Clock*), this codebase's domain words (*manifest*, *re-key*), and CS terms
  (*atomic rename*, *backpressure*). The bar: would a competent engineer new to *this* codebase
  and *this* subfield have to look it up? A term first seen in a heading or a diagram label is
  glossed at its first mention in prose.
- **Cite `file:symbol`**, never line numbers, which go stale.
- **Say how sure you are** when a claim rests on inference rather than code you read.
- Prose explains what the diagram cannot: the why, the constraint, the trade-off. Don't narrate a
  diagram node by node.

## Before ExitPlanMode

Reread the explainer once against this list:

- a term of art with no gloss at its first prose use, or no glossary row;
- a node label that is a paraphrase, or a symbol with no role line;
- an unlabelled edge or message;
- a diagram with no question line, or a shape or arrow style its key doesn't name;
- a decision with no **Over:** or **Flip signal:**, or a pattern name or source you aren't sure of;
- a `#` or `##` heading inside the explainer, which ends the rendered page early.

## After approval

Start the work. The page the hook opened is the explainer's one view; don't publish or open it
again, since a second page mid-task is a distraction.

## Publishing on request

When the user asks for a shareable copy, publish `<plan stem>.artifact.html`, which the hook wrote
beside the plan file:

1. Copy it into the session's scratchpad directory (the Artifact tool publishes only from the
   working directory or the scratchpad). With no scratchpad, ask before copying it into the
   working directory, since it would land in the user's repo.
2. Publish it with the Artifact tool: `icon: "diagram"`, and a one-sentence `description` of what
   the plan changes. Keep it private.
3. Give the user the link in one line.

Asked again after a re-plan? Publish to the same file path, so the link stays the same.
