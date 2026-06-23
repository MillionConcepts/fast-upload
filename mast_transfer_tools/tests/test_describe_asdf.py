"""
Like ASDF validation tests, these aren't intended to be as comprehensive as
FITS and Parquet description tests due to the extreme potential diversity of
ASDF. They attempt to catch some likely ASDF-specific annoyances.
"""

from pathlib import Path
import re
from typing import Any, cast

import asdf
import asdf_astropy  # noqa: F401 - register ASDF converters for Astropy types
from astropy.table import MaskedColumn, Table
import numpy as np

from mast_transfer_tools import labels
import mast_transfer_tools.validation.asdf as validate_asdf
from mast_transfer_tools.describe import describe_file
from mast_transfer_tools.describe.asdf import unify_descriptions
from mast_transfer_tools.label_meta import to_yaml_repr
from mast_transfer_tools.labels import (
    ASDFDataObject,
    DataObject,
    FilePattern,
    Filetype,
    FiletypeValidationOptions,
)
from mast_transfer_tools.tests.test_validation_generic import assert_no_errors


def _write_asdf(path: Path, tree: dict[str, Any]) -> None:
    asdf.AsdfFile(tree).write_to(path)


def _small_catalog() -> Table:
    return Table(
        {
            "source_id": np.array([1, 2, 3], dtype="i4"),
            "flux": np.array([1.5, 2.5, 3.5], dtype="f4"),
            "good": np.array([True, False, True], dtype=np.bool_),
        }
    )


def _object_descriptions(paths: list[Path]) -> list[dict[str, Any]]:
    descriptions = [describe_file(path) for path in paths]
    objdescs, failure = unify_descriptions(descriptions)
    assert failure is None, f"description unification failed: {failure}"
    return [] if objdescs is None else objdescs


def _objects_from_descriptions(
    objdescs: list[dict[str, Any]],
) -> list[ASDFDataObject]:
    objects = [ASDFDataObject.from_yaml(to_yaml_repr(o)) for o in objdescs]
    assert not any(o.errors for o in objects)
    return objects


def _filetype(objects: list[ASDFDataObject]) -> Filetype:
    return Filetype(
        filename=[FilePattern(pattern=re.compile(r"(?:/|^).*\.asdf"))],
        standard="asdf",
        objects=cast(list[DataObject], objects),
        validation_options=FiletypeValidationOptions(skip=[]),
    )


def _schema_by_name(obj: ASDFDataObject) -> dict[str, labels.ColumnObject]:
    schema: dict[str, labels.ColumnObject] = {}
    for column in obj.schema:
        assert isinstance(column.name, str)
        schema[column.name] = column
    return schema


def _assert_asdf_validates(path: Path, ft: Filetype, message: str) -> None:
    with asdf.open(path) as afile:
        errors = validate_asdf.check_file(afile, ft)
    assert_no_errors(errors, message)


def test_asdf_description_roundtrip_nested_astropy_table(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.asdf"
    _write_asdf(
        path,
        {"roman": {"products": {"catalog": _small_catalog()}}},
    )

    objects = _objects_from_descriptions(_object_descriptions([path]))

    assert len(objects) == 2
    obj = objects[0]
    assert obj.name == ["roman", "products", "catalog"]
    assert obj.objtype == "astropy.table.table.table"

    assert objects[1].name == ["roman"]
    assert objects[1].objtype == "builtins.dict"

    schema = _schema_by_name(obj)
    assert schema["source_id"].dtype == "i4"
    assert schema["source_id"].ndim == 0
    assert schema["flux"].dtype == "f4"
    assert schema["flux"].ndim == 0
    assert schema["good"].dtype == "b1"
    assert schema["good"].ndim == 0

    _assert_asdf_validates(
        path,
        _filetype(objects),
        "described nested ASDF Astropy table does not validate",
    )


def test_asdf_description_preserves_astropy_vector_column_ndim(
    tmp_path: Path,
) -> None:
    path = tmp_path / "vectors.asdf"
    table = Table(
        {
            "source_id": np.array([1, 2], dtype="i4"),
            "centroid": np.array([[1.25, 2.5], [3.75, 4.0]], dtype="f8"),
        }
    )
    _write_asdf(path, {"catalog": table})

    objects = _objects_from_descriptions(_object_descriptions([path]))

    assert len(objects) == 1
    schema = _schema_by_name(objects[0])
    assert schema["centroid"].dtype == "f8"
    assert schema["centroid"].ndim == 1

    _assert_asdf_validates(
        path,
        _filetype(objects),
        "described ASDF Astropy table with vector column does not validate",
    )


def test_asdf_description_uses_masked_astropy_column_data_dtype(
    tmp_path: Path,
) -> None:
    path = tmp_path / "masked.asdf"
    table = Table()
    table["source_id"] = np.array([1, 2, 3], dtype="i4")
    table["flux"] = MaskedColumn(
        np.array([1.5, 2.5, 3.5], dtype="f4"),
        mask=[False, True, False],
    )
    _write_asdf(path, {"catalog": table})

    objects = _objects_from_descriptions(_object_descriptions([path]))

    assert len(objects) == 1
    schema = _schema_by_name(objects[0])
    assert schema["flux"].dtype == "f4"
    assert schema["flux"].ndim == 0

    _assert_asdf_validates(
        path,
        _filetype(objects),
        "described ASDF Astropy table with masked column does not validate",
    )


def test_asdf_description_unifies_repeated_astropy_table_names(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "catalogs_0.asdf", tmp_path / "catalogs_1.asdf"]
    _write_asdf(
        paths[0],
        {
            "products": {
                "catalog_0001": _small_catalog(),
                "catalog_0002": _small_catalog(),
            }
        },
    )
    _write_asdf(
        paths[1],
        {
            "products": {
                "catalog_0003": _small_catalog(),
                "catalog_0004": _small_catalog(),
            }
        },
    )

    objects = _objects_from_descriptions(_object_descriptions(paths))

    assert len(objects) == 2
    obj = objects[0]
    assert obj.repeated is True
    assert isinstance(obj.name, list)
    assert len(obj.name) == 2
    assert isinstance(obj.name[0], re.Pattern)
    assert isinstance(obj.name[1], re.Pattern)
    assert obj.name[0].fullmatch("products")
    assert obj.name[1].fullmatch("catalog_0001")
    assert obj.name[1].fullmatch("catalog_9999")

    ft = _filetype(objects)
    for path in paths:
        _assert_asdf_validates(
            path,
            ft,
            "described repeated ASDF Astropy tables do not validate",
        )
