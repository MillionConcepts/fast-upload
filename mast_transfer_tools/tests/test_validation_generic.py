"""
Tests of mast_transfer_tools.validation.generic
"""
import io
import pprint
import re
from functools import cache
from typing import Any, Sequence

import numpy as np

from hypothesis import given, strategies as st
from mast_transfer_tools.tests.test_label_objects import st_identifier

from mast_transfer_tools import labels
from mast_transfer_tools.validation import generic as v_generic


def assert_no_errors(errors: dict[str, Any], descr: str) -> None:
    if not errors:
        return
    s = io.StringIO()
    s.write(descr)
    s.write(":\n")
    pprint.pp(errors, s, indent=2)
    raise AssertionError(s.getvalue())


@st.composite
def st_unequal_identifiers(draw: st.DrawFn) -> tuple[str, str]:
    id1 = draw(st_identifier())
    id2 = draw(st_identifier().filter(lambda n: n != id1))
    return (id1, id2)


@st.composite
def st_dtype_name(
    draw: st.DrawFn,
    choices: Sequence[str] = labels.SUPPORTED_DTYPE_NAMES
) -> str:

    # The 'M' and 'm' entries in all the possible 'choices' lists are
    # more general than we want.
    @cache
    def restrict_timestamp_regex(rx: str) -> str:
        return "\\A" + rx.replace(
            "(?:[1-9][0-9]*)?",
            "(?:|[2-9]|[1-9]0|[1-9][05]0)"
        ) + "\\Z"

    # Don't generate V or O columns at all.  Generating fake data for
    # such columns is too much hassle.  Support for these column types
    # is tested using fixed test cases instead.
    dt = "V"
    while dt[0] in ("V", "O"):
        dt = draw(st.sampled_from(choices))

    if dt[0] in ("M", "m"):
        return draw(st.from_regex(restrict_timestamp_regex(dt)))

    return dt


@st.composite
def st_unequal_dtype_names(
    draw: st.DrawFn,
    choices: Sequence[str] = labels.SUPPORTED_DTYPE_NAMES
) -> tuple[str, str]:
    id1 = draw(st_dtype_name(choices))
    id2 = draw(st_dtype_name(choices).filter(lambda n: n != id1))
    return (id1, id2)


@st.composite
def st_unequal_ndims(draw: st.DrawFn) -> tuple[int, int]:
    d1 = draw(st.integers(min_value=1, max_value=9))
    d2 = draw(st.integers(min_value=1, max_value=9).filter(lambda n: n != d1))
    return (d1, d2)


@st.composite
def st_record_dtype(draw: st.DrawFn) -> np.dtype:
    fields = draw(st.lists(
        st.tuples(st_identifier(), st_dtype_name()),
        min_size=2,
        max_size=16,
        unique_by=lambda v: v[0]
    ))
    return np.dtype(fields)


def st_metadata_value() -> st.SearchStrategy[str | bool | float | int]:
    return st.one_of(
        st.text(),
        st.booleans(),
        st.floats(allow_nan=False),
        st.integers()
    )


@st.composite
def st_unequal_metadata_same_type(draw: st.DrawFn) -> tuple[
    str | bool | float | int,
    str | bool | float | int
]:
    v1 = draw(st_metadata_value())

    if isinstance(v1, str):
        return (v1, draw(st.text().filter(lambda v2: v2 != v1)))
    if isinstance(v1, bool):
        # there are only two values of bool so we don't need to draw
        # the other one
        return (v1, not v1)
    if isinstance(v1, float):
        return (v1, draw(st.floats(allow_nan=False).filter(lambda v2: v2 != v1)))

    # note: bool is a subtype of int so this needs to be last
    assert isinstance(v1, int)
    return (v1, draw(st.integers().filter(lambda v2: v2 != v1)))


@st.composite
def st_unequal_metadata_diff_types(draw: st.DrawFn) -> tuple[
    str | bool | float | int,
    str | bool | float | int
]:
    v1 = draw(st_metadata_value())
    if isinstance(v1, str):
        return (v1, draw(st.one_of(st.booleans(), st.floats(), st.integers())))
    if isinstance(v1, bool):
        return (v1, draw(st.one_of(st.text(), st.floats(), st.integers())))
    if isinstance(v1, float):
        return (v1, draw(st.one_of(st.text(), st.booleans(), st.integers())))

    # note: bool is a subtype of int so this needs to be last
    assert isinstance(v1, int)
    return (v1, draw(st.one_of(st.text(), st.booleans(), st.floats())))


def make_ColumnObject(
    name: str,
    *,
    dtype: str,
    name_regex: bool = False,
    ndim: int = 0,
    lpath: str = "/"
) -> labels.ColumnObject:
    return labels.ColumnObject(
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
) -> labels.DataObject:
    return labels.DataObject(
        schema = schema,
        metadata = {},
        lpath = lpath
    )


def make_ObjectMetadata(
    val: str | bool | float | int | re.Pattern[str]  # NOQA: FBT001
) -> labels.ObjectMetadata:
    if isinstance(val, re.Pattern):
        raise NotImplementedError
    else: # NOQA: RET506
        return labels.ObjectMetadata(
            value = val,
            value_regex = False,
            lpath = "/"
        )


def test_normalized_dt_rep_from_python_types() -> None:
    ndr = v_generic.normalize_dt_rep
    assert ndr(np.dtype(bool))     == "b1"
    assert ndr(np.dtype(int))      in ("i4", "i8")
    assert ndr(np.dtype(float))    in ("f4", "f8")
    assert ndr(np.dtype(complex))  in ("c8", "c16")
    assert ndr(np.dtype(object))   == "O"
    assert ndr(np.dtype(str))[0]   == "V"
    assert ndr(np.dtype(bytes))    == "V0"


@given(dtname = st_dtype_name())
def test_normalized_dt_rep_from_names(dtname: str) -> None:
    ndr = v_generic.normalize_dt_rep

    normed = ndr(np.dtype(dtname))
    assert normed == dtname

    if dtname[0] in ("f", "u", "i", "c"):
        # endianness is supposed to be erased
        for variant in ["<", ">", "="]:
            assert ndr(np.dtype(variant + dtname)) == dtname


@given(name = st_identifier(), dtname = st_dtype_name())
def test_check_column_ok_name_eq(name: str, dtname: str) -> None:
    ndr = v_generic.normalize_dt_rep
    check_column = v_generic.check_column

    dtype = np.dtype(dtname)
    normed = ndr(dtype)
    col = make_ColumnObject(name, dtype = normed, name_regex = False)
    assert check_column(name, dtype, col) == []


@given(name = st_identifier(), dtname = st_dtype_name())
def test_check_column_ok_name_match(name: str, dtname: str) -> None:
    ndr = v_generic.normalize_dt_rep
    check_column = v_generic.check_column

    dtype = np.dtype(dtname)
    normed = ndr(dtype)
    col = make_ColumnObject(name, dtype = normed, name_regex = True)
    assert check_column(name, dtype, col) == []


@given(names = st_unequal_identifiers(), dtname = st_dtype_name())
def test_check_column_fail_name_ne(names: tuple[str, str], dtname: str) -> None:
    ndr = v_generic.normalize_dt_rep
    check_column = v_generic.check_column

    dtype = np.dtype(dtname)
    normed = ndr(dtype)
    col = make_ColumnObject(names[1], dtype = normed, name_regex = False)

    errors = check_column(names[0], dtype, col)
    assert len(errors) == 1
    assert "wrong name" in errors[0]
    assert f"expected {names[1]!r}" in errors[0]
    assert f"got {names[0]!r}" in errors[0]


@given(names = st_unequal_identifiers(), dtname = st_dtype_name())
def test_check_column_fail_name_mismatch(
        names: tuple[str, str], dtname: str
) -> None:
    ndr = v_generic.normalize_dt_rep
    check_column = v_generic.check_column

    dtype = np.dtype(dtname)
    normed = ndr(dtype)
    col = make_ColumnObject(names[1], dtype = normed, name_regex = True)

    errors = check_column(names[0], dtype, col)
    assert len(errors) == 1
    assert "wrong name" in errors[0]
    assert f"doesn't match /{names[1]}/" in errors[0]
    assert repr(names[0]) in errors[0]


@given(name = st_identifier(), dtnames = st_unequal_dtype_names())
def test_check_column_fail_dtype_ne(name: str, dtnames: str) -> None:
    ndr = v_generic.normalize_dt_rep
    check_column = v_generic.check_column

    dtype = np.dtype(dtnames[0])
    got_normed = ndr(dtype)
    exp_normed = ndr(np.dtype(dtnames[1]))
    col = make_ColumnObject(name, dtype = exp_normed)

    errors = check_column(name, dtype, col)
    assert len(errors) == 1
    assert "wrong dtype" in errors[0]
    assert f"expected {exp_normed}" in errors[0]
    assert f"got {got_normed}" in errors[0]


@given(name = st_identifier(),
       dtname = st_dtype_name().filter(lambda n: n[0] != "V"),
       dims = st_unequal_ndims())
def test_check_column_fail_ndims_ne(
    name: str, dtname: str, dims: tuple[int, int]
) -> None:
    ndr = v_generic.normalize_dt_rep
    check_column = v_generic.check_column

    dtype = np.dtype((dtname, (2,)*dims[0]))
    got_normed = ndr(dtype)
    exp_normed = ndr(np.dtype((dtname, (2,)*dims[1])))
    assert got_normed == exp_normed
    col = make_ColumnObject(name, dtype = exp_normed, ndim = dims[1])

    errors = check_column(name, dtype, col)
    assert len(errors) == 1
    assert "wrong item dimensionality" in errors[0]
    assert f"expected {dims[1]}" in errors[0]
    assert f"got {dims[0]}" in errors[0]


@given(record = st_record_dtype())
def test_check_schema_ok(record: np.dtype) -> None:
    ndr = v_generic.normalize_dt_rep

    names = record.names
    fields = record.fields
    assert names is not None
    assert fields is not None

    columns = [
        make_ColumnObject(name, dtype = ndr(fields[name][0]))
        for name in names
    ]

    dobj = make_DataObject(schema = columns)

    errors = v_generic.check_schema(record, dobj)
    assert errors == {}


@given(record = st_record_dtype())
def test_check_schema_fail_extra_fields(record: np.dtype) -> None:
    ndr = v_generic.normalize_dt_rep

    names = record.names
    fields = record.fields
    assert names is not None
    assert fields is not None

    for limit in range(len(names) - 1):
        columns = [
            make_ColumnObject(name, dtype = ndr(fields[name][0]))
            for name in names[:limit]
        ]

        dobj = make_DataObject(schema = columns)

        errors = v_generic.check_schema(record, dobj)
        assert errors == {
            i : [f"extra field {names[i]!r}"]
            for i in range(limit, len(names))
        }

@given(record = st_record_dtype())
def test_check_schema_fail_missing_fields(record: np.dtype) -> None:
    ndr = v_generic.normalize_dt_rep

    names = record.names
    fields = record.fields
    assert names is not None
    assert fields is not None
    columns = [
        make_ColumnObject(name, dtype = ndr(fields[name][0]))
        for name in names
    ]
    dobj = make_DataObject(schema = columns)

    for limit in range(len(names) - 1):
        trunc_record = np.dtype({
            'names': names[:limit],
            'formats': [fields[n][0] for n in names[:limit]]
        })

        errors = v_generic.check_schema(trunc_record, dobj)
        assert errors == {
            i : [f"field {names[i]!r} missing"]
            for i in range(limit, len(names))
        }


@given(record = st_record_dtype())
def test_check_schema_fail_reordered_fields(record: np.dtype) -> None:
    ndr = v_generic.normalize_dt_rep

    names = record.names
    fields = record.fields
    assert names is not None
    assert fields is not None

    rnames = names[-1:] + names[:-1]

    columns = [
        make_ColumnObject(name, dtype = ndr(fields[name][0]))
        for name in rnames
    ]
    dobj = make_DataObject(schema = columns)
    errors = v_generic.check_schema(record, dobj)

    exp_errors = {}
    for i in range(len(names)):
        exp_field_errors = []
        exp_name = rnames[i]
        got_name = names[i]
        exp_type = ndr(fields[exp_name][0])
        got_type = ndr(fields[got_name][0])
        assert exp_name != got_name
        exp_field_errors.append(
            f"wrong name: expected {exp_name!r}, got {got_name!r}"
        )
        if exp_type != got_type:
            exp_field_errors.append(
                f"wrong dtype: expected {exp_type}, got {got_type}"
            )
        exp_errors[i] = exp_field_errors

    assert errors == exp_errors



@given(val = st_metadata_value())
def test_check_meta_ok_eq(val: str | bool | float | int) -> None: # NOQA: FBT001
    md = make_ObjectMetadata(val)
    assert v_generic.check_meta(val, md) is None


@given(vals = st_unequal_metadata_same_type())
def test_check_meta_fail_ne(
    vals: tuple[str | bool | float | int, str | bool | float | int]
) -> None:
    md = make_ObjectMetadata(vals[1])
    assert v_generic.check_meta(vals[0], md) == \
        f"incorrect metadata value: expected {vals[1]!r}, got {vals[0]!r}"


@given(vals = st_unequal_metadata_diff_types())
def test_check_meta_fail_wrong_type(
    vals: tuple[str | bool | float | int, str | bool | float | int]
) -> None:
    md = make_ObjectMetadata(vals[1])
    assert v_generic.check_meta(vals[0], md) == \
        f"wrong type for metadata value: expected {type(vals[1])}, got {type(vals[0])}"
