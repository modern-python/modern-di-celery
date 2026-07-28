import typing

from celery import Celery, signals
from modern_di import Container

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
