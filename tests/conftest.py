import typing

import pytest
from celery import Celery, current_app
from modern_di import Container

from modern_di_celery import setup_di
from tests.dependencies import Dependencies


@pytest.fixture(autouse=True)
def _restore_current_app() -> typing.Iterator[None]:
    previous = current_app._get_current_object()  # noqa: SLF001
    yield
    previous.set_current()


@pytest.fixture
def app() -> Celery:
    app_ = Celery("test", broker="memory://", backend="cache+memory://")
    app_.conf.task_always_eager = True
    app_.conf.task_store_eager_result = True
    container = setup_di(app_, container=Container(groups=[Dependencies]))
    # worker_process_init (which opens the container in production) doesn't fire
    # under task_always_eager; open it here so the suite exercises the real path.
    container.open()
    return app_
