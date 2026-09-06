import types

import modern_di_celery


def test_public_surface_is_exactly_the_five_documented_symbols() -> None:
    """INVARIANT: the exports are exactly ``setup_di``, ``fetch_di_container``, ``FromDI``, ``inject`` and ``DITask``.

    Broken by promoting a helper to a public name, in ``__all__`` or as an unprefixed binding in
    ``__init__`` -- the latter is public whether or not it was meant to be. These five are the whole
    semver contract of the integration: each is a name a major release has to keep working, and the
    README's API table is written against exactly this set. The surface is the only place the cost
    of a new name is visible before it is paid.
    """
    public = sorted(
        name
        for name, value in vars(modern_di_celery).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    )

    assert public == ["DITask", "FromDI", "fetch_di_container", "inject", "setup_di"]
    assert modern_di_celery.__all__ == public
