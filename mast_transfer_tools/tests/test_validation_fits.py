import re

from functools import reduce
from re import Pattern
from typing import cast

from io import BytesIO
from astropy.io.fits import open as fits_open
from astropy.io.fits.hdu import (
    PrimaryHDU,
    ImageHDU,
    BinTableHDU,
    HDUList,
)
from astropy.io.fits.hdu.base import _BaseHDU

import numpy as np

from mast_transfer_tools import labels
from mast_transfer_tools.validation import fits

from hypothesis import given, strategies as st
from mast_transfer_tools.tests.test_label_objects import st_identifier
from mast_transfer_tools.tests.test_validation_generic import (
    assert_no_errors,
    st_dtype_name,
)


RNG = np.random.default_rng()


# these are *almost* the same as the copies in test_validation_generic
# but they use the specialized column and data objects for FITS
def make_ColumnObject(
    name: str,
    *,
    dtype: str,
    name_regex: bool = False,
    ndim: int = 0,
    lpath: str = "/",
) -> labels.FITSColumnObject:
    return labels.FITSColumnObject(
        repeated=False,
        name_regex=name_regex,
        name=re.compile(name) if name_regex else name,
        dtype=dtype,
        ndim=ndim,
        lpath=lpath,
    )


def make_DataObject(
    *,
    name: str,
    objtype: str,
    schema: list[labels.ColumnObject],
    dtype: str | None = None,
    ndim: int | None = None,
    name_regex: bool = False,
    repeated: bool = False,
    optional: bool = False,
    lpath: str = "/",
) -> labels.FITSDataObject:
    name_regex |= repeated
    return labels.FITSDataObject(
        name=re.compile(name) if name_regex else name,
        objtype=objtype,
        schema=schema,
        dtype=dtype,
        ndim=ndim,
        name_regex=name_regex,
        repeated=repeated,
        optional=optional,
        metadata={},
        lpath=lpath,
    )


def st_fits_namelist(*, max_hdus: int = 5) -> st.SearchStrategy[list[str]]:
    return st.lists(
        st_identifier(lowercase=False, underscore=False).filter(
            lambda id: id != "PRIMARY"
        ),
        min_size=0,
        max_size=max_hdus - 1,
        unique=True,
    ).map(lambda names: ["PRIMARY"] + names)


def st_bintable_schema(
    hdu_name: str,
    *,
    min_columns: int = 3,
    max_columns: int = 15,
) -> st.SearchStrategy[list[labels.FITSColumnObject]]:
    return st.lists(
        st.tuples(
            st_identifier(lowercase=False, underscore=False),
            st_dtype_name(choices=labels.FITS_TABLE_DTYPES),
        ),
        min_size=min_columns,
        max_size=max_columns,
        unique_by=lambda t: t[0],
    ).map(
        lambda cols: [
            make_ColumnObject(
                f"C{i:02}{name}",
                dtype=dtype,
                lpath=f"/filetypes/fitstest/objects/{hdu_name}/schema/{i}",
            )
            for i, (name, dtype) in enumerate(cols)
        ]
    )


@st.composite
def st_fits_objspec(
    draw: st.DrawFn,
    name: str,
    *,
    min_schema_columns: int = 3,
    max_schema_columns: int = 15,
) -> labels.FITSDataObject:
    if name == "PRIMARY":
        objtype = "primary"
    else:
        objtype = draw(st.sampled_from(["image", "bintable"]))

    if objtype in ("primary", "image"):
        dtype = draw(st_dtype_name(choices=labels.FITS_ARRAY_DTYPES))
        ndim = draw(st.integers(min_value=2, max_value=4))
        schema = []
    else:
        dtype = None
        ndim = None
        schema = draw(
            st_bintable_schema(
                name,
                min_columns=min_schema_columns,
                max_columns=max_schema_columns,
            )
        )

    # cast needed because list[FITSColumnObject] isn't assignment
    # compatible with list[ColumnObject] for tedious type theory reasons
    return make_DataObject(
        name=name,
        objtype=objtype,
        schema=cast(list[labels.ColumnObject], schema),
        dtype=dtype,
        ndim=ndim,
    )


@st.composite
def st_fits_filetype(
    draw: st.DrawFn,
    max_hdus: int = 5,
    min_schema_columns: int = 3,
    max_schema_columns: int = 15,
) -> labels.Filetype:
    hdu_names = draw(st_fits_namelist(max_hdus=max_hdus))
    hdus = [
        draw(
            st_fits_objspec(
                name,
                min_schema_columns=min_schema_columns,
                max_schema_columns=max_schema_columns,
            )
        )
        for name in hdu_names
    ]

    # cast needed because list[FITSDataObject] isn't assignment
    # compatible with list[DataObject] for tedious type theory reasons
    return labels.Filetype(
        standard="fits",
        filename=[
            labels.FilePattern(
                lpath="/filetypes/fitstest/filename/0",
                pattern=re.compile(r".*\.fits"),
            )
        ],
        objects=cast(list[labels.DataObject], hdus),
        validation_options=labels.FiletypeValidationOptions(skip=[]),
        lpath="/filetypes/fitstest",
    )


@st.composite
def st_hdu(draw: st.DrawFn, spec: labels.FITSDataObject) -> _BaseHDU:
    if spec.objtype == "primary" or spec.objtype == "image":
        assert spec.ndim is not None
        assert spec.dtype is not None
        if spec.ndim == 0:
            arr = np.array([], dtype=spec.dtype)
        else:
            axis_sizes = draw(
                st.lists(
                    st.integers(min_value=1, max_value=5),
                    min_size=spec.ndim,
                    max_size=spec.ndim,
                )
            )
            nelements = reduce(lambda x, y: x * y, axis_sizes)
            arr = np.arange(nelements).reshape(*axis_sizes).astype(spec.dtype)
        if spec.objtype == "primary":
            return PrimaryHDU(arr)
        else:
            return ImageHDU(arr, name=spec.name)
    else:
        assert spec.ndim is None
        assert spec.dtype is None
        dtypes = []
        nrows = 1
        for col in spec.schema:
            dtuple: (
                tuple[str | Pattern[str], str]
                | tuple[str | Pattern[str], str, tuple[int, ...]]
            )
            if col.ndim > 0:
                dtuple = (
                    col.name,
                    col.dtype,
                    tuple(nrows for _ in range(col.ndim)),
                )
            else:
                dtuple = (col.name, col.dtype)
            dtypes.append(dtuple)
        dt = np.dtype(dtypes)
        tbl = np.frombuffer(
            RNG.integers(0, 255, nrows * dt.itemsize, dtype="u1").data,
            dtype=dt,
        )
        # import sys
        # sys.stderr.write(str(dt) + "\n")
        return BinTableHDU(tbl, name=spec.name)


@st.composite
def st_hdul(draw: st.DrawFn, ft: labels.Filetype) -> HDUList:
    hdus = []
    for objspec in ft.objects:
        assert isinstance(objspec, labels.FITSDataObject)
        hdus.append(draw(st_hdu(objspec)))
    return HDUList(hdus)


@st.composite
def st_filetype_with_good_hdul(
    draw: st.DrawFn,
) -> tuple[labels.Filetype, HDUList]:
    ft = draw(st_fits_filetype())
    hdul = draw(st_hdul(ft))
    return (ft, hdul)


@given(st_filetype_with_good_hdul())
def test_random_fits_validation_ok(
    tcase: tuple[labels.Filetype, HDUList],
) -> None:
    ft, hdul = tcase

    assert_no_errors(
        ft.errors, "test precondition failed: invalid filetype example"
    )

    ostream = BytesIO()
    hdul.writeto(ostream)
    blob = ostream.getvalue()
    del ostream

    fitsfile = fits_open(BytesIO(blob))
    errors = fits.check_file(fitsfile, ft)
    assert_no_errors(errors, "HDUL does not conform to schema")
