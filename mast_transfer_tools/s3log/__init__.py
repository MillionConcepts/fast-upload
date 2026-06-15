"""This submodule contains components related to shared S3 logs for use by the
upload client and validation pipeline."""

from ..utilz import __getattr__impl, ModuleType


def __getattr__(name: str) -> ModuleType:
    return __getattr__impl(name, __name__)
