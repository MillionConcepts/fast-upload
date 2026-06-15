"""
ASDF is a much broader format than FITS or Parquet, and most validation
plumbing failures will be caught by tests in other modules, so these don't
attempt to be as comprehensive as the FITS + Parquet property-based tests.
They just attempt to look for some likely ASDF-specific badness.
"""

import io
import re

import asdf
import numpy as np

from mast_transfer_tools import labels
from mast_transfer_tools.tests.test_validation_generic import assert_no_errors
import mast_transfer_tools.validation.asdf as asdf_validation


def make_asdf_column(
    name: str,
    *,
    dtype: str,
    name_regex: bool = False,
    ndim: int = 0,
    lpath: str = "/",
) -> labels.ColumnObject:
    return labels.ColumnObject(
        repeated=False,
        name_regex=name_regex,
        name=re.compile(name) if name_regex else name,
        dtype=dtype,
        ndim=ndim,
        lpath=lpath,
    )


def make_asdf_object(
    *,
    name: str | list[str | int | re.Pattern[str]],
    objtype: str,
    schema: list[labels.ColumnObject] | None = None,
    dtype: str | None = None,
    ndim: int | None = None,
    name_regex: bool = False,
    repeated: bool = False,
    optional: bool = False,
    value=None,
    value_regex: bool = False,
    lpath: str = "/",
) -> labels.ASDFDataObject:
    return labels.ASDFDataObject(
        name=name,
        objtype=objtype,
        schema=[] if schema is None else schema,
        dtype=dtype,
        ndim=ndim,
        name_regex=name_regex,
        repeated=repeated,
        optional=optional,
        value=value,
        value_regex=value_regex,
        metadata={},
        lpath=lpath,
    )


def make_asdf_filetype(
    *objects: labels.ASDFDataObject,
    skip: list[str] | None = None,
) -> labels.Filetype:
    return labels.Filetype(
        standard="asdf",
        filename=[
            labels.FilePattern(
                lpath="/filetypes/asdftest/filename/0",
                pattern=re.compile(r".*\.asdf"),
            )
        ],
        objects=list(objects),
        validation_options=labels.FiletypeValidationOptions(
            skip=[] if skip is None else skip,
        ),
        lpath="/filetypes/asdftest",
    )


def test_asdf_nested_array_validation_ok() -> None:
    afile = asdf.AsdfFile({"science": {"image": np.zeros((2, 3), dtype="f4")}})

    ft = make_asdf_filetype(
        make_asdf_object(
            name=["science", "image"],
            objtype="numpy.ndarray",
            dtype="f4",
            ndim=2,
        )
    )

    errors = asdf_validation.check_file(afile, ft)
    assert_no_errors(errors, "ASDF array does not conform to spec")


def test_asdf_array_validation_ok_after_roundtrip() -> None:
    buf = io.BytesIO()

    asdf.AsdfFile({"data": np.arange(6, dtype="i2").reshape(2, 3)}).write_to(
        buf
    )

    buf.seek(0)
    with asdf.open(buf) as afile:
        ft = make_asdf_filetype(
            make_asdf_object(
                name=["data"],
                objtype="numpy.ndarray",
                dtype="i2",
                ndim=2,
            )
        )

        errors = asdf_validation.check_file(afile, ft)

    assert_no_errors(errors, "round-tripped ASDF array failed validation")


def test_asdf_array_validation_reports_dtype_and_ndim_mismatch() -> None:
    afile = asdf.AsdfFile({"image": np.zeros((2, 3), dtype="f4")})

    ft = make_asdf_filetype(
        make_asdf_object(
            name=["image"],
            objtype="numpy.ndarray",
            dtype="f8",
            ndim=1,
        )
    )

    errors = asdf_validation.check_file(afile, ft)

    assert "root[image]/array_props" in errors
    assert any(
        "Invalid dimensionality" in e
        for e in errors["root[image]/array_props"]
    )
    assert any("invalid dtype" in e for e in errors["root[image]/array_props"])


def test_asdf_structured_array_schema_validation_ok() -> None:
    table = np.array(
        [(1, 2.5), (2, 3.5)], dtype=[("id", "i4"), ("flux", "f8")]
    )

    afile = asdf.AsdfFile({"catalog": table})

    ft = make_asdf_filetype(
        make_asdf_object(
            name=["catalog"],
            objtype="numpy.ndarray",
            schema=[
                make_asdf_column("id", dtype="i4"),
                make_asdf_column("flux", dtype="f8"),
            ],
        )
    )

    errors = asdf_validation.check_file(afile, ft)
    assert_no_errors(
        errors, "structured ASDF array does not conform to schema"
    )


def test_asdf_scalar_value_validation_ok() -> None:
    afile = asdf.AsdfFile({
        "meta": {
            "instrument": "NIRCam"
        }
    })

    ft = make_asdf_filetype(make_asdf_object(
        name=["meta", "instrument"],
        objtype="str",
        value="NIRCam",
    ))

    errors = asdf_validation.check_file(afile, ft)
    assert_no_errors(errors, "scalar ASDF value failed validation")


def test_asdf_structured_array_schema_validation_reports_bad_column() -> None:
    table = np.array([(1, 2.5)], dtype=[("id", "i4"), ("flux", "f4")])

    afile = asdf.AsdfFile({"catalog": table})

    ft = make_asdf_filetype(
        make_asdf_object(
            name=["catalog"],
            objtype="numpy.ndarray",
            schema=[
                make_asdf_column("id", dtype="i4"),
                make_asdf_column("flux", dtype="f8"),
            ],
        )
    )

    errors = asdf_validation.check_file(afile, ft)

    assert "root[catalog]/schema" in errors
    assert 1 in errors["root[catalog]/schema"]
    assert any(
        "wrong dtype: expected f8, got f4" in e
        for e in errors["root[catalog]/schema"][1]
    )


def test_asdf_repeated_regex_objects_ok() -> None:
    afile = asdf.AsdfFile(
        {
            "image1": np.zeros((2, 2), dtype="f4"),
            "image2": np.ones((2, 2), dtype="f4"),
        }
    )

    ft = make_asdf_filetype(
        make_asdf_object(
            name=[re.compile(r"image\d+")],
            name_regex=True,
            repeated=True,
            objtype="numpy.ndarray",
            dtype="f4",
            ndim=2,
        )
    )

    errors = asdf_validation.check_file(afile, ft)
    assert_no_errors(errors, "repeated ASDF regex object validation failed")


def test_asdf_nonrepeated_regex_multiple_matches_fails() -> None:
    afile = asdf.AsdfFile(
        {
            "image1": np.zeros((2, 2), dtype="f4"),
            "image2": np.ones((2, 2), dtype="f4"),
        }
    )

    ft = make_asdf_filetype(
        make_asdf_object(
            name=[re.compile(r"image\d+")],
            name_regex=True,
            repeated=False,
            objtype="numpy.ndarray",
            dtype="f4",
            ndim=2,
        )
    )

    errors = asdf_validation.check_file(afile, ft)

    assert errors


def test_asdf_validation_deep_tree_array_ok() -> None:
    arr = np.arange(12, dtype="f4").reshape(3, 4)

    afile = asdf.AsdfFile(
        {
            "roman": {
                "calibration": [
                    {
                        "junk": {
                            "why": "is this here",
                            "data": np.zeros(2, dtype="i2"),
                        }
                    },
                    {
                        "exposures": {
                            "exp_0001": {
                                "detectors": [
                                    {
                                        "name": "WFI01",
                                        "products": {
                                            "rate": {
                                                "arrays": [
                                                    {
                                                        "kind": "dq",
                                                        "data": np.zeros(
                                                            (3, 4),
                                                            dtype="u1",
                                                        ),
                                                    },
                                                    {
                                                        "kind": "sci",
                                                        "payload": {
                                                            "seriously": {
                                                                "the_data": arr,
                                                            }
                                                        },
                                                    },
                                                ]
                                            }
                                        },
                                    }
                                ]
                            }
                        }
                    },
                ]
            }
        }
    )

    ft = make_asdf_filetype(
        make_asdf_object(
            name=[
                "roman",
                "calibration",
                1,
                "exposures",
                "exp_0001",
                "detectors",
                0,
                "products",
                "rate",
                "arrays",
                1,
                "payload",
                "seriously",
                "the_data",
            ],
            objtype="numpy.ndarray",
            dtype="f4",
            ndim=2,
            lpath="/filetypes/asdftest/objects/0",
        )
    )

    errors = asdf_validation.check_file(afile, ft)

    assert_no_errors(errors, "deep ASDF tree array does not conform to spec")


def test_asdf_validation_deep_tree_regex_path_ok() -> None:
    arr = np.arange(6, dtype="i2").reshape(2, 3)

    afile = asdf.AsdfFile(
        {
            "roman": {
                "calibration": [
                    {"decoy": np.zeros(1, dtype="f4")},
                    {
                        "exposures": {
                            "exp_0007": {
                                "detector_WFI03": {
                                    "products": {
                                        "cal_step_12": {
                                            "arrays": [
                                                {"kind": "dq"},
                                                {
                                                    "kind": "science",
                                                    "data": arr,
                                                },
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    },
                ]
            }
        }
    )

    ft = make_asdf_filetype(
        make_asdf_object(
            name=[
                r"\Aroman\Z",
                r"\Acalibration\Z",
                1,
                r"\Aexposures\Z",
                r"\Aexp_[0-9]{4}\Z",
                r"\Adetector_WFI[0-9]{2}\Z",
                r"\Aproducts\Z",
                r"\Acal_step_[0-9]+\Z",
                r"\Aarrays\Z",
                1,
                r"\Adata\Z",
            ],
            name_regex=True,
            objtype="numpy.ndarray",
            dtype="i2",
            ndim=2,
            lpath="/filetypes/asdftest/objects/0",
        )
    )

    errors = asdf_validation.check_file(afile, ft)

    assert_no_errors(
        errors, "deep ASDF regex path array does not conform to spec"
    )


def test_asdf_validation_deep_tree_array_reports_failure_at_deep_path() -> (
    None
):
    afile = asdf.AsdfFile(
        {
            "maze": [
                {
                    "left": {
                        "right": [
                            {"nope": "trash"},
                            {
                                "bottom": {
                                    "data": np.zeros((2, 2), dtype="u1"),
                                }
                            },
                        ]
                    }
                }
            ]
        }
    )

    ft = make_asdf_filetype(
        make_asdf_object(
            name=[
                "maze",
                0,
                "left",
                "right",
                1,
                "bottom",
                "data",
            ],
            objtype="numpy.ndarray",
            dtype="f4",
            ndim=3,
            lpath="/filetypes/asdftest/objects/0",
        )
    )

    errors = asdf_validation.check_file(afile, ft)

    key = "root[maze][0][left][right][1][bottom][data]/array_props"
    assert key in errors
    assert any("Invalid dimensionality" in e for e in errors[key])
    assert any("invalid dtype" in e for e in errors[key])
