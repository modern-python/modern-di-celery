import typing

from celery import Celery

from modern_di_celery import DITask, FromDI, inject
from tests.dependencies import SimpleCreator


def test_ditask_resolves_without_inject(app: Celery) -> None:
    @app.task(base=DITask)
    def sample(y: int, app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)]) -> dict[str, typing.Any]:
        return {"y": y, "dep1": app_instance.dep1}

    assert sample.delay(9).get() == {"y": 9, "dep1": "original"}


def test_ditask_skips_already_injected(app: Celery) -> None:
    @app.task(base=DITask)
    @inject
    def sample(y: int, app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)]) -> dict[str, typing.Any]:
        return {"y": y, "dep1": app_instance.dep1}

    assert sample.delay(4).get() == {"y": 4, "dep1": "original"}
