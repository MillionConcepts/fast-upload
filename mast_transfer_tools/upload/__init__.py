"""This submodule contains all of the components used exclusively by
the mast-upload tool."""

from ..utilz import __getattr__impl, ModuleType


def __getattr__(name: str) -> ModuleType:
    return __getattr__impl(name, __name__)
