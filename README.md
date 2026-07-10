# modern-di-celery

[Modern-DI](https://github.com/modern-python/modern-di) integration for [Celery](https://docs.celeryq.dev) 5.x.

## Quickstart

```python
import typing

from celery import Celery
from modern_di import Container, Group, Scope, providers
from modern_di_celery import DITask, FromDI, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)


app = Celery("myapp", broker="redis://localhost", task_cls=DITask)
setup_di(app, Container(groups=[Dependencies], validate=True))


@app.task
def greet(name: str, settings: typing.Annotated[Settings, FromDI(Dependencies.settings)]) -> str:
    return f"{settings.greeting}, {name}"
```

With `task_cls=DITask` every task is injected; alternatively decorate individual
tasks with `@inject`. See the [documentation](https://modern-di.modern-python.org).
