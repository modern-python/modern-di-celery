# `inject` rejects `*args`/`**kwargs` alongside a `FromDI` parameter

Decorating a function that declares a variadic parameter *and* at least one `FromDI` parameter
raises `TypeError` at decoration time; a function with no `FromDI` parameter is returned unchanged
and may use variadics freely. The wrapper binds the caller's arguments to the visible signature and
calls by name, `func(**bound.arguments, **resolved)`, which is what makes injection insensitive to
where a `FromDI` parameter sits. By-name calling cannot forward a variadic: `Signature.bind` stores
the payload under the literal parameter names, so a task called with three positional arguments
receives one tuple named `args`. Forwarding positionally would surrender order insensitivity for
every task, and special-casing the two names misroutes again once a task declares a real parameter
called `args`. For the same reason the wrapper sets `__name__`, `__qualname__`, `__doc__` and
`__module__` by hand rather than using `functools.wraps`, whose `__wrapped__` points
`inspect.signature` back at the un-rewritten signature.
