# Dependency injection

The capability this package exists for: wiring a `modern-di` `Container` into
a Celery `app` so task parameters resolve from it, scoped per task
invocation. Everything lives in `modern_di_celery/main.py`; the public surface
is `setup_di`, `fetch_di_container`, `FromDI`, `inject`, and `DITask`.

## Setup and worker-signal lifecycle

`setup_di(app, container)` is the single entry point. It:

1. Stores the container on `app.conf` under `_ROOT_CONTAINER_KEY`
   (`"modern_di_container"`), a named constant — writer (`setup_di`) and
   reader (`fetch_di_container`) stay in provable agreement instead of
   relying on a bare string literal.
2. Connects two named closures to Celery's worker-process signals:
   `signals.worker_process_init.connect(_open_container, weak=False)` calls
   `container.open()`, and
   `signals.worker_process_shutdown.connect(_close_container, weak=False)`
   calls `container.close_sync()`.

`weak=False` is required on both connections. Celery's signal dispatcher
holds receivers by weak reference by default; `_open_container` and
`_close_container` are local closures with no other strong reference keeping
them alive, so a weak-ref connection would let the garbage collector reclaim
them before a forked worker process ever fires the signal — the handlers
would silently never run. `weak=False` makes the dispatcher hold a strong
reference for the life of the connection instead.

`fetch_di_container(app)` reads the same key back off `app.conf` and returns
the root container.

## Lifecycle

Reopening on `worker_process_init` is idempotent: a fresh `Container` is
already open on construction, and `Container.open` is a no-op when already
open, so firing `worker_process_init` again — a restart, a test re-entry —
reopens a container that was closed on a previous `worker_process_shutdown`
instead of raising an error. This matters because Celery's prefork pool forks
one worker process per configured concurrency slot, and each forked process
fires its own `worker_process_init`/`worker_process_shutdown` pair
independently on the container object it inherited from the fork — the
open/close cycle is scoped per forked worker process, not to the parent
process as a whole.

## Per-task scope

`inject`'s wrapper runs once per task invocation. On each call it:

1. Builds one `Scope.REQUEST` child container via
   `fetch_di_container(current_app).build_child_container(scope=Scope.REQUEST)`,
   entered with a sync `with` — modern-di 3.x's mandatory-open lifecycle means
   a freshly built child is not usable until opened, and `Container.__enter__`
   is what opens it. Unlike a web-framework request, a Celery task carries no
   framework request object to seed as context, so there is no equivalent of a
   "connection provider" here — the child container is built with no context.
2. Resolves every `FromDI` parameter against that child container, then calls
   the original function with the caller's `args`/`kwargs` plus the resolved
   dependencies.
3. Closes the child container via `Container.__exit__` (which calls
   `close_sync()`) when the `with` block exits, so it closes whether the task
   returns normally or raises — including the task error path.

## Resolution

`FromDI` is `modern_di.integrations.from_di` — its marker factory. Calling
`FromDI(dependency)` returns an inert `Marker(dependency)` wrapping a
provider or a bare type; it does nothing on its own. Parameters opt into
injection by annotating them `typing.Annotated[SomeType, FromDI(dependency)]`.

`inject` rewrites a task function's signature at decoration time:

1. `integrations.parse_markers(func)` scans the resolved type hints
   (`typing.get_type_hints(func, include_extras=True)`) for `Annotated`
   parameters carrying a `Marker`.
2. If none are found, the function is returned unchanged — only marked via
   `integrations.mark_injected(func)` — and `inject` short-circuits without
   building a wrapper at all.
3. Otherwise `inject` builds a `wrapper` whose visible signature drops every
   DI parameter (`visible_params`, computed by excluding the DI parameter
   names from the original `inspect.signature(func)`). At call time the
   wrapper resolves every DI parameter via
   `integrations.resolve_markers(container, di_params)` — which calls each
   `Marker.resolve(container)`, itself `container.resolve_dependency(...)`,
   dispatching to `resolve_provider` when `dependency` is a provider
   instance and to `resolve` (by type) otherwise — and calls the original
   function with the DI arguments merged into the caller's `args`/`kwargs`.
4. The wrapper deliberately does **not** use `functools.wraps`. Instead it
   copies just `__name__`, `__qualname__`, `__doc__`, and `__module__` by
   hand, and sets `__signature__` explicitly to the stripped signature — so
   Celery's own argument binding reads the rewritten signature and only
   expects the caller's real arguments, never the DI ones.

Resolution binds the caller's arguments to the visible signature *by name*
(`bound.arguments`), which is what makes injection parameter-order-insensitive.
That by-name call cannot faithfully forward `*args`/`**kwargs`: `Signature.bind`
stores their values under the literal names `"args"`/`"kwargs"`, so
`func(**bound.arguments, ...)` would misroute a variadic payload into a keyword
argument. Rather than silently corrupt arguments, `inject` **rejects at
decoration time** (raises `TypeError`) any task that declares a `VAR_POSITIONAL`
or `VAR_KEYWORD` parameter *alongside* a `FromDI` parameter. A task with no
`FromDI` parameter is returned unchanged (step 2) and may use `*args`/`**kwargs`
freely.

## DITask

`DITask(Task)` is the auto-inject path, used via `task_cls=DITask` on the
`Celery` app or `base=DITask` on an individual task. On `__init__` it checks
`integrations.is_injected(self.run)`; if not already marked, it
wraps `self.run` with `inject`, reassigns the wrapped callable back onto
`self.run`, and resets `self.__header__ = head_from_fun(injected)`. Celery
precomputes `__header__` — the arg-binding header used when a task is
called — from the task function's original signature, so it has to be
recomputed from the rewritten signature after wrapping. Checking
`is_injected` first means a task explicitly decorated with `@inject` and
also based on `DITask` is not wrapped twice.

## Synchronous only

Every lifecycle and resolution step here is synchronous:
`setup_di` calls `container.open()` and `container.close_sync()`, and
`inject`'s wrapper calls `close_sync()`. There is no async counterpart
anywhere in this integration, matching Celery workers themselves being
synchronous. The package requires `celery>=5,<6`.
