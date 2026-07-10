import pytest
from celery import Celery
from modern_di import Container

from modern_di_celery import setup_di
from tests.dependencies import Dependencies


@pytest.fixture
def app() -> Celery:
    app_ = Celery("test", broker="memory://", backend="cache+memory://")
    app_.conf.task_always_eager = True
    app_.conf.task_store_eager_result = True
    setup_di(app_, container=Container(groups=[Dependencies], validate=True))
    return app_
