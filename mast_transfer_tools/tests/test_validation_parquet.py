import re
from typing import Any

import numpy as np
import pyarrow as pa

from mast_transfer_tools import labels
from mast_transfer_tools.validation import parquet

from hypothesis import given, strategies as st
from mast_transfer_tools.tests.test_label_objects import st_identifier
from mast_transfer_tools.tests.test_validation_generic import (
    assert_no_errors,
    st_dtype_name,
)


# these are *almost* the same as the copies in test_validation_generic
# but they use the specialized column and data objects for Parquet
def make_ColumnObject(
    name: str,
    *,
    dtype: str,
    name_regex: bool = False,
    ndim: int = 0,
    lpath: str = "/"
) -> labels.ParquetColumnObject:
    return labels.ParquetColumnObject(
        repeated = False,
        name_regex = name_regex,
        name = re.compile(name) if name_regex else name,
        dtype = dtype,
        ndim = ndim,
        lpath = lpath
    )


def make_DataObject(
    *,
    schema: list[labels.ColumnObject],
    lpath: str = "/"
) -> labels.ParquetDataObject:
    return labels.ParquetDataObject(
        schema = schema,
        metadata = {},
        lpath = lpath,
    )



def st_parquet_table_schema() -> st.SearchStrategy[list[labels.ColumnObject]]:
    return st.lists(
        st.tuples(
            st_identifier(),
            st_dtype_name(choices=labels.PARQUET_DTYPES),
        ),
        min_size=3,
        max_size=7,
        unique_by=lambda t: t[0],
    ).map(lambda cols: [
        make_ColumnObject(
            f"{i}.{name}",
            dtype=dtype,
            lpath=f"/filetypes/pqtest/objects/0/schema/{i}"
        )
        for i, (name, dtype) in enumerate(cols)
    ])


def st_parquet_filetype() -> st.SearchStrategy[labels.Filetype]:
    return st_parquet_table_schema().map(lambda schema: labels.Filetype(
        standard="parquet",
        filename=[labels.FilePattern(
            lpath="/filetypes/pqtest/filename/0",
            pattern=re.compile(r".*\.parquet")
        )],
        objects=[make_DataObject(
            schema=schema,
            lpath="/filetypes/pqtest/objects/0"
        )],
        validation_options=labels.FiletypeValidationOptions(skip=[]),
        lpath="/filetypes/pqtest",
    ))


@st.composite
def st_arrow_table(draw: st.DrawFn, spec: labels.Filetype) -> pa.Table:
    if not spec.objects:
        return pa.table([])

    rows = 1
    schema = spec.objects[0].schema
    arrs: list[pa.Array[Any]] = []
    names = []

    for col in schema:
        assert isinstance(col.name, str)
        names.append(col.name)

        dtype = np.dtype(col.dtype)
        itemsize = dtype.itemsize
        arrow_dtype = pa.from_numpy_dtype(dtype)
        nbytes = rows * itemsize
        data = draw(st.binary(min_size=nbytes, max_size=nbytes))

        try:
            arrs.append(pa.Array.from_buffers(
                arrow_dtype,
                rows,
                # The leading None means "no nulls", I think;
                # the PyArrow documentation does not explain how
                # many buffers pa.Array.from_buffers expects or
                # what they mean.  This use of None _is_ documented
                # (in an example) but the type stubs don't recognize it.
                [None, pa.py_buffer(data)],  # type:ignore[list-item]
                null_count=0
            ))
        except Exception as e:
            raise RuntimeError(
                f"failed to construct column with"
                f" {rows=} {itemsize=} {col.dtype=} {arrow_dtype=}"
            ) from e

    return pa.Table.from_arrays(arrs, names=names)


@st.composite
def st_filetype_with_good_table(draw: st.DrawFn) -> tuple[labels.Filetype, pa.Table]:
    ft = draw(st_parquet_filetype())
    table = draw(st_arrow_table(ft))
    return (ft, table)


@given(st_filetype_with_good_table())
def test_random_parquet_validation_ok(tcase: tuple[labels.Filetype, pa.Table]) -> None:
    ft, tbl = tcase

    assert_no_errors(
        ft.errors,
        "test precondition failed: invalid filetype example"
    )

    ostream = pa.BufferOutputStream()
    pa.parquet.write_table(tbl, ostream)
    buf = ostream.getvalue()

    istream = pa.BufferReader(buf)
    pqfile = pa.parquet.ParquetFile(istream)
    errors = parquet.check_file(pqfile, ft)
    assert_no_errors(
        errors,
        "table does not conform to schema"
    )
