import datetime as dt
from numbers import Number
from operator import eq
import re
from types import MappingProxyType as MPt
from typing import Any, Callable

from asdf import AsdfFile
import astropy
from dustgoggles.dynamic import exc_report
import pandas as pd

from mast_transfer_tools.labels import (
    Filetype,
    FiletypeValidationOptions,
    DataObject,
)
from mast_transfer_tools.utilz.english import a_noun, a_type, repr_rx
from mast_transfer_tools.validation.generic import (
    check_schema,
    normalize_dt_rep,
)


YAML_SCALAR_TYPES = (bool, str, Number, dt.datetime, None)


def comparable_to_yaml_literal(obj: Any) -> bool:
    """
    Is this object viable for strict equality comparison to YAML 'literal'?
    """
    # NOTE: nested YAML sequences / mappings not supported for equality
    #  comparison
    if isinstance(obj, list):
        return all(isinstance(e, YAML_SCALAR_TYPES) for e in obj)
    if isinstance(obj, dict):
        return all(isinstance(e, YAML_SCALAR_TYPES) for e in obj.values())
    return isinstance(obj, YAML_SCALAR_TYPES)


def check_obj_type(
    obj: Any, spec: DataObject, _valopts: FiletypeValidationOptions
) -> list[str] | None:
    typename = spec.objtype
    if typename is None:
        return None
    typename = typename.lower()
    ot = type(obj)
    if (
        ot.__name__.lower() == typename
        or f"{ot.__module__}.{ot.__name__}".lower() == typename
        # don't require specifying the special ASDF lazy-loading
        # ndarray node type
        or (ot.__name__ == "NDArrayType" and "ndarray" in typename)
    ):
        return None
    return [
        f"Incorrect object type: expected {a_noun(typename)}, got {a_type(ot)}"
    ]


def check_obj_value(
    obj: Any, spec: DataObject, _valopts: FiletypeValidationOptions
) -> list[str] | None:
    if spec.value is None:
        return None
    if not comparable_to_yaml_literal(obj):
        return [f"Cannot compare {a_type(obj)} to a YAML literal"]
    if spec.value_regex:
        assert isinstance(spec.value, re.Pattern)
        obj_rep = str(obj)
        if not spec.value.match(obj_rep):
            return [
                f"string representation of object did not match regex: expected "
                f"match to {repr_rx(spec.value)}, got {obj_rep!r}"
            ]
    else:
        if isinstance(obj, complex):
            try:
                val = complex(spec.value)
            except ValueError:
                return [
                    f"attempted strict value comparison to complex, but value in "
                    f"label ({spec.value!r}) could not be interpreted as complex."
                ]
        else:
            val = spec.value
        if val != obj:
            return [f"incorrect value: expected {val!r}, got {obj!r}"]
    return None


def check_obj_schema(
    obj: Any, spec: DataObject, _valopts: FiletypeValidationOptions
) -> dict[str, list[str]] | None:
    if not spec.schema:
        return None
    if isinstance(obj, astropy.table.Table):
        dtype = obj.as_array().dtype
    elif isinstance(obj, pd.DataFrame):
        dtype = obj.to_records().dtype
    elif hasattr(obj, "dtype"):
        dtype = obj.dtype
    else:
        return {
            "base": [f"Don't know how to interpret {a_type(obj)} as a table"]
        }
    if len(dtype) == 0:
        return {
            "base": [
                f"Can't interpret object with scalar dtype ({obj.dtype}) as "
                f"a table"
            ]
        }
    failures = check_schema(dtype, spec)
    return failures if len(failures) > 0 else None


def check_obj_array_props(
    obj: Any, spec: DataObject, valopts: FiletypeValidationOptions
) -> list[str] | None:
    if spec.dtype is None and spec.ndim is None:
        return None
    if "dtype" in valopts.skip and "ndim" in valopts.skip:
        return None
    if not hasattr(obj, "dtype"):
        return [
            f"dtype or ndim specified, but this does not appear to be an "
            f"ndarray-like object. (Type is {a_type(obj)})"
        ]
    if len(obj.dtype) > 0:
        return [
            "dtype and ndim checks are only supported for arrays with scalar "
            "dtypes. Use 'schema' to define more complicated dtypes."
        ]
    failures = []
    # NOTE: it's not totally clear if there's a way for an array to be mangled
    #  at data level in an ASDF file but still have these attributes look ok
    #  in the unloaded tag.

    # checking most attributes of an unloaded NDArrayTag causes array load.
    # 'ndim' is included. however,'shape' and 'dtype' are safe. don't change
    # 'len(obj.shape)' to 'ndim'.
    if spec.ndim is not None and "ndim" not in valopts.skip:
        if len(obj.shape) != spec.ndim:
            failures.append(
                f"Invalid dimensionality: expected {spec.ndim}, got "
                f"{len(obj.shape)}"
            )
    dt = normalize_dt_rep(obj.dtype)
    if (
        spec.dtype is not None
        and "dtype" not in valopts.skip
        and dt != spec.dtype
    ):
        failures.append(f"invalid dtype: expected {spec.dtype}, got {dt}")
    return failures if len(failures) > 0 else None


OBJ_CHECK_MAP = MPt(
    {
        "objtype": check_obj_type,
        "array_props": check_obj_array_props,
        "schema": check_obj_schema,
        "value": check_obj_value,
    }
)


# NOTE: The use of the unconstrained type 'Any' throughout this
#  module to represent an object extracted from an ASDF file tree is
#  unfortunate but necessary. The ASDF standard allows users to declare objects
#  of any (existing or hypothetical) Python type, or, indeed, any type in any
#  (existing or hypothetical) member of the set of all type systems
def check_obj(
    obj: Any, obj_spec: DataObject, options: FiletypeValidationOptions
) -> dict[str, str]:
    failures = {}
    for checkname, checkfunc in OBJ_CHECK_MAP.items():
        if checkname in options.skip:
            continue
        try:
            failures[checkname] = checkfunc(obj, obj_spec, options)
        except Exception as ex:
            failures[checkname] = {"check_function_failure": exc_report(ex)}
    return {k: v for k, v in failures.items() if v is not None}


def _progress_matches(
    matches: list[tuple[str, Any]],
    key: str | int,
    equal: Callable[[str, str], bool],
) -> list[tuple[str, Any]]:
    new_matches = []
    for p, m in matches:
        if isinstance(m, list) and isinstance(key, int) and len(m) > key:
            new_matches.append((f"{p}[{key}]", m[key]))
        elif hasattr(m, "items"):
            new_matches += [
                (f"{p}[{k}]", v) for k, v in m.items() if equal(key, k)
            ]
    return new_matches


def find_objects(file: AsdfFile, objspec: DataObject) -> list[tuple[str, Any]]:
    if isinstance(objspec.name, list):
        if len(objspec.name) == 0:
            return []
        # no, we can't just iterate over all the paths (not all nodes are
        # traversable); no, there's no way to directly fetch an object by its
        # path (only schema info) or do path-sensitive searches
        equal = re.match if objspec.name_regex else eq
        name_ix, matches = 0, [("root", file.tree)]
        while name_ix < len(objspec.name):
            matches = _progress_matches(matches, objspec.name[name_ix], equal)
            name_ix += 1
        return matches
    result = file.search(objspec.name)
    if objspec.name_regex:
        return list(zip(result.paths, result.nodes))
    return [
        (p, n)
        for (p, n) in zip(result.paths, result.nodes)
        # no, there's no way to directly get the plain name in the general case
        if p.split("[")[-1][1:-2] == objspec.name
    ]


def check_file(file: AsdfFile, spec: Filetype) -> dict[str, list[str]]:
    if "all" in spec.validation_options.skip:
        return {}
    failures = {}
    for objspec in spec.objects:
        matches = find_objects(file, objspec)
        if len(matches) == 0 and not objspec.optional:
            failures[f"{objspec.nice_name}/base"] = ["missing"]
        if len(matches) == 0:
            continue
        if len(matches) > 1 and not objspec.repeated:
            failures[f"{objspec.nice_name}/base"] = "too many matches"
        for path, obj in matches:
            obj_failures = check_obj(obj, objspec, spec.validation_options)
            for key, k_failures in obj_failures.items():
                failures[f"{path}/{key}"] = k_failures
    return failures
