# `inject`'s wrapper does not use `functools.wraps`

**Decision:** the wrapper copies `__name__`, `__qualname__`, `__doc__` and `__module__` by hand and
sets `__signature__` to the visible signature. It does not use `functools.wraps`.

Those four attributes are a subset of what `functools.wraps` copies, so the hand-copying reads as an
oversight and invites a one-line "cleanup". It is not an oversight.

`functools.wraps` also sets `__wrapped__`, and `inspect.signature` follows `__wrapped__` — which
would hand Celery's argument binding the *original* signature, `FromDI` parameters included, and
make every caller supply them. That the code would still work by luck is the trap: `inspect`
stops unwrapping at an object that carries its own `__signature__`, so the explicit assignment does
win today. The correctness would then rest on the interaction of two attributes set for opposite
purposes, three lines apart, with nothing naming the dependency between them.

The signature rewrite is the entire mechanism by which a `FromDI` parameter disappears from a task's
public API. Nothing in the wrapper should point `inspect` back at the un-rewritten function, and the
sibling `modern-di` integrations that rewrite signatures avoid `wraps` for the same reason.

**Revisit trigger:** something in the ecosystem needs `__wrapped__` on a task — a debugger, a
documentation generator, or Celery itself — and losing it costs more than the ambiguity gains.

**Related:** [ADR-0003](0003-reject-variadics-alongside-fromdi.md), which depends on the visible
signature being the one Celery binds against.
