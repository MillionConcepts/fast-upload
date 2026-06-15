import sys
from pathlib import Path

from mast_transfer_tools.utilz.shims import path_walk

import pytest

def test_path_walk() -> None:
    our_mods = set(
        m for m in sys.modules.keys() if m.startswith("mast_transfer_tools.")
    )

    try:
        basefile = getattr(sys.modules["mast_transfer_tools"], "__file__")
        assert basefile is not None
        basepath = Path(basefile)
        assert basepath.name == "__init__.py"
        basedir = basepath.parent.resolve()
    except Exception as e:
        pytest.skip(f"looking for root of our package: {e}")

    expected_dirs = set()
    expected_files = set()
    root = Path("/")
    dot = Path(".")
    for m in our_mods:
        if (f := getattr(sys.modules[m], "__file__", None)) is not None:
            p = Path(f).relative_to(basedir)
            expected_files.add(p)
            p = p.parent
            while p != root and p != dot:
                expected_dirs.add(p)
                p = p.parent

    got_dirs = set()
    got_files = set()
    for entry in path_walk(basedir):
        if entry.is_dir(follow_symlinks=False):
            got_dirs.add(entry.path)
        elif entry.is_file(follow_symlinks=False):
            got_files.add(entry.path)

    # there may be files we don't expect, but all of the files we do expect
    # should have been encountered
    assert expected_dirs - got_dirs == set()
    assert expected_files - got_files == set()
