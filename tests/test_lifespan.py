from celery import Celery, signals
from modern_di import Container

import modern_di_celery
from modern_di_celery import fetch_di_container
from tests.dependencies import Dependencies


def test_fetch_returns_the_same_container(app: Celery) -> None:
    assert isinstance(fetch_di_container(app), Container)


def test_setup_di_returns_the_container() -> None:
    app = Celery("t", broker="memory://", backend="cache+memory://")
    container = Container(groups=[Dependencies], validate=True)
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
