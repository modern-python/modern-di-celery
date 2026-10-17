import typing

import pytest
from celery import Celery, signals
from celery.utils.dispatch import Signal
from modern_di import Container, Group, Scope, providers

from modern_di_celery import fetch_di_container, setup_di


class Pool:
    pass


class _FakeWorker:
    def __init__(self, app: Celery) -> None:
        self.app = app


def _container(events: list[str]) -> Container:
    class Resources(Group):
        pool = providers.Factory(
            Pool, scope=Scope.APP, cache=providers.CacheSettings(finalizer=lambda _: events.append("finalized"))
        )

    return Container(groups=[Resources])


def _make_app(main: str) -> Celery:
    app = Celery(main, broker="memory://", backend="cache+memory://")
    app.set_current()
    return app


_WORKER_PAIR = (signals.worker_init, signals.worker_shutdown, True)
_PROCESS_PAIR = (signals.worker_process_init, signals.worker_process_shutdown, False)
_PAIRS = pytest.mark.parametrize(
    ("init", "shutdown", "sent_by_worker"), [_WORKER_PAIR, _PROCESS_PAIR], ids=["worker", "process"]
)


def _cycle(app: Celery, init: Signal, shutdown: Signal, *, sent_by_worker: bool) -> None:
    sender = _FakeWorker(app) if sent_by_worker else None
    init.send(sender=sender)
    fetch_di_container(app).resolve(Pool)
    shutdown.send(sender=sender)


@_PAIRS
def test_root_closes_after_shutdown_receivers_connected_after_setup_di(
    init: Signal, shutdown: Signal, sent_by_worker: bool
) -> None:
    events: list[str] = []
    app = _make_app(f"late-receiver-{shutdown.name}")
    container = setup_di(app, _container(events))

    def hook(**_: typing.Any) -> None:  # noqa: ANN401
        container.resolve(Pool)
        events.append("user")

    shutdown.connect(hook, weak=False)
    try:
        _cycle(app, init, shutdown, sent_by_worker=sent_by_worker)
    finally:
        shutdown.disconnect(hook)

    assert events == ["user", "finalized"]
    assert container.closed is True


def _receiver_counts(*watched: Signal) -> list[int]:
    return [len(signal.receivers or ()) for signal in watched]


@_PAIRS
def test_restarts_do_not_add_shutdown_receivers(init: Signal, shutdown: Signal, sent_by_worker: bool) -> None:
    events: list[str] = []
    app = _make_app(f"restart-{shutdown.name}")
    setup_di(app, _container(events))
    receivers_after_setup = _receiver_counts(init, shutdown)

    _cycle(app, init, shutdown, sent_by_worker=sent_by_worker)
    _cycle(app, init, shutdown, sent_by_worker=sent_by_worker)

    assert _receiver_counts(init, shutdown) == receivers_after_setup
    assert events == ["finalized", "finalized"]


@_PAIRS
def test_manage_lifespan_false_still_neither_opens_nor_closes_the_root(
    init: Signal, shutdown: Signal, sent_by_worker: bool
) -> None:
    events: list[str] = []
    app = _make_app(f"unmanaged-{shutdown.name}")
    container = setup_di(app, _container(events), manage_lifespan=False)
    container.close_sync()

    sender = _FakeWorker(app) if sent_by_worker else None
    init.send(sender=sender)
    assert container.closed is True

    container.open()
    container.resolve(Pool)
    shutdown.send(sender=sender)
    assert container.closed is False
    assert events == []
