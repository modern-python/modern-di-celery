import typing

import pytest
from celery import Celery
from modern_di import Container, Group, Scope, providers

from modern_di_celery import FromDI, inject, setup_di
from tests.dependencies import Dependencies, DependentCreator, SimpleCreator


def test_inject_resolves_app_and_request(app: Celery) -> None:
    @app.task
    @inject
    def sample(
        x: int,
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        request_instance: typing.Annotated[DependentCreator, FromDI(Dependencies.request_factory)],
    ) -> dict[str, typing.Any]:
        return {
            "x": x,
            "app_ok": isinstance(app_instance, SimpleCreator),
            "request_ok": isinstance(request_instance, DependentCreator),
            "distinct": request_instance.dep1 is not app_instance,
        }

    # caller passes ONLY the real arg x; the DI params must not be required
    assert sample.delay(7).get() == {"x": 7, "app_ok": True, "request_ok": True, "distinct": True}


def test_inject_resolves_with_di_param_declared_first(app: Celery) -> None:
    @app.task
    @inject
    def sample(
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        x: int,
    ) -> dict[str, typing.Any]:
        return {"x": x, "dep1": app_instance.dep1}

    # caller passes only the real positional arg; the leading FromDI param must not collide
    assert sample.delay(7).get() == {"x": 7, "dep1": "original"}


def test_inject_is_noop_without_fromdi(app: Celery) -> None:
    @app.task
    @inject
    def sample(x: int) -> int:
        return x * 2

    assert sample.delay(5).get() == 10  # noqa: PLR2004


def test_child_closed_on_task_error() -> None:
    teardowns: list[str] = []

    class Boom(Group):
        resource = providers.Factory(
            scope=Scope.REQUEST,
            creator=SimpleCreator,
            kwargs={"dep1": "x"},
            bound_type=None,
            cache=providers.CacheSettings(finalizer=lambda _: teardowns.append("closed")),
        )

    app = Celery("boom", broker="memory://", backend="cache+memory://")
    app.conf.task_always_eager = True
    app.conf.task_store_eager_result = True
    boom_container = setup_di(app, Container(groups=[Boom], validate=True))
    boom_container.open()

    @app.task
    @inject
    def sample(_res: typing.Annotated[SimpleCreator, FromDI(Boom.resource)]) -> None:
        msg = "boom"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="boom"):
        sample.delay().get()
    assert teardowns == ["closed"]  # per-task child closed (finalizer ran) on the error path


def test_inject_rejects_var_positional_with_fromdi() -> None:
    def bad_task(
        _svc: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        *args: int,
    ) -> tuple[int, ...]:
        return args  # pragma: no cover

    with pytest.raises(TypeError):
        inject(bad_task)


def test_inject_rejects_var_keyword_with_fromdi() -> None:
    def bad_task(
        _svc: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        **kwargs: int,
    ) -> dict[str, int]:
        return kwargs  # pragma: no cover

    with pytest.raises(TypeError):
        inject(bad_task)
