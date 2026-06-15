"""This submodule contains all of the components used exclusively by
the AWS lambdas needed by the MAST upload server."""

from ..utilz import __getattr__impl, ModuleType


def __getattr__(name: str) -> ModuleType:
    return __getattr__impl(name, __name__)
