"""
Description of ASDF files
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import astropy.table
from typing import Literal, Any, Collection

from hostess.aws.s3 import Bucket
from mast_transfer_tools.describe.generic import (
    sanitize_object_description,
    unify_object_lists,
    FileDescription, GROUPPAT,
)
from mast_transfer_tools.io.asdf import extract_objects, asdfopen_generic
from mast_transfer_tools.labels import ASDF_TABLE_TYPES
from mast_transfer_tools.validation.generic import normalize_dt_rep


def describe_asdf_table(
    table: np.ndarray | astropy.table.Table | pa.Table | pd.DataFrame,
) -> dict[Literal["schema"], list[dict]]:
    """Generate description of an ASDF table-like object."""
    # NOTE: this is similar to Parquet file schema description, but notably
    # omits fallback to Parquet physical type. This is simply because
    # Arrow tables not stored in Parquet format _have_ no Parquet physical
    # types; Arrow and Parquet are compatible but not identical. So we just
    # describe unsupported logical types as 'O'.
    schema = []
    if isinstance(table, pa.Table):
        for field in table.schema.fields:
            name, ftype = field.name, field.type
            if pa.types.is_primitive(ftype) or pa.types.is_date(ftype):
                col = {"dtype": normalize_dt_rep(ftype.to_pandas_dtype())}
            elif pa.types.is_fixed_size_binary(ftype):
                col = {"dtype": f"V{ftype.byte_width}"}
            else:
                col = {"dtype": "O"}
            # NOTE: ndim not supported for nested pyarrow types
            schema.append(col | {"name": name, "ndim": 0})
    elif isinstance(table, astropy.table.Table):
        for colname, col in table.columns.items():
            column = {
                "name": colname,
                "dtype": normalize_dt_rep(col.dtype),
                "ndim": col.dtype.ndim,
            }
            schema.append(column)
    elif isinstance(table, np.ndarray):
        for name, dt_shape in table.dtype.fields.items():
            base = dt_shape[0]
            column = {
                "name": name,
                "dtype": normalize_dt_rep(base),
                "ndim": base.ndim,
            }
            schema.append(column)
    return {"schema": schema}


def describe_ndarray(
    arr: np.ndarray,
) -> dict[Literal["ndim", "dtype"], int | str]:
    """Generate a description of an ndarray."""
    return {"ndim": arr.ndim, "dtype": normalize_dt_rep(arr.dtype)}


def describe_asdf_object(obj: Any) -> dict[str, str | list[dict] | int]:
    """Generate a description of an ndarray or table-like object."""
    ot = type(obj)
    objtype = f"{ot.__module__}.{ot.__name__}".lower()
    if objtype == "numpy.ndarray" and len(obj.dtype) == 0:
        description = describe_ndarray(obj)
    elif objtype in ASDF_TABLE_TYPES:
        description = describe_asdf_table(obj)
    else:
        raise TypeError(
            f"Don't know how to describe ASDF data object of type {objtype}."
        )
    return description | {"objtype": objtype}


def _n_unique_object_sets(trees: list[list[dict]]) -> int:
    """How many unique sets of objects exist among these trees?"""
    return len(set(frozenset([o["group_id"] for o in t]) for t in trees))


def assign_unordered_stemgroups(
    tree: list[dict], stems: list[str]
) -> str | None:
    """
    Heuristically group object names by stemming likely 'repeated' object
    names (suffixed with numbers).
    """
    for obj in tree:
        if m := GROUPPAT.match(obj["name"][-1]):
            matches = [
                s
                for s in stems
                if (s[-1] == m.group(1)) and (s[:-1] == obj["name"][:-1])
            ]
        else:
            matches = []
        if len(matches) > 1:
            # should not actually be able to happen
            return "redundant stems"
        elif len(matches) == 1:
            obj["group_id"] = matches[0]
    return None


def chunk_repeated_unordered_objects(
    trees: list[list[dict]]
) -> tuple[list[list[dict]], str | None]:
    """
    Find groups of 'repeated' unordered objects (notionally ASDF nodes)
    shared among all elements of `trees`. Limited to finding 'repetitions'
    defined by variable numeric / underscore patterns suffixed to some stem,
    performing stemming only on the final element of the path (which is a
    tuple of str | int | bool).

    Unlike rules for FITS HDULs and table schemata, consistent ordering is
    not required with respect to other nodes across all elements of `trees` --
    this would make no sense, as there is no canonical ordering on ASDF trees.
    """
    # everything is the same; moving on
    if _n_unique_object_sets(trees) < 2:
        return trees, None
    shared = set(obj["name"] for obj in trees[0])
    unshared = set()
    for tree in trees[1:]:
        names = set(obj["name"] for obj in tree)
        shared = shared.intersection(names)
        unshared = unshared.union(shared.symmetric_difference(names))
    stems = set()
    for u in unshared:
        if m := GROUPPAT.match(u[-1]):
            stems.add((*u[:-1], m.group(1)))
    if not stems:
        return trees, None
    for i, tree in enumerate(trees):
        failure = assign_unordered_stemgroups(tree, stems)
        if failure is not None:
            return trees, f"failed grouping on {i}: {failure}"
        trees[i] = tree
    return trees, None


def unify_tree_descriptions(
    object_descriptions: list[list[dict]],
) -> tuple[dict | None, str | None]:
    """"""
    trees = []
    for d in object_descriptions:
        trees.append([o | {"group_id": o["name"]} for o in d])
    trees, failure = chunk_repeated_unordered_objects(trees)
    if failure is not None:
        return None, failure
    if _n_unique_object_sets(trees) > 1:
        return (
            None,
            "variation in tree structure too complex to automatically describe",
        )
    return unify_object_lists(trees)


def unify_descriptions(
    descriptions: Collection[FileDescription],
) -> tuple[list[dict] | None, str | None]:
    """
    Attempt to unify a collection of ASDF file descriptions into a list of
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
    if not all(d.standard == "asdf" for d in descriptions):
        return None, "Not all files are ASDF"
    if max(len(d.objects) for d in descriptions) == 0:
        # none of these files have any objects that look like they're worth
        # mentioning. Weird case! Situation might sometimes warrant a warning
        # -- perhaps they're storing data in some nonstandard object type, or
        # the files might even be mangled. This function shouldn't emit that
        # warning, though.
        return [], None
    objs, failure = unify_tree_descriptions([d.objects for d in descriptions])
    if failure is not None:
        return None, failure
    return [sanitize_object_description(o) for o in objs.values()], None


def describe_file(fn: str | Path, bucket: Bucket | None = None) -> list[dict]:
    """Describe objects in an individual ASDF file."""
    obj_descriptions = []
    asdf_file = asdfopen_generic(fn, bucket)
    try:
        for path, obj in extract_objects(asdf_file, autoload=True)[0].items():
            obj_descriptions.append(describe_asdf_object(obj) | {"name": path})
    finally:
        asdf_file.close()
    return obj_descriptions
