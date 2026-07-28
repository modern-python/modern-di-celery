# Minimal modern-di + celery example.
# Run for real (point broker/backend at Redis/RabbitMQ/etc.):
#   celery -A examples.app worker --loglevel=info
import dataclasses
import typing

from celery import Celery
from modern_di import Container, Group, Scope, providers

from modern_di_celery import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True)
class Settings:
    greeting: str = "Hello"


@dataclasses.dataclass(kw_only=True)
class GreetingService:
    settings: Settings  # auto-injected by type

    def greet(self, name: str) -> str:
        return f"{self.settings.greeting}, {name}!"


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)
    service = providers.Factory(scope=Scope.REQUEST, creator=GreetingService)


app = Celery("examples", broker="memory://", backend="cache+memory://")
container = Container(groups=[Dependencies])
setup_di(app, container)
container.validate()  # optional fail-fast; must come after setup_di registers its providers


@app.task
@inject
def greet(name: str, service: typing.Annotated[GreetingService, FromDI(Dependencies.service)]) -> str:
    return service.greet(name)
