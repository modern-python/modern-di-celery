<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/modern-di-celery/lockup-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/modern-di-celery/lockup-light.svg">
    <img alt="modern-di-celery" src="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/modern-di-celery/lockup.png" width="420">
  </picture>
</p>

[![PyPI version](https://img.shields.io/pypi/v/modern-di-celery.svg)](https://pypi.org/project/modern-di-celery/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/modern-di-celery.svg)](https://pypi.org/project/modern-di-celery/)
[![Downloads](https://static.pepy.tech/badge/modern-di-celery/month)](https://pepy.tech/projects/modern-di-celery)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/modern-python/modern-di-celery/actions/workflows/ci.yml)
[![CI](https://github.com/modern-python/modern-di-celery/actions/workflows/ci.yml/badge.svg)](https://github.com/modern-python/modern-di-celery/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/modern-python/modern-di-celery.svg)](https://github.com/modern-python/modern-di-celery/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di-celery)](https://github.com/modern-python/modern-di-celery/stargazers)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

[Modern-DI](https://github.com/modern-python/modern-di) integration for [Celery](https://docs.celeryq.dev) 5.x.

Full guide: [Celery integration docs](https://modern-di.modern-python.org/integrations/celery/)

Usage example: [examples/](./examples)

## Installation

```bash
uv add modern-di-celery      # or: pip install modern-di-celery
```

## Usage

`setup_di` stores the container on `app.conf` and registers `worker_process_init`/`worker_process_shutdown` handlers that open/close it once per worker process. `@inject` builds a `Scope.REQUEST` child container per task call and resolves the `FromDI`-marked parameters from it; alternatively set `task_cls=DITask` to inject every task without a per-task decorator.

```python
import typing

from celery import Celery
from modern_di import Container, Group, Scope, providers
from modern_di_celery import FromDI, inject, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class Greeter:
    def __init__(self, settings: Settings) -> None:  # auto-injected by type
        self._settings = settings

    def greet(self, name: str) -> str:
        return f"{self._settings.greeting}, {name}"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)
    greeter = providers.Factory(Greeter, scope=Scope.REQUEST)


app = Celery("myapp", broker="redis://localhost")
setup_di(app, Container(groups=[AppGroup], validate=True))


@app.task
@inject
def greet(
    name: str,
    greeter: typing.Annotated[Greeter, FromDI(Greeter)],  # resolve by type
) -> str:
    return greeter.greet(name)
```

The `worker_process_init`/`worker_process_shutdown` signals fire only when a real `celery worker` process starts and stops, so a script or test that runs tasks eagerly (`task_always_eager = True`) must drive the container lifecycle itself — send those signals or open/close the container directly. Celery tasks are sync, so REQUEST-scoped finalizers run via `close_sync()`; there is no framework request/message object, so no context provider is registered.

## API

| Symbol | Description |
|---|---|
| `setup_di(app, container)` | Stores the APP-scope container on `app.conf` and opens/closes it on `worker_process_init`/`worker_process_shutdown`. Returns the container |
| `FromDI(dependency)` | Inert marker for `Annotated[T, FromDI(...)]` in task signatures; accepts a provider instance or a type |
| `inject(task)` | Decorator that builds a `Scope.REQUEST` child per call, resolves the `FromDI`-annotated parameters, and closes the child with `close_sync()` afterwards |
| `DITask` | `Task` subclass that applies `@inject` to a task's `run` automatically; pass `task_cls=DITask` to `Celery(...)` or `base=DITask` to `@app.task(...)` |
| `fetch_di_container(app)` | Returns the APP-scope container registered with the Celery app |

## 📦 [PyPI](https://pypi.org/project/modern-di-celery)

## 📝 [License](LICENSE)

## Part of `modern-python`

Built on [`modern-di`](https://github.com/modern-python/modern-di), a dependency-injection framework with IoC container and scopes.

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python) — see the org profile for the categorized index.
