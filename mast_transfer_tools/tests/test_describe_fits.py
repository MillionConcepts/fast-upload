import re
from typing import cast

from astropy.io import fits
import yaml

from mast_transfer_tools.describe import describe_file
from mast_transfer_tools.describe.fits import unify_descriptions
from mast_transfer_tools import labels, validation
from mast_transfer_tools.labels import (
    DataObject,
    FITSDataObject,
    FilePattern,
    Filetype,
    FiletypeValidationOptions,
)
from mast_transfer_tools.tests.test_validation_fits import (
    st_fits_filetype, st_hdul
)
from mast_transfer_tools.tests.test_validation_generic import assert_no_errors

import pytest
from hypothesis import given, strategies as st


@st.composite
def st_filetype_with_hduls(
    draw: st.DrawFn
) -> tuple[labels.Filetype, list[fits.HDUList]]:
    ft = draw(st_fits_filetype())
    hduls = draw(st.lists(
        st_hdul(ft),
        min_size=1, max_size = 3
    ))
    return ft, hduls


# This uses tmp_path_factory instead of tmp_path to work around
# Hypothesis's unfortunate semantics for function-scope fixtures, see
# https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.HealthCheck.function_scoped_fixture
@given(st_filetype_with_hduls())
def test_random_fits_description_roundtrip(
    tmp_path_factory: pytest.TempPathFactory,
    tcase: tuple[labels.Filetype, list[fits.HDUList]],
) -> None:
    ft_out, hduls = tcase
    assert_no_errors(
        ft_out.errors,
        "test precondition failed: invalid filetype example"
    )
    tmp_path = tmp_path_factory.mktemp("random-fits-desc-roundtrip-",
                                       numbered=True)
    paths = []
    for i, hdul in enumerate(hduls):
        path = tmp_path / f"{i}.fits"
        paths.append(path)
        hdul.writeto(path, overwrite=True)
    descriptions = [describe_file(p) for p in paths]
    objdescs, failure = unify_descriptions(descriptions)
    assert failure is None, "description unification failed"
    if objdescs is None:
        objdescs = []
    # cast needed because list[FITSDataObject] isn't assignment
    # compatible with list[DataObject] for tedious type theory reasons
    objects = cast(list[DataObject], [
        FITSDataObject.from_text(yaml.dump(o))
        for o in objdescs
    ])
    assert not any(o.errors for o in objects)
    ft_in = Filetype(
        filename=[FilePattern(pattern=re.compile(r"(?:/|^)[0-9]+\.fits"))],
        standard='FITS',
        objects=objects,
        validation_options=FiletypeValidationOptions(skip=[])
    )
    assert_no_errors(
        ft_in.errors,
        "invalid filetype reconstructed from description"
    )
    for p in paths:
        with fits.open(p) as hdul:
            errors = validation.fits.check_file(hdul, ft_in)
            assert_no_errors(
                errors,
                "HDUL does not conform to described schema"
            )
