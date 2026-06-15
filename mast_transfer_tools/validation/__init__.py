"""
Validation of data files against their labels.
"""
from functools import cache
from importlib import import_module
from pathlib import Path
from typing import Callable, TYPE_CHECKING, Any

from asdf._asdf import AsdfFile
from astropy.io.fits import HDUList
from hostess.aws.s3 import Bucket
from pyarrow.parquet import ParquetFile

from mast_transfer_tools.labels import (
    Filetype, STANDARDS_SUPPORTING_DATA_VALIDATION
)


class ValidationNotSupported(NotImplementedError):
    """File-level validation isn't supported for this file standard."""


ObjectChecker = Callable[[Any, Filetype], dict]


def validator_for(standard: str) -> ObjectChecker:
    if standard not in STANDARDS_SUPPORTING_DATA_VALIDATION:
        raise ValidationNotSupported(
            f"No file-level validation available for {standard} files."
        )
    if standard == "fits":
        from .fits import check_file
    elif standard == "parquet":
        from .parquet import check_file
    elif standard == "asdf":
        from .asdf import check_file
    else:
        raise NotImplementedError(
            f"Validator not yet implemented for {standard}"
        )
    return check_file


@cache
def load_object_check_hook(module_name: str) -> ObjectChecker:
    module = import_module(module_name)
    checker = getattr(module, "check_file", None)
    if not callable(checker):
        raise TypeError(
            f"{module_name!r} must define callable check_file(data, spec)"
        )
    return checker


def object_checkers_for(
    ft: Filetype, *, object_check_hook: bool = True
) -> list[tuple[str, ObjectChecker]]:
    checkers = []

    if len(ft.objects) != 0:
        checkers.append(("standard", validator_for(ft.standard)))

    hook_module = getattr(ft.validation_options, "object_check_hook", None)
    if (
        object_check_hook
        and hook_module is not None
        and "hook" not in ft.validation_options.skip
    ):
        checkers.append(
            (f"hook:{hook_module}", load_object_check_hook(hook_module))
        )

    return checkers


def check_data(data: Any, ft: Filetype, object_check_hook: bool = True):
    failures = {}

    for name, checker in object_checkers_for(
        ft, object_check_hook=object_check_hook
    ):
        these_failures = checker(data, ft) or {}

        if len(these_failures) == 0:
            continue

        if name == "standard":
            failures |= these_failures
        else:
            if name in failures:
                raise ValueError(f"failure namespace collision: {name!r}")
            failures[name] = these_failures

    return failures


def validate(
    ft: Filetype,
    path: str | Path,
    *,
    bucket: Bucket | str | None = None,
    object_check_hook: bool = True
) -> dict[str, list[str]]:
    """
    Check whether the file at PATH is accurately described by the filetype
    FT. Return a dict of mismatches.  If the dict is empty, there are no
    mismatches. If BUCKET is not None, PATH is interpreted as a key in the
    S3 bucket BUCKET.
    """
    from mast_transfer_tools.io import loader_for

    path = str(path)
    opener = loader_for(ft.standard)
    data = opener(path, bucket)
    try:
        failures = check_data(data, ft, object_check_hook=object_check_hook)
        if failures:
            failures = {
                f"{path}: at {key}:": value
                for key, value in failures.items()
            }
        return failures
    finally:
        close = getattr(data, "close", None)
        if callable(close):
            close()
