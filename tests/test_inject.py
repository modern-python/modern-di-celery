import inspect
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


def test_a_fromdi_parameter_is_absent_from_the_signature_celery_binds_against(app: Celery) -> None:
    """INVARIANT: the callable ``inject`` returns advertises only the task's real parameters.

    Broken by dropping the explicit ``__signature__`` assignment, or by reaching for
    ``functools.wraps`` instead of copying the four dunders by hand: ``inspect.signature`` then
    follows ``__wrapped__`` back to the undecorated function and every ``FromDI`` parameter
    reappears in the task's public API, which callers must then supply. The wrapper accepts
    ``*args``/``**kwargs`` and re-binds them itself, so a correct call still runs under the
    violation and every other test here keeps passing. What moves is where a *wrong* call is
    caught: Celery checks arity against the task header in the caller's process, so with the
    rewrite a bad call raises at ``.delay()``, and without it the call is accepted, serialized and
    dispatched, and dies on a worker.
    """

    @app.task
    @inject
    def sample(x: int, app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)]) -> str:
        return f"{x}:{app_instance.dep1}"

    assert list(inspect.signature(sample.run).parameters) == ["x"]
    assert sample.delay(7).get() == "7:original"
    with pytest.raises(TypeError):
        sample.delay(7, "surplus")


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
    boom_container = setup_di(app, Container(groups=[Boom]))
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
