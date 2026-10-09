# `setup_di` connects both worker signal pairs

`setup_di` connects the same open/close closures to `worker_process_init`/`worker_process_shutdown`
*and* to `worker_init`/`worker_shutdown`, four connections for two operations, because neither pair
alone covers every pool. The process pair fires only under prefork and solo, once per forked child,
keeping cached resources and finalizers fork-safe; the worker pair fires once in the main process and
is the only pair the gevent, eventlet and threads pools send, since those never fork. Connecting only
the process pair is the bug 3.0.1 fixed. `modern-di` 3.0 raised on a resolve from a closed container,
and 4.x does again, so under the non-forking pools the root container stayed closed and every
`@inject` task raised. The overlap is harmless: `open()` is a no-op on an open container,
`close_sync()` when nothing was cached.
`weak=False` belongs to the same decision: Celery holds receivers weakly by default and these
closures have no other strong reference, so a weak connection lets them be collected and the handlers
never run.
