"""
Generation of label objects that describe individual files, and merging
those label objects to describe classes of files included in a data set.
"""

# Note: this file cannot contain anything that is used by the format-
# specific submodules, as this would create a circular dependency,
# which Python's import machinery cannot handle.  All of those things
# need to be in the 'generic' submodule instead.

import logging

from collections import defaultdict
from pathlib import Path

from hostess.aws.s3 import Bucket
from mast_transfer_tools.describe import (
    generic as describe_generic,
    asdf as describe_asdf,
    fits as describe_fits,
    parquet as describe_parquet
)
from mast_transfer_tools.describe.generic import FileDescription


LOG = logging.getLogger(__name__)


SUPPORTED_STANDARDS = {
    "asdf": describe_asdf,
    "fits": describe_fits,
    "parquet": describe_parquet,
}

PROBABLE_DOC_SUFFIXES = {
    "text", "txt",
    "markdown", "mdwn", "md",
    "tex", "ltx", "bib",
    "pdf", "doc", "docx",
    "html", "xhtml", "htm",
}


def describe_file(fn: str | Path, bucket: Bucket | None = None) -> FileDescription:
    """
    Examine the file `fn`, transparently decompressing it if necessary,
    and produce a description of that file suitable for a MAST label.
    """
    desc = FileDescription(fn=fn)
    suffixes = tuple(map(lambda suf: suf.lower(), Path(fn).suffixes))
    if "fit" in suffixes or "fits" in suffixes:
        std = "fits"
    elif "pqt" in suffixes or "parquet" in suffixes:
        std = "parquet"
    elif "asdf" in suffixes:
        std = "asdf"
    elif len(suffixes) == 0:
        std = "unknown"
    else:
        std = suffixes[-1]
    std = std.strip(".")
    desc.standard = std
    stdmod = SUPPORTED_STANDARDS.get(std)
    if stdmod is None:
        raise ValueError(
            f"Object-level description of {std} files is not supported."
        )
    desc.objects = stdmod.describe_file(desc.fn, bucket)
    return desc


def unify_descriptions(descs: list[FileDescription]) -> list[FileDescription]:

    stds: dict[str, list[FileDescription]] = defaultdict(list)
    for desc in descs:
        stds[desc.standard].append(desc)

    merged: list[FileDescription] = []
    for std, s_descs in stds.items():
        merged.extend(describe_generic.unify_descriptions(s_descs))

    return merged
