# modern-di-celery

A Celery adapter over [`modern-di`](https://github.com/modern-python/modern-di): it stores a root
container on the Celery app, opens and closes it on the worker lifecycle signals, and resolves a
task's marked parameters from a child container built per task invocation.

## Language

A term is listed only when there is a synonym to reject, or a meaning subtle enough that code and
docs must agree on it. General programming vocabulary does not belong here, however heavily this
package uses it.

The domain terms are `modern-di`'s — `Container`, `Provider`, `Group`, `Scope`, `Resolution`,
`Override`. That project's `CONTEXT.md` is the authority for all of them; nothing here redefines
one. Celery's vocabulary is Celery's — task, worker, broker, beat, and the pool names mean what
[its docs](https://docs.celeryq.dev) say they mean. The three below are this package's own.

**Root container**:
The `Scope.APP` `Container` handed to `setup_di` and stored on the Celery app's `conf`; the worker
lifecycle signals open and close it, and every per-task child descends from it. `fetch_di_container`
returns this one.
_Avoid_: APP container, APP-scope container — both have been used for it, and neither says the thing
that matters at a call site, which is that this is the container a per-task child is built *from*.

**Per-task child container**:
The `Scope.REQUEST` child that `inject` builds, opens, resolves from, and closes on every task
invocation. It is REQUEST-scoped even though a Celery task carries no request: the unit of work is
one task invocation, and there is no framework object to seed it with, so it is built with no
context and this integration registers no connection provider.

**Visible signature**:
The task function's signature with its `FromDI` parameters removed, set on the wrapper as
`__signature__`. It is what Celery binds a caller's arguments against, so a DI parameter that leaks
into it becomes an argument the caller is required to pass.
_Avoid_: stripped signature, rewritten signature.
