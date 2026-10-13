# tdd

Test-driven development that scales its rigor to the risk of the change. A copy fix and a payment
race condition shouldn't get the same ceremony: the first needs no test, and the second needs more
than one red test.

The organizing principle: **choose the tier before writing the test.** Most over-testing and
under-testing comes from skipping that choice, not from getting the loop wrong.

## The tiers

| Tier | For | Takes |
|---|---|---|
| None | Copy, config, presentation of a correct value, dead code, mechanical renames and extractions | Look at it |
| Regression (default) | A bug fix or a small feature | One red test per behaviour, watched failing |
| Full | Money, encryption, persisted data, payments, concurrency, cross-service contracts | Edge-case table, script oracles, mutation check |
| Refactor | Logic rewritten, behaviour unchanged | Existing assertions unedited; characterization test where coverage is missing |

The signals, the escalation rules, and the loop itself are in [`skills/tdd/SKILL.md`](skills/tdd/SKILL.md).

## Usage

```
/plugin marketplace add jjailer/claude-skills
/plugin install tdd@jjc-claude-skills
```

The skill loads on its own when Claude writes or changes tests. To invoke it explicitly:

```
/tdd:tdd
```

Workflow skills in your own repo can route to it by name (`tdd:tdd`, Calibrate first) and keep
only their repo's mapping from issue type to tier, so the general rules live in one place.

No hooks and no scripts: this plugin is a single skill.

## Credit

Adapted from [obra/superpowers](https://github.com/obra/superpowers) (`test-driven-development` and
`writing-good-tests.md`), MIT, Copyright (c) 2025 Jesse Vincent. The upstream notice is in
[`LICENSE-superpowers`](LICENSE-superpowers).
