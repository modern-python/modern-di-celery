# `inject` rejects `*args`/`**kwargs` alongside a `FromDI` parameter

**Decision:** decorating a function that declares a `VAR_POSITIONAL` or `VAR_KEYWORD` parameter
*and* at least one `FromDI` parameter raises `TypeError` at decoration time. A task with no `FromDI`
parameter is returned unchanged and may use variadics freely.

The wrapper binds the caller's arguments to the visible signature and calls the task by name
(`func(**bound.arguments, **resolved)`). Binding by name is what makes injection insensitive to
where a `FromDI` parameter sits in the parameter list — a property the suite tests, and the reason
`@inject` can be applied to a task whose dependencies are declared first, last, or interleaved.

By-name calling cannot faithfully forward a variadic. `Signature.bind` stores the payload of `*args`
and `**kwargs` under the literal parameter names, so the re-expansion passes a tuple as a keyword
argument called `args` — a task called with three positional arguments receives one, named wrong.
Two alternatives were rejected:

- **Forward positionally instead.** Gives up by-name binding, and with it order insensitivity,
  for every task in order to serve the combination that provoked the bug.
- **Special-case the two names when re-expanding.** Works until a task declares an ordinary
  parameter genuinely named `args` or `kwargs`, at which point it silently misroutes again — the
  same failure, moved somewhere rarer and harder to find.

Refusing the combination costs a signature nobody has asked for, and it fails at import time rather
than corrupting a payload on a worker. The error names the offending parameter and says what to
write instead.

**Revisit trigger:** a real task needs both — a variadic fan-out signature that also wants a
resolved dependency. By-name binding would then have to be replaced by a call reconstruction that
preserves order insensitivity, and the two rejected options above are the list of what it must not
regress to.
