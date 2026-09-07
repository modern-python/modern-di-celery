# AGENTS.md

[`CONTEXT.md`](CONTEXT.md) opens with what this package is and owns the vocabulary — read it before
naming a concept in code, in a test name, or in an issue title.

## Workflow

Real work **not scheduled** becomes a GitHub issue.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches.
Nothing enforces that docstring shape; it is read at review time.
