from examples.app import app, container, greet


def test_example_greets() -> None:
    # Other test modules construct their own Celery apps, which silently steals
    # celery's thread-local "current app" (@inject resolves via current_app);
    # reclaim it so this task resolves from the example's own container.
    app.set_current()
    app.conf.task_always_eager = True
    app.conf.task_store_eager_result = True
    # worker_process_init (which opens the container in production) doesn't fire
    # under task_always_eager; open it here so the task can resolve.
    container.open()

    assert greet.delay("world").get() == "Hello, world!"
