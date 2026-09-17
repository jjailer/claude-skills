# Campaign state

A campaign spans sessions, so its state lives in `~/.claude/intent-layer/capture/<repo-slug>.json` —
the slug is `git rev-parse --show-toplevel` with `/` and `.` replaced by `-`. Use the repo root, not
the cwd: a resume from a subdirectory, or through a symlink like `/tmp` → `/private/tmp`, must land on
the same file, and git returns the root with symlinks resolved.

| Field | Written | Why it must persist |
|---|---|---|
| `head` | After the Phase 0 answer | `git diff --name-only <head>..HEAD` on resume decides which boundaries moved enough to need re-chunking. |
| `destination` — `committed` or `local` | After the Phase 0 answer | Capture writes files that don't exist yet, so it can't read the variant off disk. A resume must not re-ask. |
| `chunks` — the approved map, in order, each with every path it spans | On approval | Recomputing it is non-deterministic, and a different chunking mid-campaign silently produces overlapping nodes. |
| `skipped` — chunk and reason | Per chunk | Without it, resume re-interviews the chunks that correctly earned nothing, forever. |
| `parked_facts` (with the paths each applies to), `open_questions` (with who knows), `overrides` (local mode), `tasks` | As they arise | By definition they are in no node yet. |

Keep it under `~/.claude`, never in the repo. **State is scaffolding, not product:** a file in the
repo listing open questions about payments is a second, unmaintained intent layer.

**Close-out empties the file.** Every remaining open question is either routed into a node as a
conservative rule or handed back to the SME as a task; every candidate override is handed back as a
change to propose to the committed node's owner. State that outlives the campaign is state nobody will
ever read again.
