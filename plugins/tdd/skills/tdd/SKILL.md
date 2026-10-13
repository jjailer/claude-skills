---
name: tdd
description: Use when writing or changing tests, adding mocks or test helpers, or doing test-first feature/bugfix work — including deciding whether a change needs a test at all and how much rigor it gets. Covers the rigor tiers, the red-green-refactor loop, naming the break a test catches, deriving expected values, choosing what to mock, and the pre-done mutation check.
---

# TDD

Adapted from superpowers 6.4.1 `test-driven-development` + `writing-good-tests.md` (obra/superpowers,
MIT, Copyright (c) 2025 Jesse Vincent; full notice in the plugin's `LICENSE-superpowers`).

## Calibrate first

Pick a tier before writing anything, and state it in the plan so whoever approves the approach
approves the rigor with it. Rigor scales with what the bug would cost once it reached users, not
with the size of the diff.

A change has **testable behaviour** when it alters a return value, a side effect, or a state
transition for an input you can name. That line separates None from every other tier.

| Tier | Signals | What it takes |
|---|---|---|
| **None** | Presentation of an already-correct value, copy, config, docs, dead code, log text, a guard for a case that can't occur, generated code, a throwaway prototype, a mechanical move (rename, extract method or constant) that edits no logic. You can't name a break. | Run it or look at it. No new test; the existing suite covers a mechanical move. |
| **Regression** (default) | One named behaviour: a bug fix or a small feature. | The loop below, with one RED test per behaviour. Watching it fail against the unfixed code *is* the mutation check. Literal expected values; script oracle only for arithmetic you'd get wrong in your head. |
| **Full** | Money, credentials or encryption, persisted or migrated data, payments and webhooks, concurrency or ordering, a state machine with many transitions, a contract another service depends on. | Regression, plus an edge-case table (zero, empty, nil, unauthorised, malformed, boundary), a script oracle for every computed expectation, the full mutation check, and a test across the boundary when a contract changes. |
| **Refactor** | Logic is rewritten — restructured, not just moved — and behaviour must not change. | No new behaviour tests. Existing tests pass before and after with assertions unedited — an edited assertion means behaviour changed. Rewriting logic no test covers? Pin it with a characterization test first; it passes on its first run, correctly, and stays as the regression guard. |

- **More than one behaviour** stays Regression: one RED test each.
- **Escalate to Full** when a Full signal turns up mid-work, or the RED surprises you — it fails
  for a reason you didn't predict.
- **Drop to None** when you can't name the production change that would break the test.
- **Nondeterministic bugs** (races, timers, ordering): a RED that fails only sometimes isn't a RED.
  Force the interleaving — a barrier, an injected clock, an explicit call order — until it fails on
  every run, then fix.

## Ground rules

- Tests assert **correct** behaviour. If the code is buggy the test fails; never match an assertion
  to buggy output, and never edit a test to accommodate buggy code.
- Can't fix the bug now? Mark the test an expected failure carrying the reason (pytest:
  `@pytest.mark.xfail(reason="BUG: …")`) so the suite stays green and flags the fix when it lands.
- Scratch tests are welcome inside the loop. Before committing, prune any you can't tie to a named
  failure mode.

## The loop

1. **RED** — one minimal test for one behaviour, named for what should happen. "and" in the name? Split it.
2. **Verify RED** — run it. It must *fail*, not error, with the message you expected, because the
   feature is missing (not a typo or import error). Passes immediately? You're testing existing
   behaviour — fix the test. Two exceptions pass first run by design: a characterization test
   (Refactor tier), and a guard test pinning behaviour the change must not break, such as most
   Full-tier edge cases. Validate either by breaking the code on purpose and watching it fail.
3. **GREEN** — simplest code that passes. No extra options, no refactoring neighbours.
4. **Verify GREEN** — run the test file you touched. Output pristine: no new warnings or errors. A
   test fails? Fix the code, not the test.
5. **REFACTOR** — only on green: dedupe, rename, extract. Stay green; add no behaviour.
6. **Done** — run the project's *full* suite once and name every failure, including ones you didn't
   cause. A full run on every cycle costs minutes and buys nothing this one doesn't. A skipped
   test is not a pass: name any of yours that skipped, and why.

Bug fix = same loop: the RED test reproduces the bug. Code written before its test gets its test
watched failing against a reverted version before you trust it.

## Name the break

Before writing the test body: **what production change should make this test fail — and is that
change a bug or a decision?**

| Answer | Do |
|---|---|
| Can't name one | Redesign around an observable behaviour |
| "The source text changed" | Run the artifact and assert its effects — never grep its text |
| Only intentional decisions | Change detector. Test the behaviour the decision drives: not `MAX_RETRIES == 5` but "the 6th attempt never happens" |

- **No mirror assertions.** An expected value computed by the code under test, or its helpers,
  passes whatever the code does. Table-driven tests with literal `want` values are the preferred shape.
- **Script oracles.** For arithmetic you'd get wrong in your head (hashes, dates, floats,
  combinatorics), compute the expected value with a throwaway script: stdlib or brute force, never
  importing the project, ideally a different method than the implementation — a same-author
  reimplementation shares the author's misconception. Paste the output as a literal and keep the
  one-liner in a comment beside it.
- **Your contract, not the framework's.** Test the route you register, the query you emit, the
  payload you produce — not that the router calls handlers. Constructors, getters, constants and
  trivial forwarding earn tests only when they validate, normalise, default, derive, or cause side
  effects. Upstream surprised you? One narrow characterization test naming the assumption.
- Prose for humans earns no test. Documents that instruct agents are tested by the agent's behaviour.

## Exercise the real thing

- **Before mocking, list the real method's side effects.** Keep what the test depends on real;
  mock the slow/external level *below* it. Unsure? Run against the real implementation first and
  watch what actually needs to happen.
- **Make doubles specific.** When arguments, call counts or ordering are part of the contract,
  assert them. Give each branch (success, error, malformed) its own fixture so the wrong branch
  can't satisfy the expectation.
- **Mirror real data completely** — every documented field, not just the ones this test reads.
  Partial mocks pass while integration breaks.
- **Production classes carry production methods only.** Called only from tests? It belongs in
  test utilities.
- **Mock setup outgrowing the test** is the signal to switch to an integration test with real
  components. Hard to test usually means hard to use — listen to the design.

## Mutation check (Full tier)

At the Regression tier, the RED watched against the unfixed code covers this. At Full, mentally
mutate the production code; at least one test should fail for each realistic mutation:

- wrong constant or argument
- wrong branch handler
- missing state change or side effect
- empty or default return
- missing validation for zero, empty, nil, unauthorised, or malformed input

A mutation nothing catches is unprotected behaviour — or a tautological test.

## Warning signs

- Setup and assertion share an object, guaranteeing equality
- The test can only fail via crash, panic, or missing selector
- It fails on every intentional change, never on accidental breakage
- Expected values hidden behind loops, builders, or helpers
- It asserts on a `*-mock` test ID, or would fail if you removed the mock
- Mock setup is over half the test, or you can't say why the mock is needed
- It exists for coverage, checking no outcome or side effect
