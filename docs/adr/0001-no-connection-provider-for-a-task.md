# No connection provider for a task invocation

**Decision:** the per-task child container is built with no context, and this integration registers
no connection provider.

`modern-di` defines a connection as the framework object a unit of work carries — the HTTP request
in the web integrations, the incoming message in the broker ones. Those adapters seed it as the
child container's context so a provider can depend on it, and the question asked of every new
integration is which object plays that role. It is asked here because Celery clearly *has*
per-invocation state: a task id, a retry count, message headers.

That state lives on the `Task` instance, one layer above the seam. `inject` wraps the plain task
function, and `@app.task` sits outside `@inject`, so when the wrapper runs it holds the caller's
arguments and nothing else. Reaching the `Task` would mean either requiring `bind=True` on every
injected task or reading Celery's thread-local current task inside the wrapper — coupling this
package to task-instance internals to supply a context object that no provider it exists to serve
has needed. `modern-di-typer` declined the same thing for the same reason: a command, like a task,
is a plain call.

So the unit of work is the task invocation itself: one `Scope.REQUEST` child per call, built with no
context, closed when the call returns or raises. A dependency that needs task metadata takes it as
an ordinary task parameter, passed by the caller.

**Revisit trigger:** a provider that genuinely needs per-invocation Celery state rather than the
arguments the caller passed. At that point the context object has a concrete consumer, and the
coupling it costs is worth paying.
