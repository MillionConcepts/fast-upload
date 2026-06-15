"""
Description of FITS files
"""
from pathlib import Path
from typing import Collection

from astropy.io import fits

from hostess.aws.s3 import Bucket
from mast_transfer_tools.describe.generic import (
    sanitize_object_description,
    _n_unique_groups,
    chunk_repeated_ordered_objects,
    unify_object_lists,
    FileDescription
)
from mast_transfer_tools.io.fits import fitsopen_generic
from mast_transfer_tools.validation.generic import normalize_dt_rep
from mast_transfer_tools.utilz.compression import MCFile
from mast_transfer_tools.utilz.english import a_type

SupportedHDU = (
    fits.PrimaryHDU | fits.BinTableHDU | fits.CompImageHDU | fits.ImageHDU
)


def describe_hdu(hdu: SupportedHDU) -> dict:
    if isinstance(hdu, (fits.PrimaryHDU, fits.ImageHDU, fits.CompImageHDU)):
        description = describe_image_hdu(hdu)
    elif isinstance(hdu, fits.BinTableHDU):
        description = describe_bintable_hdu(hdu)

    elif isinstance(hdu, fits.TableHDU):
        raise NotImplementedError(
            f"{hdu.name!r}: ASCII-table HDUs (XTENSION=TABLE) are not"
            f" supported. We recommend converting all TABLE HDUs to BINTABLE."
        )
    # These classes are undocumented but it should be OK to use them
    # for these fine distinctions of diagnostics.
    elif isinstance(hdu, fits.hdu.base._CorruptedHDU):
        raise ValueError(f"{hdu.name!r}: HDU is corrupted")
    elif isinstance(hdu, fits.hdu.base._BaseHDU):
        hdutype = type(hdu).__name__.upper().replace("HDU", "")
        raise NotImplementedError(
            f"{hdu.name!r}: {hdutype} HDUs are not supported."
            f" Automatic description of FITS files supports PRIMARY, IMAGE,"
            f" ZIMAGE and BINTABLE HDUs."
        )
    else:
        raise TypeError(
            f"BUG: describe_hdu called on {a_type(hdu)},"
            f" which is not a type of FITS HDU."
        )

    description["objtype"] = type(hdu).__name__.lower().replace("hdu", "")
    description["name"] = hdu.name
    return description


def describe_image_hdu(hdu: fits.PrimaryHDU | fits.ImageHDU) -> dict:
    if hdu.data is None:
        return {}
    return {"ndim": hdu.data.ndim, "dtype": normalize_dt_rep(hdu.data.dtype)}


def describe_bintable_hdu(hdu: fits.BinTableHDU) -> dict:
    if hdu.data is None:
        return {}
    dtype = hdu.data.dtype
    schema = []
    for name, dt_shape in dtype.fields.items():
        # we must do this because astropy lies about top-level dtype
        dt = hdu.data[name].dtype
        column = {"dtype": normalize_dt_rep(dt), "ndim": dt.ndim, "name": name}
        schema.append(column)
    return {"schema": schema}


def unify_hdu_descriptions(
    ds: Collection[FileDescription]
) -> list[FileDescription]:
    hduls = []
    for d in ds:
        hdul = []
        for hdu_ix, hdu in enumerate(d.objects):
            hdul.append(hdu | {"group_id": hdu_ix})
        hduls.append(hdul)
    hduls, failure = chunk_repeated_ordered_objects(hduls)
    if failure is not None:
        raise ValueError(failure)
    if _n_unique_groups(hduls) > 1:
        raise ValueError(
            "variation in object structure too complex to automatically "
            "describe"
        )
    return unify_object_lists(hduls)


def unify_descriptions(
    descriptions: Collection[FileDescription]
) -> tuple[list[dict] | None, str | None]:
    if not all(d.standard == "fits" for d in descriptions):
        return None, "Not all files are FITS"
    hdus, failure = unify_hdu_descriptions(descriptions)
    if failure is not None:
        return None, failure
    return [sanitize_object_description(h) for h in hdus.values()], None


def describe_file(fn: str | Path, bucket: Bucket | None = None) -> list[dict]:
    hdu_descriptions = []
    for hdu in fitsopen_generic(fn, bucket):
        hdu_descriptions.append(describe_hdu(hdu))
    return hdu_descriptions


def describe_objects(desc: FileDescription, fp: MCFile) -> None:
    assert desc.objects is None
    desc.objects = []
    for hdu in fits.open(fp):
        desc.objects.append(describe_hdu(hdu))
