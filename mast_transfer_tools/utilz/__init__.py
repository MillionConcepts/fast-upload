"""Grab bag of utility functions."""

# written this way so mypy understands it's OK for other modules to
# import ModuleType from here
from types import ModuleType as ModuleType


def __getattr__impl(name: str, parent: str) -> ModuleType:
    """Hook for attribute lookup on modules: attempt to load any
    undefined name as a submodule.  This makes 'import foo; foo.bar'
    work whenever 'import foo.bar' would have."""
    if '.' in name:
        raise AttributeError(f"module '{parent}' has no attribute '{name}'")
    from importlib import import_module
    try:
        mod = import_module("." + name, parent)
        globals()[name] = mod
        return mod
    except ImportError as e:
        raise AttributeError(
            f"module '{parent}' has no attribute '{name}'"
        ) from e


def __getattr__(name: str) -> ModuleType:
    return __getattr__impl(name, __name__)
