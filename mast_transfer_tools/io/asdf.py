from typing import Any, Hashable, Mapping

import logging

import asdf
import asdf.tags.core
import astropy.table
from cytoolz import get_in, valfilter, merge, valmap
from hostess.aws.s3 import Bucket
import numpy as np
import pandas as pd
import pyarrow.lib

from mast_transfer_tools.io.s3 import S3Reader, DEFAULT_CHUNK_SIZE

LOG = logging.getLogger(__name__)

DEFAULT_ASDF_DATA_OBJECT_TYPES = (
    astropy.table.Table,
    asdf.tags.core.NDArrayType,
    np.ndarray,
    pd.DataFrame,
    pyarrow.lib.Table,
)


# NOTE: there is no consistent top-level tag class we can use to more
# consistently type this.
def sanitize_data_tag(node: Any, *, autoload: bool = False) -> Any:
    if isinstance(node, asdf.tags.core.NDArrayType):
        if autoload is True and node._array is None:
            return np.asarray(node)
        if node._array is not None:
            return node._array
    return node


def sanitize_schema_descr(descr: dict) -> str | dict | None:
    """Pull the "real" description from an ASDF schema description."""
    if descr is None:
        return descr
    if len(descr.keys()) == 1 and "description" in descr.keys():
        return descr["description"]
    return descr


def _unnest_to_pathkeys(
    nested: Mapping | list | tuple, levels: list[Hashable]
) -> list[dict[tuple[Hashable, ...,], Any]]:
    if hasattr(nested, "items"):
        items = tuple(nested.items())
    else:
        items = tuple((i, e) for i, e in enumerate(nested))
    long_records = []
    for level, item in items:
        if isinstance(item, (list, tuple, Mapping)):
            long_records += _unnest_to_pathkeys(item, [*levels, level])
        else:
            long_records.append({tuple((*levels, level)): item})
    return long_records


def unnest_to_pathkeys(nested: Mapping) -> dict[tuple[Hashable, ...], Any]:
    """
    Flatten a mapping to a list like

    [
      {(key level 1, key level 2, ...): value},
      ...
    ]
    """
    flat_records = _unnest_to_pathkeys(nested, [])
    return merge(flat_records)


def extract_objects(
    asdf_file: asdf.AsdfFile,
    datatypes: tuple[type] = DEFAULT_ASDF_DATA_OBJECT_TYPES,
    *,
    autoload: bool = False,
    use_full_paths: bool = True,
) -> tuple[
    dict[str | bool | int, Any] | dict[tuple[str | bool | int, ...], Any],
    dict[str | bool | int, Any] | dict[tuple[str | bool | int, ...], Any],
]:
    """
    Search for and return the "data" objects in an AsdfFile, as defined by
    DEFAULT_ASDF_DATA_OBJECT_TYPE.

    Returns a tuple like:
    ({path: object}, {path: schema description or None if no description})
    for each identified object.

    If use_full_paths is True, uses full object paths as keys; otherwise,
    uses last element of path (and logs a warning if any duplicated keys are
    discarded).
    """
    # NOTE: we can't simply iterate over asdf_file.search() here because:
    # 1. not all nodes can be traversed
    # 2. it will greedily load data objects under some circumstances
    #    (note that some data objects, like embedded astropy tables,
    #    are always greedily loaded anyway)
    flat_tree = valfilter(
        lambda v: isinstance(v, datatypes), unnest_to_pathkeys(asdf_file.tree)
    )
    flat_tree = valmap(
        lambda v: sanitize_data_tag(v, autoload=autoload), flat_tree
    )
    info = asdf_file.schema_info()
    descriptions = {
        k: sanitize_schema_descr(get_in(k, info)) for k in flat_tree.keys()
    }
    if use_full_paths is True:
        return flat_tree, descriptions
    if len(set(k[-1] for k in flat_tree.keys())) != len(flat_tree):
        LOG.warning(
            "use_full_paths is False, but some extracted node names are "
            "duplicates. Returned value will not contain all extracted nodes."
        )
    return (
        {k[-1]: v for k, v in flat_tree.items()},
        {k[-1]: v for k, v in descriptions.items()}
    )


def asdfopen_generic(
    key: str,
    bucket: Bucket | str | None = None,
    blocksize: int = DEFAULT_CHUNK_SIZE,
) -> asdf._asdf.AsdfFile:
    """Open an S3 object or local file as an AsdfFile."""
    if bucket is None:
        return asdf.open(key, strict_extension_check=True)

    if not isinstance(bucket, Bucket):
        bucket = Bucket(bucket)
    return asdf.open(
        S3Reader(bucket, key, chunk_size=blocksize),
        strict_extension_check=True
    )
