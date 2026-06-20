"""This submodule contains utilities related to i/o for specific file
formats."""

from typing import Callable

from astropy.io.fits import HDUList
from asdf import AsdfFile
from hostess.aws.s3 import Bucket
from pyarrow.parquet import ParquetFile

from ..labels import STANDARDS_SUPPORTING_DATA_VALIDATION
from ..utilz import __getattr__impl, ModuleType


def __getattr__(name: str) -> ModuleType:
    return __getattr__impl(name, __name__)


def loader_for(
    standard: str,
) -> (
    Callable[[str, Bucket | str | None], HDUList]
    | Callable[[str, Bucket | str | None], AsdfFile]
    | Callable[[str, Bucket | str | None], ParquetFile]
):
    """Get the canonical loader function for a supported standard."""
    if standard not in STANDARDS_SUPPORTING_DATA_VALIDATION:
        raise TypeError(
            f"No standardized loader available for {standard} files."
        )
    if standard == "fits":
        from .fits import fitsopen_generic

        return fitsopen_generic
    elif standard == "parquet":
        from .parquet import parquetopen_generic

        return parquetopen_generic
    elif standard == "asdf":
        from .asdf import asdfopen_generic

        return asdfopen_generic
    raise NotImplementedError(f"Validator not yet implemented for {standard}")
