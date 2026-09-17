# Measuring the chunking signals

The signals and their thresholds belong to the `intent-layer` skill's *Where nodes live*, including
what to exclude. This file is only how to measure them with git. Pass the exclusions as
`':(exclude)…'` pathspecs in every command below.

## Manifests

Filter this list by the manifest names in *Where nodes live*:

```
git ls-files
```

## Size

```
git ls-files -z -- <dir> ':(exclude)*.md' ':(exclude)*.lock' … | xargs -0 cat | wc -c
```

## Coupling, by inclusion-exclusion

For adjacent sibling pairs among the candidates that passed the size filter. Three counts —
one for `A`, one for `B`, one for both:

```
git log --oneline --since=18.months -- <A> <exclusions> | wc -l
git log --oneline --since=18.months -- <B> <exclusions> | wc -l
git log --oneline --since=18.months -- <A> <B> <exclusions> | wc -l
```

Co-changes are `|A| + |B| - |A∪B|`; take the ratio against the smaller of `|A|` and `|B|`.

**Write every path as its own literal argument** — `-- src/a src/b` — never through a variable. zsh
does not word-split `$paths`, so `A B` arrives as one path that matches nothing, `|A∪B|` comes back
zero, and every pair looks coupled. **Check the counts before trusting the ratio:** `|A∪B|` is never
below `max(|A|, |B|)`. If it is, the command was malformed — rerun it; don't propose a merge on it.

**Ignore the ratio when the smaller side has fewer than about ten commits.** One shared commit out of
two is 50% and means nothing; a young or rarely-touched directory has no co-change signal. Fall back
to the other four signals.

| Ratio | In the chunk map |
|---|---|
| Above ~40% | Propose merging the pair, and name which other signals agree. Coupling alone doesn't decide it. |
| ~20–40% | Not a merge. Counts as a co-change partner for ordering. |

## Ordering within a tier

Ascending by **co-change partners** (siblings above ~20%) **times distinct authors**:

```
git shortlog -sn --since=18.months HEAD -- <dir> <exclusions>
```

`HEAD` is required — without a revision, a non-interactive shortlog reads stdin and reports nothing.
