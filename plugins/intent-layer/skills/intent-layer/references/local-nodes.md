# When the node isn't yours

Sometimes you may not commit to a repo's nodes at all — the layer isn't your call. Then it goes to
`CLAUDE.local.md`, which loads right after `CLAUDE.md` in the same directory, is discovered in
subdirectories exactly like a nested node, and is gitignored. It **supplements** whatever committed
nodes exist rather than replacing them. Permission is a property of the repo, not of the fact, so one
answer covers every node.

| Rule | Why |
|---|---|
| **Same bar** | The variant changes who can read the layer, never what earns a line. A file nobody reviews is where derivable filler goes to hide. |
| **Never restate — add, or override in the open** | Loading last means a line copied from the committed node outranks its original, and only one of the two is reviewable, so the pair drifts with nobody watching. An override is legitimate and often the point; it has to name what it overrides. |
| **Update it before you commit** | It can never appear in a commit, so the commit hook counts it as updated when it is newer than the code implicating it. Edit code, edit node, commit. |
| **A node arriving later gets a sibling, not an edit** | When the hook names a committed `CLAUDE.md` that isn't yours, start a `CLAUDE.local.md` beside it rather than editing theirs. |
| **A directory holding both belongs to the local node** | It is the one you can write, and it resolves last. Committed is the default only when nothing answers — a directory with no local node beside it. |
| **Promotion deletes the original** | If the layer later becomes yours to commit, content moves into the committed nodes and the local file goes — moved, not copied and pointed at. |
