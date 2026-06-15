"""
Utilities for wrangling whole-file compression formats.

Because MAST does not accept files compressed in any format other than
plain gzip, this module doesn't support reading or writing such files.
However, it is capable of identifying several other common whole-file
compression formats for diagnostic purposes.
"""

import os

from builtins import open as builtin_open
from gzip import GzipFile
from io import FileIO
from pathlib import Path
from typing import BinaryIO, Literal, TypeAlias, cast

from mast_transfer_tools.utilz.shims import close_or_forget


__all__ = (
    "MCFile",
    "SUPPORTED_COMPRESSION_EXTS",
    "RECOGNIZED_COMPRESSION_EXTS"
)


# MAST policy prefers to accept only uncompressed files, however
# gzipped files are sometimes allowed.
SUPPORTED_COMPRESSION_EXTS = (".gz",)


# Type alias for 'either a regular Python open-file object, in binary
# mode, or a compressed-file object for one of the supported compression
# formats.'  MC stands for 'maybe compressed'.
MCFile: TypeAlias = BinaryIO | GzipFile

# We try to *recognize* (and reject) all the compressed file types that
# might plausibly get included in a MAST data set by accident.  There's
# zillions more (see http://fileformats.archiveteam.org/wiki/Archiving
# and http://fileformats.archiveteam.org/wiki/Compression ); I think
# this is a reasonable first approximation to 'what might actually
# be encountered in the wild'.
#
# Note: file extensions are considered case-insensitively, erasing
# some no-longer-important distinctions (historically .z and .Z were
# different, for instance).
#
# Keys in this dictionary are the lowercased form of the canonical
# file extension for a particular compressed file format, and values
# are the canonical human-readable name for that format.
RECOGNIZED_COMPRESSION_EXTS = {
    # supported formats first
    ".gz":   "gzip",

    # these formats are not supported due to MAST policy
    ".bz2":  "bzip2",
    ".lz4":  "LZ4",   # Lempel-Ziv by itself, focused on fast decompression
    ".lzo":  "LZO",   # Lempel-Ziv-Oberhumer, also focused on fast decompression
    ".xz":   "XZ",    # xz container for LZMA compression
    ".zst":  "Zstandard",

    # these are multiple-file container formats that cannot be
    # transparently decompressed via the interface in this module
    ".zip":  "(PK)Zip",
    ".7z":   "7-Zip",

    # these formats are obsolete, do not have a public specification,
    # or there is no Python decompressor module for them
    ".bz":   "bzip 1",
    ".lz":   "LZ",   # alternative, rarely used LZMA-based compression format
    ".lzma": "LZMA", # legacy container for XZ-style LZMA compression
    ".rar":  "(Win)RAR",
    ".z":    "compress(1)",
}

# How many bytes we need to read at the beginning of the file to
# determine whether its in-band "magic number" agrees with its
# name extension.  This needs to be kept in sync with
# compression_format_for_magic, below.
LONGEST_COMPRESSION_MAGIC = 9

# open_maybe_compressed makes caller include the 'b' to ensure they know
# they need to wrap it themselves for text mode.
# If you're thinking "how does 'x+' make any sense", consider it as
# O_RDWR|O_CREAT|O_EXCL, as opposed to 'x' being O_WRONLY|O_CREAT|O_EXCL.
MCOpenMode: TypeAlias = Literal['rb', 'wb', 'xb', 'ab',
                                'r+b', 'w+b', 'x+b', 'a+b',
                                'rb+', 'wb+', 'xb+', 'ab+']


def open(name: Path, mode: MCOpenMode) -> tuple[MCFile, str | None]:
    """
    Like the built-in open(), but:

    - when opening for reading, if the filename extension on 'name'
      is one of the recognized whole-file compression extensions,
      checks whether the content of the file matches that extension,
      and, for the smaller set of *supported* compression algorithms,
      transparently decompresses the file contents.

    - when opening for writing, if the filename extension on 'name'
      indicates a supported compression algorithm, transparently
      compresses the file contents.

    Unlike the built-in open():

    - the first argument must be a pathlib.Path
    - the mode argument is mandatory
    - you cannot open a file in text mode (wrap the returned open-file
      object in an io.TextIOWrapper to get text mode).

    The return value is a 2-tuple of the open file object and the
    canonical extension for the compression format (_with_ a leading dot,
    like Path.suffix) or None if the file does not appear to be compressed.
    """
    if 'b' not in mode:
        raise TypeError(
            f"bad mode {mode!r}; utilz.compression.open() only does binary mode"
        )

    with close_or_forget(builtin_open(name, mode)) as guard:
        if 'r' in mode or '+' in mode:
            magic = os.pread(guard.resource.fileno(),
                             LONGEST_COMPRESSION_MAGIC, 0)
        else:
            magic = b''
        ext = check_compression_magic(magic, name)
        if ext is None:
            return (guard.forget(), None)
        elif ext == ".gz":
            return (closing_gzfile(fileobj=guard.forget(), mode=mode), ext)
        else:
            form = RECOGNIZED_COMPRESSION_EXTS[ext]
            raise ValueError(
                f"MAST does not accept files in {form} format"
            )


#
# Implementation
#


def closing_gzfile(*, fileobj: BinaryIO, mode: str) -> GzipFile:
    """As gzip.GzipFile(), except that 'fileobj' must be a file object,
    and closing the resulting GzipFile does close that object."""

    # This is a dirty hack, but the property it relies on has existed
    # unchanged since GzipFile grew the ability to wrap an existing
    # file object (in Python 3.3).
    gz = GzipFile(fileobj=fileobj, mode=mode)
    gz.myfileobj = cast(FileIO, fileobj)
    return gz


def check_compression_magic(magic: bytes, name: Path) -> str | None:
    """
    Verify that a file named NAME starts with the expected magic
    number for the compression format identified by the file's extension.
    MAGIC is the first N bytes of the file.

    If the file does not appear to be compressed, returns None.

    If the file's contents and name are consistent, returns the
    *canonical* name extension for that type of compression.

    Throws ValueError if the file's contents and name are inconsistent.
    """
    suffix: str | None = name.suffix.lower()
    if suffix not in RECOGNIZED_COMPRESSION_EXTS:
        suffix = None

    if len(magic) == 0:
        # file was just created or is empty, trust suffix
        return suffix

    fmt = compression_format_for_magic(magic)
    if fmt == suffix:
        return suffix    # correct magic number for the indicated format

    if suffix is None:
        s_are_what = "should be uncompressed"
    else:
        s_form = RECOGNIZED_COMPRESSION_EXTS[suffix]
        s_are_what = f"use {s_form} compression"

    if fmt is None:
        c_are_what = "are uncompressed"
    else:
        c_form = RECOGNIZED_COMPRESSION_EXTS[fmt]
        c_are_what = f"use {c_form} compression"

    raise ValueError(
        f"file extension indicates contents {s_are_what}"
        f" but they {c_are_what}"
    )


def compression_format_for_magic(magic: bytes) -> str | None:
    """
    Get the canonical file name extension for the compression format
    identified by the magic number MAGIC (i.e. the first N bytes of a
    file compressed using that format).  If the magic number doesn't
    correspond to a compression format we know about, returns None.
    """
    # many compression formats have regrettably weak magic numbers
    # therefore this series of tests must be kept sorted from longest
    # to shortest check string
    # if more formats are added, LONGEST_COMPRESSION_MAGIC may need
    # to be updated

    # see, this is how you do it properly
    if magic[:9] == b'\x89LZO\x00\x0D\x0A\x1A\x0A':
        return '.lzo'

    # these are acceptable
    if magic[:6] == b'\xFD7zXZ\x00':
        return '.xz'

    if magic[:6] == b'7z\xBC\xAF\x27\x1C':
        return '.7z'

    # this covers both the RAR 1.5--4.20 and >5.00 formats
    if magic[:6] == b'Rar!\x1a\x07':
        return '.rar'

    if magic[:4] == b'(\xb5/\xfd':
        return '.zst'

    if magic[:4] == b'\x04"M\x18':
        return '.lz4'

    # but this is bad (any four ASCII alphanumerics could plausibly
    # appear at the beginning of a text file)
    if magic[:4] == b'LZIP':
        return '.lz'

    # and this is worse, because technically zip files don't have
    # to begin with this code!  but we are not in a position to search
    # for the "end of central directory signature" which is more reliable
    if magic[:4] == b'PK\x03\x04':
        return '.zip'

    # similar problems with this one
    if magic[:3] == b']\x00\x00':
        return '.lzma'

    # oh come on now you're not even trying
    # (but at least there's no printable ASCII and it _is_ guaranteed
    # to be present at the beginning of the file)
    if magic[:3] == b'\x1F\x8B\x08':
        return '.gz'

    # if you look carefully you can see the disappointment
    if magic[:3] == b'BZh' and (0x31 <= magic[3] <= 0x39):
        return '.bz2'

    if magic[:3] == b'BZ0':
        return '.bz'

    if magic[:2] in (
        b'\x1F\x1E',
        b'\x1F\x1F',
        b'\x1F\x8B',
        b'\x1F\x9D',
        b'\x1F\x9E',
        b'\x1F\x9F',
        b'\x1F\xA0',
        b'\x1F\xA1',
        b'\x1F\xFF',
    ):
        return '.z'

    return None
