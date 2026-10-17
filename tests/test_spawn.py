import pickle
import typing

from celery import Celery, current_app, signals
from modern_di import Container

from modern_di_celery import fetch_di_container, setup_di
from tests.dependencies import Dependencies


def _make_app(main: str, set_as_current: bool = True) -> Celery:
    return Celery(main, broker="memory://", backend="cache+memory://", set_as_current=set_as_current)


def test_a_configured_app_survives_a_pickle_round_trip() -> None:
    app = _make_app("pickled")
    setup_di(app, Container(groups=[Dependencies]))

    assert isinstance(pickle.loads(pickle.dumps(app)), Celery)  # noqa: S301


def test_main_survives_a_pickle_round_trip() -> None:
    app = _make_app("pickled-main")
    setup_di(app, Container(groups=[Dependencies]))

    assert pickle.loads(pickle.dumps(app)).main == "pickled-main"  # noqa: S301


def test_a_spawn_child_binds_the_recreated_container_to_its_current_app() -> None:
    payload = pickle.dumps(_make_app("spawn-child", set_as_current=False))
    unpickled = pickle.loads(payload)  # noqa: S301
    recreated = _make_app("spawn-child", set_as_current=False)
    container = setup_di(recreated, Container(groups=[Dependencies]))
    container.close_sync()
    unpickled.set_current()

    signals.worker_process_init.send(sender=None)

    assert fetch_di_container(typing.cast(Celery, current_app)) is container
    assert container.closed is False


def test_apps_with_different_main_names_keep_their_own_containers() -> None:
    alpha = _make_app("alpha", set_as_current=False)
    beta = _make_app("beta", set_as_current=False)
    alpha_container = setup_di(alpha, Container(groups=[Dependencies]))
    beta_container = setup_di(beta, Container(groups=[Dependencies]))
    pickle.loads(pickle.dumps(alpha)).set_current()  # noqa: S301

    signals.worker_process_init.send(sender=None)

    assert fetch_di_container(typing.cast(Celery, current_app)) is alpha_container
    assert fetch_di_container(alpha) is alpha_container
    assert fetch_di_container(beta) is beta_container


def test_an_app_with_a_container_keeps_it_when_a_later_handler_fires() -> None:
    current = _make_app("shared-main")
    later = _make_app("shared-main", set_as_current=False)
    current_container = setup_di(current, Container(groups=[Dependencies]))
    setup_di(later, Container(groups=[Dependencies]))

    signals.worker_process_init.send(sender=None)

    assert fetch_di_container(current) is current_container
