# Loading edge cases

Read this when a node, rule, or ancestor isn't loading the way the tier table in `SKILL.md` says.

**Two node locations you don't author.** The managed-policy node
(`/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS) loads before everything and cannot be
excluded; you read it, you don't author it. And an ancestor node that loads but doesn't apply — the
monorepo case — is a settings problem, not a writing one: `claudeMdExcludes` in
`.claude/settings.local.json` drops it by glob.

**`paths:` scoping has known gaps** — reported loading globally, and firing on Read but not Write.
Confirm it actually fires before putting something load-bearing behind it.
