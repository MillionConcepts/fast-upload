"""
Just checks: are we correctly turning the "make it fail if we don't have the
extension" knob?
"""

from io import BytesIO

import asdf
from asdf.tags.core import ExtensionMetadata, Software
import pytest

from mast_transfer_tools.io.asdf import asdfopen_generic


def _asdf_with_missing_extension() -> BytesIO:
    buff = BytesIO()

    afile = asdf.AsdfFile({
        "history": {
            "extensions": [
                ExtensionMetadata(
                    extension_class=(
                        "mast_transfer_tools.tests."
                        "DefinitelyNotInstalledExtension"
                    ),
                    extension_uri=(
                        "asdf://mast-transfer-tools/tests/extensions/"
                        "definitely-not-installed-1.0.0"
                    ),
                    software=Software(
                        name="definitely-not-installed",
                        version="1.0.0",
                    ),
                )
            ]
        },
        "data": {
            "some": "perfectly boring payload",
        },
    })

    afile.write_to(buff)
    buff.seek(0)
    return buff


def test_asdfopen_generic_fails_for_missing_declared_extension(
    tmp_path,
) -> None:
    path = tmp_path / "missing-extension.asdf"
    path.write_bytes(_asdf_with_missing_extension().getvalue())

    with pytest.raises(RuntimeError, match="not currently installed"):
        asdfopen_generic(str(path))
