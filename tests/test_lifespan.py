import asyncio
import typing

from celery import Celery, signals
from modern_di import Container, Group, Scope, providers

import modern_di_celery
from modern_di_celery import FromDI, fetch_di_container, inject
from tests.dependencies import Dependencies, DependentCreator, SimpleCreator


def test_fetch_returns_the_same_container(app: Celery) -> None:
    assert isinstance(fetch_di_container(app), Container)


def test_setup_di_returns_the_container() -> None:
    app = Celery("t", broker="memory://", backend="cache+memory://")
    container = Container(groups=[Dependencies])
    assert modern_di_celery.setup_di(app, container) is container


def test_worker_signals_open_and_close(app: Celery) -> None:
    container = fetch_di_container(app)
    container.close_sync()
    assert container.closed is True
    signals.worker_process_init.send(sender=None)  # eager mode never spawns a worker; send directly
    assert container.closed is False
    signals.worker_process_shutdown.send(sender=None)
    assert container.closed is True


def test_restart_reopens_without_error(app: Celery) -> None:
    container = fetch_di_container(app)
    signals.worker_process_shutdown.send(sender=None)
    assert container.closed is True
    signals.worker_process_init.send(sender=None)  # second cycle must not raise ContainerClosedError
    assert container.closed is False


def test_worker_init_opens_container_for_non_forking_pools() -> None:
    # gevent/eventlet/threads run in the main worker process and never fire
    # worker_process_init — only worker_init. Use a fresh app/container (not the
    # `app` fixture, which auto-opens) so this proves the signal opens it.
    non_forking_app = Celery("non-forking", broker="memory://", backend="cache+memory://")
    non_forking_app.conf.task_always_eager = True
    non_forking_app.conf.task_store_eager_result = True
    container = modern_di_celery.setup_di(non_forking_app, Container(groups=[Dependencies]))
    # modern-di 3.1 builds containers open, so close it first — otherwise "the signal opens it"
    # is not observable and the assertion below would pass without the signal doing anything.
    container.close_sync()
    assert container.closed is True

    signals.worker_init.send(sender=None)  # no worker_process_init: simulates gevent/eventlet/threads
    assert container.closed is False

    @non_forking_app.task
    @inject
    def sample(
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        request_instance: typing.Annotated[DependentCreator, FromDI(Dependencies.request_factory)],
    ) -> bool:
        return isinstance(app_instance, SimpleCreator) and isinstance(request_instance, DependentCreator)

    assert sample.delay().get() is True

    signals.worker_shutdown.send(sender=None)
    assert container.closed is True


class _FakeWorker:
    def __init__(self, app: Celery) -> None:
        self.app = app


def _make_app(main: str) -> Celery:
    return Celery(main, broker="memory://", backend="cache+memory://", set_as_current=False)


def test_worker_signals_act_only_on_the_senders_app() -> None:
    app_a = _make_app("worker-a")
    app_b = _make_app("worker-b")
    container_a = modern_di_celery.setup_di(app_a, Container(groups=[Dependencies]))
    container_b = modern_di_celery.setup_di(app_b, Container(groups=[Dependencies]))
    worker_a = _FakeWorker(app_a)

    signals.worker_shutdown.send(sender=worker_a)
    assert (container_a.closed, container_b.closed) == (True, False)

    container_b.close_sync()
    signals.worker_init.send(sender=worker_a)
    assert (container_a.closed, container_b.closed) == (False, True)


def test_process_signals_act_only_on_the_current_app() -> None:
    app_a = _make_app("process-a")
    app_b = _make_app("process-b")
    container_a = modern_di_celery.setup_di(app_a, Container(groups=[Dependencies]))
    container_b = modern_di_celery.setup_di(app_b, Container(groups=[Dependencies]))
    app_a.set_current()

    signals.worker_process_shutdown.send(sender=None)
    assert (container_a.closed, container_b.closed) == (True, False)

    container_b.close_sync()
    signals.worker_process_init.send(sender=None)
    assert (container_a.closed, container_b.closed) == (False, True)


class _AppResource:
    pass


class _TaskResource:
    pass


def _tracked_container(finalized: list[str]) -> Container:
    class Tracked(Group):
        app_resource = providers.Factory(
            _AppResource,
            scope=Scope.APP,
            cache=providers.CacheSettings(finalizer=lambda _: finalized.append("app")),
        )
        task_resource = providers.Factory(
            _TaskResource,
            scope=Scope.REQUEST,
            cache=providers.CacheSettings(finalizer=lambda _: finalized.append("task")),
        )

    return Container(groups=[Tracked])


def _unmanaged_app(main: str, container: Container) -> Celery:
    app = Celery(main, broker="memory://", backend="cache+memory://")
    app.conf.task_always_eager = True
    app.conf.task_store_eager_result = True
    modern_di_celery.setup_di(app, container, manage_lifespan=False)

    @app.task(name="uses_both_scopes")
    @inject
    def uses_both_scopes(
        app_resource: typing.Annotated[_AppResource, FromDI(_AppResource)],
        task_resource: typing.Annotated[_TaskResource, FromDI(_TaskResource)],
    ) -> bool:
        return isinstance(app_resource, _AppResource) and isinstance(task_resource, _TaskResource)

    return app


def _run_worker_lifecycle(app: Celery) -> bool:
    worker = _FakeWorker(app)
    signals.worker_init.send(sender=worker)
    signals.worker_process_init.send(sender=None)
    result = app.tasks["uses_both_scopes"].delay().get()
    signals.worker_process_shutdown.send(sender=None)
    signals.worker_shutdown.send(sender=worker)
    return result


def test_manage_lifespan_false_leaves_the_root_open_and_unfinalized() -> None:
    finalized: list[str] = []
    container = _tracked_container(finalized)
    app = _unmanaged_app("unmanaged-lifecycle", container)

    assert _run_worker_lifecycle(app) is True
    assert container.closed is False
    assert finalized == ["task"]


def test_manage_lifespan_false_never_opens_the_root() -> None:
    container = _tracked_container([])
    app = _unmanaged_app("unmanaged-closed", container)
    container.close_sync()

    signals.worker_init.send(sender=_FakeWorker(app))
    signals.worker_process_init.send(sender=None)

    assert container.closed is True


def test_manage_lifespan_false_lets_the_user_own_the_root() -> None:
    finalized: list[str] = []
    container = _tracked_container(finalized)
    app = _unmanaged_app("unmanaged-owned", container)

    async def run() -> bool:
        async with container:
            result = _run_worker_lifecycle(app)
            assert finalized == ["task"]
        return result

    assert asyncio.run(run()) is True
    assert container.closed is True
    assert finalized == ["task", "app"]
