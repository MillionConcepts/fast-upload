"""Tools for working with MAST, the Mikulski Archive for Space Telescopes."""

from .utilz import __getattr__impl, ModuleType


def __getattr__(name: str) -> ModuleType:
    return __getattr__impl(name, __name__)
