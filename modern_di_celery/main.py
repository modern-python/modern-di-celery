import dataclasses
import inspect
import typing

from celery import Celery, Task, current_app, signals
from celery.utils.functional import head_from_fun
from modern_di import Container, Scope, providers


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


T = typing.TypeVar("T")
T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(slots=True, frozen=True)
class _FromDI(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]


def FromDI(dependency: providers.AbstractProvider[T] | type[T]) -> T:  # noqa: N802
    return typing.cast(T, _FromDI(dependency))


def _parse_inject_params(func: typing.Callable[..., typing.Any]) -> dict[str, _FromDI[typing.Any]]:
    hints = typing.get_type_hints(func, include_extras=True)
    di_params: dict[str, _FromDI[typing.Any]] = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        if typing.get_origin(hint) is typing.Annotated:
            for meta in typing.get_args(hint)[1:]:
                if isinstance(meta, _FromDI):
                    di_params[name] = meta
                    break
    return di_params


def inject(func: typing.Callable[..., T]) -> typing.Callable[..., T]:
    di_params = _parse_inject_params(func)
    if not di_params:
        func.__modern_di_injected__ = True  # ty: ignore[unresolved-attribute]
        return func

    signature = inspect.signature(func)
    for name, param in signature.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            func_name = getattr(func, "__qualname__", repr(func))
            msg = (
                f"@inject task {func_name!r} declares *args/**kwargs (parameter {name!r}), "
                "which is unsupported; use explicit named parameters instead of *args/**kwargs with @inject."
            )
            raise TypeError(msg)
    visible_params = [p for name, p in signature.parameters.items() if name not in di_params]
    visible_signature = signature.replace(parameters=visible_params)

    def wrapper(*args: typing.Any, **kwargs: typing.Any) -> T:  # noqa: ANN401
        container = fetch_di_container(typing.cast(Celery, current_app)).build_child_container(scope=Scope.REQUEST)
        try:
            resolved = {name: container.resolve_dependency(marker.dependency) for name, marker in di_params.items()}
            bound = visible_signature.bind(*args, **kwargs)
            bound.apply_defaults()
            return func(**bound.arguments, **resolved)
        finally:
            container.close_sync()

    # NOT functools.wraps — keep Celery's arg-binding reading the stripped signature.
    wrapper.__name__ = func.__name__  # ty: ignore[unresolved-attribute]
    wrapper.__qualname__ = func.__qualname__  # ty: ignore[unresolved-attribute]
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__signature__ = visible_signature  # ty: ignore[unresolved-attribute]
    wrapper.__modern_di_injected__ = True  # ty: ignore[unresolved-attribute]
    return wrapper


class DITask(Task):
    def __init__(self) -> None:
        super().__init__()
        if not getattr(self.run, "__modern_di_injected__", False):
            injected = inject(self.run)
            self.run = injected  # ty: ignore[invalid-assignment]
            self.__header__ = head_from_fun(injected)
