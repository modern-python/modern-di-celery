import typing

from celery import Celery, signals
from modern_di import Container  # providers imported now; used from Task 3 on


# The root container lives on ``app.conf`` under this named key; read back with
# ``current_app.conf`` inside ``inject``. A named constant keeps writer and
# reader in provable agreement.
_ROOT_CONTAINER_KEY = "modern_di_container"


def setup_di(app: Celery, container: Container) -> Container:
    app.conf[_ROOT_CONTAINER_KEY] = container

    def _open_container(**_: typing.Any) -> None:  # noqa: ANN401
        container.open()

    def _close_container(**_: typing.Any) -> None:  # noqa: ANN401
        container.close_sync()

    # weak=False is required: Celery signals default to weak refs, which would
    # garbage-collect these handlers before a worker process ever fires them.
    signals.worker_process_init.connect(_open_container, weak=False)
    signals.worker_process_shutdown.connect(_close_container, weak=False)
    return container


def fetch_di_container(app: Celery) -> Container:
    return typing.cast(Container, app.conf[_ROOT_CONTAINER_KEY])
