import inspect
import typing
import weakref

from celery import Celery, Task, current_app, signals
from celery.local import Proxy
from celery.utils.functional import head_from_fun
from modern_di import Container, Scope, integrations


_ROOT_CONTAINERS: "weakref.WeakKeyDictionary[Celery, Container]" = weakref.WeakKeyDictionary()


def _real_app(app: Celery) -> Celery:
    if isinstance(app, Proxy):
        return typing.cast(Celery, app._get_current_object())  # noqa: SLF001
    return app


def _current_app() -> Celery:
    return _real_app(typing.cast(Celery, current_app))


def _worker_app(sender: object) -> Celery:
    app = getattr(sender, "app", None)
    return _current_app() if app is None else _real_app(app)


def _bind_current_app(main: str | None, container: Container) -> Celery:
    process_app = _current_app()
    if process_app.main == main:
        _ROOT_CONTAINERS.setdefault(process_app, container)
    return process_app


def setup_di(app: Celery, container: Container) -> Container:
    _ROOT_CONTAINERS[app] = container
    main = app.main

    def _owns(owner: Celery) -> bool:
        return _ROOT_CONTAINERS.get(owner) is container

    def _open_for_worker(sender: object = None, **_: typing.Any) -> None:  # noqa: ANN401
        if _owns(_worker_app(sender)):
            container.open()

    def _close_for_worker(sender: object = None, **_: typing.Any) -> None:  # noqa: ANN401
        if _owns(_worker_app(sender)):
            container.close_sync()

    def _open_for_process(**_: typing.Any) -> None:  # noqa: ANN401
        if _owns(_bind_current_app(main, container)):
            container.open()

    def _close_for_process(**_: typing.Any) -> None:  # noqa: ANN401
        if _owns(_current_app()):
            container.close_sync()

    # weak=False is required: Celery signals default to weak refs, which would
    # garbage-collect these handlers before a worker process ever fires them.
    #
    # worker_process_init/worker_process_shutdown fire only under the prefork and
    # solo pools; worker_init/worker_shutdown fire once in the main worker process
    # for all pools, and are the only pair gevent/eventlet/threads send. The
    # overlap is harmless: open() is a no-op on an open container, close_sync()
    # when nothing was cached.
    #
    # Each handler acts only when its app owns this container: the worker's app
    # for the worker pair, the process's current app for the process pair. A
    # spawn child makes an unpickled copy of the app current and re-runs
    # setup_di on a new app object, so the process-init handler first binds its
    # container to that copy by main name, unless the copy already has one.
    signals.worker_process_init.connect(_open_for_process, weak=False)
    signals.worker_process_shutdown.connect(_close_for_process, weak=False)
    signals.worker_init.connect(_open_for_worker, weak=False)
    signals.worker_shutdown.connect(_close_for_worker, weak=False)
    return container


def fetch_di_container(app: Celery) -> Container:
    try:
        return _ROOT_CONTAINERS[_real_app(app)]
    except KeyError:
        msg = (
            "No modern-di container found on the app. "
            "Call setup_di(app, container) before using @inject or fetch_di_container."
        )
        raise RuntimeError(msg) from None


T = typing.TypeVar("T")


FromDI = integrations.from_di


def inject(func: typing.Callable[..., T]) -> typing.Callable[..., T]:
    di_params = integrations.parse_markers(func)
    if not di_params:
        integrations.mark_injected(func)
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
        with fetch_di_container(typing.cast(Celery, current_app)).build_child_container(
            scope=Scope.REQUEST
        ) as container:
            resolved = integrations.resolve_markers(container, di_params)
            bound = visible_signature.bind(*args, **kwargs)
            bound.apply_defaults()
            return func(**bound.arguments, **resolved)

    # NOT functools.wraps — keep Celery's arg-binding reading the visible signature.
    wrapper.__name__ = func.__name__  # ty: ignore[unresolved-attribute]
    wrapper.__qualname__ = func.__qualname__  # ty: ignore[unresolved-attribute]
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__signature__ = visible_signature  # ty: ignore[unresolved-attribute]
    integrations.mark_injected(wrapper)
    return wrapper


class DITask(Task):
    def __init__(self) -> None:
        super().__init__()
        if not integrations.is_injected(self.run):
            injected = inject(self.run)
            self.run = injected  # ty: ignore[invalid-assignment]
            self.__header__ = head_from_fun(injected)
