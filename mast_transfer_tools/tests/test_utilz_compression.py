"""
Tests of utilz.compression
"""
# ruff: noqa: F401, F811   # Ruff doesn't understand importation of fixtures

from pathlib import Path
from re import escape
from itertools import combinations, product

import pytest

from mast_transfer_tools.utilz import compression
from mast_transfer_tools.tests.filedata import (
    compressed_files,
    compressed_exts,
    uncompressed_files,
    uncompressed_exts,
)


def test_exts_lists() -> None:
    supported = frozenset(compression.SUPPORTED_COMPRESSION_EXTS)
    recognized = frozenset(compression.RECOGNIZED_COMPRESSION_EXTS)
    c_examples = compressed_exts
    u_examples = uncompressed_exts

    assert supported.issubset(recognized)
    assert recognized == c_examples
    assert recognized.isdisjoint(u_examples)


@pytest.mark.parametrize(
    "ext", compressed_exts
)
def test_recognition_match_compressed(
    ext: str,
    compressed_files: dict[str, bytes]
) -> None:
    data = compressed_files[ext]
    assert compression.compression_format_for_magic(data) == ext
    assert compression.check_compression_magic(data, Path("x" + ext)) == ext


@pytest.mark.parametrize(
    "ext", uncompressed_exts
)
def test_recognition_match_uncompressed(
    ext: str,
    uncompressed_files: dict[str, bytes]
) -> None:
    data = uncompressed_files[ext]
    assert compression.compression_format_for_magic(data) is None
    assert compression.check_compression_magic(
        data, Path("x" + ext)
    ) is None


@pytest.mark.parametrize(
    ("e1","e2"),
    combinations(compressed_exts, 2)
)
def test_recognition_mismatch_compressed(
    e1: str,
    e2: str,
    compressed_files: dict[str, bytes]
) -> None:
    d1 = compressed_files[e1]
    d2 = compressed_files[e2]
    n1 = escape(compression.RECOGNIZED_COMPRESSION_EXTS[e1])
    n2 = escape(compression.RECOGNIZED_COMPRESSION_EXTS[e2])

    with pytest.raises(
            ValueError,
            match=f"contents use {n2} compression but they use {n1} "
    ):
        compression.check_compression_magic(d1, Path("x" + e2))
    with pytest.raises(
            ValueError,
            match=f"contents use {n1} compression but they use {n2} "
    ):
        compression.check_compression_magic(d2, Path("x" + e1))


@pytest.mark.parametrize(
    ("cext","uext"), product(
        compressed_exts,
        uncompressed_exts
    )
)
def test_recognition_mismatch_uncompressed(
    cext: str,
    uext: str,
    uncompressed_files: dict[str, bytes],
    compressed_files: dict[str, bytes],
) -> None:
    udata = uncompressed_files[uext]
    cdata = compressed_files[cext]

    cname = escape(compression.RECOGNIZED_COMPRESSION_EXTS[cext])
    with pytest.raises(
            ValueError,
            match=f"contents use {cname} compression but they are uncompressed"
    ):
        compression.check_compression_magic(udata, Path("x" + cext))

    with pytest.raises(
            ValueError,
            match=f"should be uncompressed but they use {cname} compression"
    ):
        compression.check_compression_magic(cdata, Path("x" + uext))


@pytest.mark.parametrize(
    "ext", compressed_exts
)
def test_open_for_read_compressed(
    ext: str,
    compressed_files: dict[str, bytes],
    tmp_path: Path,
) -> None:
    fname = tmp_path / ("x" + ext)

    data = compressed_files[ext]
    with open(fname, "xb") as fp:
        fp.write(data)

    if ext in compression.SUPPORTED_COMPRESSION_EXTS:
        fp2, ext2 = compression.open(fname, "rb")
        assert ext == ext2
        with fp2:
            data2 = fp2.read()
            assert data2 == b""
    else:
        with pytest.raises(ValueError, match="MAST does not accept"):
            compression.open(fname, "rb")


@pytest.mark.parametrize(
    "ext", uncompressed_exts
)
def test_open_for_read_uncompressed(
    ext: str,
    uncompressed_files: dict[str, bytes],
    tmp_path: Path,
) -> None:
    fname = tmp_path / ("x" + ext)

    data = uncompressed_files[ext]
    with open(fname, "xb") as fp:
        fp.write(data)

    fp2, ext2 = compression.open(fname, "rb")
    assert ext2 is None
    with fp2:
        data2 = fp2.read()
        assert data2 == data


@pytest.mark.parametrize(
    ("uext","cext"), product(
        uncompressed_exts,
        ("",) + compression.SUPPORTED_COMPRESSION_EXTS
    )
)
def test_open_for_write_supported(
    uext: str,
    cext: str,
    uncompressed_files: dict[str, bytes],
    tmp_path: Path,
) -> None:
    fname = tmp_path / ("x" + uext + cext)

    data = uncompressed_files[uext]
    fp, cext2 = compression.open(fname, "xb")
    assert cext2 == (cext if cext != "" else None)
    with fp:
        fp.write(data)

    fp2, cext3 = compression.open(fname, "rb")
    assert cext3 == (cext if cext != "" else None)
    with fp2:
        data2 = fp2.read()
        assert data == data2

    with open(fname, "rb") as fp3:
        data3 = fp3.read()
        if cext == "":
            assert data == data3
        else:
            assert compression.compression_format_for_magic(data3) == cext
