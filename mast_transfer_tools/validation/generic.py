"""
Validation of individual data items that can appear in multiple kinds of file.
"""

import datetime as dt
import re
from math import isnan

import numpy as np

from mast_transfer_tools.labels import ColumnObject, DataObject, ObjectMetadata
from mast_transfer_tools.utilz.english import repr_rx


def normalize_dt_rep(dtype: np.dtype) -> str:
    """
    'Normalized' string representation of a numpy dtype, agnostic to
    byteorder, repeated elements, dimensionality, etc. Will not produce
    satisfying results on dtypes with multiple fields.
    """
    if dtype == np.dtype("bool"):
        # bool is always 1 byte wide and does not require
        # disambiguation; however, 'b' by itself means _byte_ (i8);
        # you have to say 'b1' for bool
        return "b1"
    # the 'object' type denotes a variable-length object or a pointer
    # to a variable-length object; may not be consistently sized across
    # implementations and architectures
    if dtype == np.dtype("O"):
        return "O"
    # for timestamp and duration types we need to preserve the precision
    if dtype.base.kind in ("M", "m"):
        unit, count = np.datetime_data(dtype.base)
        assert count >= 1
        if count == 1:
            return f"{dtype.base.kind}{dtype.base.itemsize}[{unit}]"
        else:
            return f"{dtype.base.kind}{dtype.base.itemsize}[{count}{unit}]"
    # treat semi-deprecated 'S' character string type as alias for 'V'
    if dtype.base.kind == "S":
        return f"V{dtype.base.itemsize}"
    # also treat 'U' as alias for 'V' but correct for astropy having altered
    # the itemsize because it uses UTF-32 (yes, -32) internally
    if dtype.base.kind == "U":
        return f"V{dtype.base.itemsize // 4}"

    return f"{dtype.base.kind}{dtype.base.itemsize}"


def check_column(name: str, dtype: np.dtype, col: ColumnObject) -> list[str]:
    """
    'col' is a ColumnObject describing one column of a table.
    'name' and 'dtype' are the name and dtype of one field of a
    numpy structured array, which is supposed to agree with 'spec'.
    Compare them and return a list of differences.  An empty list
    means they do agree.
    """

    differences = []

    c_name = col.name
    if isinstance(c_name, re.Pattern):
        if not c_name.fullmatch(name):
            differences.append(
                f"wrong name: {name!r} doesn't match {repr_rx(c_name)}"
            )
    else:
        if c_name != name:
            differences.append(
                f"wrong name: expected {c_name!r}, got {name!r}"
            )

    norm_dt = normalize_dt_rep(dtype)
    if norm_dt != col.dtype:
        differences.append(f"wrong dtype: expected {col.dtype}, got {norm_dt}")
    if dtype.ndim != col.ndim:
        differences.append(
            f"wrong item dimensionality: expected {col.ndim}, got {dtype.ndim}"
        )

    return differences


def check_schema(dtype: np.dtype, spec: DataObject) -> dict[str, list[str]]:
    """
    'spec' is a DataObject describing a table.  'dtype' is the dtype of
    a numpy structured array, which should agree with the table schema
    defined by 'spec'.  Compare the two.  Return a description of the
    differences; if it is empty, they match.

    Comparison is order sensitive: np.dtype([('name', 'U10'), ('age', 'i4')])
    does not match [ColumnObject(name='age', dtype='i4'),
                    ColumnObject(name='name', dtype='U10')].
    """
    if dtype.names is None:
        raise TypeError(
            f"check_schema cannot be applied to the scalar dtype {dtype!r}."
            f" Perhaps you called it in reference to a simple array?"
        )

    schema = spec.schema
    names = dtype.names
    fields = dtype.fields
    assert fields is not None

    errors = {}
    field_ix = 0

    for column in schema:
        c_name = column.name
        if field_ix >= len(names):
            if isinstance(c_name, re.Pattern):
                errors[field_ix] = [f"no fields matching {repr_rx(c_name)}"]
            else:
                errors[field_ix] = [f"field {c_name!r} missing"]
            field_ix += 1
            continue

        while True:
            f_name = names[field_ix]
            f_type = fields[f_name][0]
            differences = check_column(f_name, f_type, column)
            if differences:
                errors[field_ix] = differences

            field_ix += 1
            if field_ix >= len(names) or not column.repeated:
                break
            assert isinstance(column.name, re.Pattern)
            if not column.name.fullmatch(names[field_ix]):
                break

    while field_ix < len(names):
        errors[field_ix] = [f"extra field {names[field_ix]!r}"]
        field_ix += 1

    return errors


def check_meta(
    val: str | bool | float | int,  # NOQA: FBT001
    spec: ObjectMetadata,
) -> str | None:
    """
    'spec' describes the constraints on a metadata item, and 'val'
    is the actual value of that metadata item.  Check whether 'val'
    is a legitimate value according to 'spec'.  Return None if it is,
    or a description of the mismatch if it is not.
    """
    # TODO, maybe: don't smash date(time) to string
    # TODO: use label_meta.a_type in diagnostics

    if spec.value_regex is True:
        assert isinstance(spec.value, re.Pattern)

        if isinstance(val, dt.datetime):
            val = val.isoformat()
        if not isinstance(val, str):
            return (
                f"wrong type for metadata value: expected str, got {type(val)}"
            )
        if not spec.value.match(val):
            return (
                f"incorrect metadata value:"
                f" {val!r} does not match {repr_rx(spec.value)}"
            )
        return None

    if isinstance(val, dt.datetime):
        val = val.isoformat()

    # bool is a subclass of int so we have to special case it here
    if (
        (type(spec.value) is bool and type(val) is not bool)
        or (type(spec.value) is not bool and type(val) is bool)
        or not isinstance(val, type(spec.value))
    ):
        return (
            f"wrong type for metadata value:"
            f" expected {type(spec.value)}, got {type(val)}"
        )

    if val != spec.value and not (
        isinstance(val, float)
        and isinstance(spec.value, float)
        and isnan(val)
        and isnan(spec.value)
    ):
        return (
            f"incorrect metadata value: expected {spec.value!r}, got {val!r}"
        )

    return None
