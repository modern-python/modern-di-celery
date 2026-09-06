# `setup_di` connects both worker signal pairs

**Decision:** `setup_di` connects the same open/close closures to
`worker_process_init`/`worker_process_shutdown` *and* to `worker_init`/`worker_shutdown` — four
connections for two operations, all with `weak=False`.

Four connections running two closures looks like duplication, and the obvious edit is to keep one
pair. Neither pair alone is sufficient, because they cover different pool families.

`worker_process_init`/`worker_process_shutdown` fire only under the prefork and solo pools, once per
forked child under prefork. That per-child open/close is what keeps cached resources and finalizers
fork-safe: a forked process gets its own open container rather than inheriting one whose cached
values were created before the fork. `worker_init`/`worker_shutdown` fire once in the main worker
process for every pool, and are the *only* pair the gevent, eventlet and threads pools send, because
those pools run tasks in the main process and never fork.

Shipping only the per-process pair is what 3.0.1 had to fix: under `modern-di` 3.x's mandatory-open
lifecycle the root container was never opened under the non-forking pools, and every `@inject` task
raised. Shipping only the worker pair would leave prefork children sharing state opened before the
fork. The overlap under prefork and solo is therefore deliberate and harmless: `Container.open()` is
a no-op on an already-open container, and `close_sync()` is a no-op when nothing was cached.

`weak=False` is part of the same decision, not a style choice. Celery's signal dispatcher holds
receivers by weak reference by default, and these closures are local to `setup_di` with no other
strong reference to keep them alive — a weak connection lets them be collected before any worker
fires the signal, and the handlers then silently never run. The failure is invisible in eager tests
and total in a real worker.

**Revisit trigger:** Celery changes which pools emit which of the four signals, or adds a pool family
that emits neither pair.
