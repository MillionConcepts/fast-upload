"""
Description of Parquet files
"""
from typing import Collection

from pathlib import Path

import numpy as np
import pyarrow as pa

from hostess.aws.s3 import Bucket
from mast_transfer_tools.describe.generic import FileDescription, unify_object_lists, \
    sanitize_object_description
from mast_transfer_tools.io.parquet import parquetopen_generic
from mast_transfer_tools.validation.generic import normalize_dt_rep
from mast_transfer_tools.validation.parquet import PARQUET_PHYSICAL_TYPE_MAP


def unify_descriptions(
    descriptions: Collection[FileDescription]
) -> tuple[list[dict] | None, str | None]:
    """
    Attempt to unify a collection of Parquet file descriptions into a list of
    dicts suitable for use as the DataObjects of a Filetype.

    Args:
        descriptions: collection of FileDescriptions populated with
            describe_file()

    Returns:
        objects: if unification succeeded, a list of dicts that can be used
            to initialize DataObjects; if it didn't, None
        failure: if unification failed, a string describing the failure;
            if it succeeded, None
    """

    if not all(d.standard == "parquet" for d in descriptions):
        return None, "Not all files are Parquet"
    table, failure = unify_object_lists([d.objects for d in descriptions])
    if failure is not None:
        return None, failure
    return [sanitize_object_description(table[0])], None


def describe_file(fn: str | Path, bucket: Bucket | None = None) -> list[dict]:
    """
    Describe objects (always a single object) in an individual parquet file.
    """
    file = parquetopen_generic(fn, bucket=bucket)
    try:
        row: pa.Table = file.read_row_group(0).take([0])
    finally:
        file.close()
    schema = []
    for i, field in enumerate(tuple(row.schema)):
        name, ftype = field.name, field.type
        column = {"name": name}
        if pa.types.is_primitive(ftype) or pa.types.is_date(ftype):
            column["dtype"] = normalize_dt_rep(
                np.dtype(ftype.to_pandas_dtype())
            )
        elif pa.types.is_fixed_size_binary(ftype):
            column["dtype"] = f"V{ftype.byte_width}"
        elif pa.types.is_binary(ftype):
            column["dtype"] = "O"
        else:
            phystype = file.schema.column(i).physical_type
            if phystype == "INT96":
                raise TypeError(
                    "Deprecated INT96 physical type not supported when not "
                    "associated with datetime logical type."
                )
            if phystype == "FIXED_LEN_BYTE_ARRAY":
                column["dtype"] = f"V{ftype.byte_width}"
            elif phystype not in PARQUET_PHYSICAL_TYPE_MAP.keys():
                raise TypeError(f"Unknown physical type {phystype}")
            elif file.schema.column(i).name != file.schema.column(i).path:
                column["dtype"] = "O"
            else:
                column["dtype"] = PARQUET_PHYSICAL_TYPE_MAP[phystype]
        schema.append(column)
    # adding group_id and "table" are a little redundant but let us go
    # through the unify_object_lists() workflow without ceremony
    return [{"schema": schema, "group_id": 0, "name": "table"}]
