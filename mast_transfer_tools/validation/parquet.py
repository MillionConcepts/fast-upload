"""
Validation of Parquet data files
"""

import re
from types import MappingProxyType as MPt

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from mast_transfer_tools.labels import Filetype, DataObject, ObjectMetadata
from mast_transfer_tools.validation import generic

PARQUET_PHYSICAL_TYPE_MAP = MPt(
    {
        "BOOLEAN": "b",
        "INT32": "i4",
        "INT64": "i8",
        "FLOAT": "f4",
        "DOUBLE": "f8",
        "BYTE_ARRAY": "O",
    }
)

SCHEMA_BAILOUT_MESSAGE = (
    "Columns of such types are not supported, as their presence suggests "
    "that the Parquet format version in use by this file may be incompatible "
    "with the Parquet format version in use by this software, or the file may "
    "be corrupted in some unusual way. Halting full schema verification."
)


def check_schema(
    file: pq.ParquetFile, spec: DataObject
) -> dict[str, list[str]]:
    """
    Compare the schema of FILE to the schema described by SPEC.
    Return a semi-structured description of the differences.
    An empty dict means no significant differences were found.
    """
    if spec.schema is None:
        return {}

    # verify the file's contents against its embedded schema
    try:
        file.scan_contents()
    except (pa.ArrowInvalid, pa.ArrowException) as ex:
        return {"base": [f"Table data is invalid: {(type(ex))}: {ex}"]}

    # having gotten here, we know the file is self-consistent; now we need
    # to check whether it matches our expectations
    dtype = []
    for i, field in enumerate(file.schema_arrow):
        name, ftype = field.name, field.type
        # to_pandas_dtype() gives the wrong result for both Arrow date types
        # (namely pa.types.date32 and pa.types.date64).  pa.types.is_primitive
        # is true for Arrow date types, so we need to check is_date first.
        if pa.types.is_date(ftype):
            dtype.append((name, "M8[D]"))
        # The value of is_primitive() is _not_ determined by whether or
        # not a type corresponds directly to a Parquet physical type, even
        # though those are sometimes called Parquet primitive types. It is
        # determined by whether or not it is an _Arrow_ primitive type. This
        # includes most numerical data types. It does _not_ include either
        # fixed- or variable-length binary arrays (even though these are the
        # prototypical realizations of the Parquet FIXED_LEN_BINARY_ARRAY and
        # BINARY_ARRAY physical types). However, it reliably tells us that we
        # can cast it to an equivalent numpy/pandas type.
        elif pa.types.is_primitive(ftype):
            dtype.append((name, ftype.to_pandas_dtype()))
        elif pa.types.is_fixed_size_binary(ftype):
            dtype.append((name, f"V{ftype.byte_width}"))
        elif pa.types.is_binary(ftype):
            dtype.append((name, "O"))
        else:
            phystype = file.schema.column(i).physical_type
            if phystype == "INT96":
                return {
                    "base": [
                        f"Column {name} uses the deprecated INT96 "
                        f"primitive type but does not have a datetime logical "
                        f"type. {SCHEMA_BAILOUT_MESSAGE}"
                    ]
                }
            if phystype == "FIXED_LEN_BYTE_ARRAY":
                dtype.append((name, f"V{ftype.byte_width}"))
            elif phystype not in PARQUET_PHYSICAL_TYPE_MAP.keys():
                return {
                    "base": [
                        f"unknown physical type {phystype} on column "
                        f"{name}. {SCHEMA_BAILOUT_MESSAGE}"
                    ]
                }
            elif file.schema.column(i).name != file.schema.column(i).path:
                # variable-length 'container' types (like lists) whose
                # elements are primitive types will report the physical
                # type of their elements, but the column itself is not actually
                # of that type. However, these cases will always give a
                # 'path' to the elements that differs from the column name.
                dtype.append((name, "O"))
            else:
                dtype.append((name, PARQUET_PHYSICAL_TYPE_MAP[phystype]))
    return generic.check_schema(np.dtype(dtype), spec)


PARQUET_METADATA_TRUE_RE = re.compile(r"(?i)\A(?:t(?:rue)?|yes|on|1)\Z")
PARQUET_METADATA_FALSE_RE = re.compile(r"(?i)\A(?:f(?:alse)?|no|off|0)\Z")


def convert_meta(
    raw_val: str, spec: ObjectMetadata
) -> str | bool | float | int:
    if isinstance(spec.value, bool):
        if PARQUET_METADATA_TRUE_RE.fullmatch(raw_val):
            return True
        elif PARQUET_METADATA_FALSE_RE.fullmatch(raw_val):
            return False
        else:
            raise ValueError(
                f"Label specifies boolean value, but value could not be "
                f"interpreted as boolean (got {raw_val!r})"
            )
    if isinstance(spec.value, int):
        return int(raw_val)
    if isinstance(spec.value, float):
        return float(raw_val)
    assert isinstance(spec.value, str)
    return raw_val


def check_meta(file: pq.ParquetFile, spec: DataObject) -> dict[str, list[str]]:
    """
    Compare the metadata of FILE to the expectations described by SPEC.
    Return a semi-structured description of the differences.
    An empty dict means no significant differences were found.
    """
    if spec.metadata is None:
        return {}
    file_meta = file.metadata.metadata
    if file_meta is not None:
        user_meta = {
            k.decode("utf-8"): v.decode("utf-8") for k, v in file_meta.items()
        }
    else:
        user_meta = {}

    failures = {}
    for key, meta_spec in spec.metadata.items():
        user_val = user_meta.get(key)
        if user_val is None:
            failures[key] = ["required metadata key missing"]
            continue
        if meta_spec.value is None:
            continue
        try:
            meta_val = convert_meta(user_val, meta_spec)
        except ValueError as e:
            failures[key] = [str(e)]
            continue
        if (failure := generic.check_meta(meta_val, meta_spec)) is not None:
            failures[key] = [failure]
    return failures


def check_file(file: pq.ParquetFile, spec: Filetype) -> dict[str, list[str]]:
    """
    Compare FILE to the expectations described by SPEC.
    Return a semi-structured description of the differences.
    An empty dict means no significant differences were found.
    """
    if "all" in spec.validation_options.skip or len(spec.objects) == 0:
        return {}

    failures: dict[str, list[str]] = {}

    if len(spec.objects) > 1:
        failures["base"] = [
            f"Parquet file definitions must have either 0 or 1 objects"
            f"(got {len(spec.objects)}). Ignoring all but the first."
        ]

    if "metadata" not in spec.validation_options.skip:
        meta_failures = check_meta(file, spec.objects[0])
        for key, errors in meta_failures.items():
            failures[f"metadata/{key}"] = errors

    if "schema" not in spec.validation_options.skip:
        schema_failures = check_schema(file, spec.objects[0])
        for key, errors in schema_failures.items():
            failures[f"schema/{key}"] = errors

    return failures
