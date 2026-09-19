# No connection provider for a task invocation

`modern-di` seeds a child container with the framework object a unit of work carries, the HTTP
request in the web integrations, the incoming message in the broker ones, so every integration must
name that object. Celery's per-invocation state, the task id, retry count and message headers, lives
on the `Task` instance, one layer above the seam: `inject` wraps the plain task function and
`@app.task` sits outside it, so the wrapper sees only the caller's arguments. Reaching the `Task`
would mean forcing `bind=True` on every injected task or reading Celery's thread-local current task,
coupling this package to task internals for a context object no provider needs; `modern-di-typer`
declined the same for a command. The unit of work is therefore the invocation: one `Scope.REQUEST`
child per call, built with no context, and a dependency needing task metadata takes it as an ordinary
task parameter.
