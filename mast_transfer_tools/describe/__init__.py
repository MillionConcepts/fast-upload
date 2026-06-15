"""
Generation of label objects that describe individual files, and merging
those label objects to describe classes of files included in a data set.
"""

# Note: this file cannot contain anything that is used by the format-
# specific submodules, as this would create a circular dependency,
# which Python's import machinery cannot handle.  All of those things
# need to be in the 'generic' submodule instead.

import logging
import os

from collections import defaultdict
from pathlib import Path

from mast_transfer_tools.describe import (
    generic as describe_generic,
    asdf as describe_asdf,
    fits as describe_fits,
    parquet as describe_parquet
)
from mast_transfer_tools.describe.generic import FileDescription
from mast_transfer_tools.utilz.compression import open as mc_open


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
    # TODO there are dozens more
}


def describe_file(fn: Path) -> FileDescription:
    """
    Examine the file `fn`, transparently decompressing it if necessary,
    and produce a description of that file suitable for a MAST label.
    """
    desc = FileDescription()
    desc.fn.append(fn)

    fp, cext = mc_open(fn, "rb")
    with fp:
        suffixes = fn.suffixes
        s = 1 if cext is None else 2
        std = suffixes[-s][1:].lower() if len(suffixes) >= s else "unknown"

        # alternative suffixes for a couple of formats we understand
        if std == "fit":
            std = "fits"
        elif std == "pqt":
            std = "parquet"

        desc.standard = std
        stdmod = SUPPORTED_STANDARDS.get(std)
        if stdmod is None:
            if std in PROBABLE_DOC_SUFFIXES:
                LOG.debug(
                    "%s: assuming a '%s' file is documentation",
                    fn, std
                )
                desc.standard = "documentation"
            else:
                LOG.debug(
                    "%s: structural analysis of '%s' files not yet supported",
                    fn, std
                )
        else:
            LOG.debug(
                "%s: analyzing as a '%s' file",
                fn, std
            )
            stdmod.describe_objects(desc, fp)
        return desc


def unify_descriptions(descs: list[FileDescription]) -> list[FileDescription]:

    stds: dict[str, list[FileDescription]] = defaultdict(list)
    for desc in descs:
        stds[desc.standard].append(desc)

    merged: list[FileDescription] = []
    for std, s_descs in stds.items():
        merged.extend(describe_generic.unify_descriptions(s_descs))

    return merged
