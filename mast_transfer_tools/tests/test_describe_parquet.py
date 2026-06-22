import re
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml
from hypothesis import given, strategies as st

from mast_transfer_tools import labels, validation
from mast_transfer_tools.describe import describe_file
from mast_transfer_tools.describe.parquet import unify_descriptions
from mast_transfer_tools.labels import (
    DataObject,
    FilePattern,
    Filetype,
    FiletypeValidationOptions,
    ParquetDataObject,
)
from mast_transfer_tools.tests.test_validation_generic import assert_no_errors
from mast_transfer_tools.tests.test_validation_parquet import (
    st_arrow_table,
    st_parquet_filetype,
)


@st.composite
def st_filetype_with_tables(
    draw: st.DrawFn,
) -> tuple[labels.Filetype, list[pa.Table]]:
    ft = draw(st_parquet_filetype())
    tables = draw(st.lists(st_arrow_table(ft), min_size=1, max_size=3))
    return ft, tables


# This uses tmp_path_factory instead of tmp_path to work around
# Hypothesis's unfortunate semantics for function-scope fixtures, see
# https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.HealthCheck.function_scoped_fixture
@given(st_filetype_with_tables())
def test_random_parquet_description_roundtrip(
    tmp_path_factory: pytest.TempPathFactory,
    tcase: tuple[labels.Filetype, list[pa.Table]],
) -> None:
    ft_out, tables = tcase
    assert_no_errors(
        ft_out.errors, "test precondition failed: invalid filetype example"
    )
    tmp_path = tmp_path_factory.mktemp(
        "random-parquet-desc-roundtrip-", numbered=True
    )
    paths = []
    for i, table in enumerate(tables):
        path = tmp_path / f"{i}.parquet"
        paths.append(path)
        pq.write_table(table, path)
    descriptions = [describe_file(p) for p in paths]
    objdescs, failure = unify_descriptions(descriptions)
    assert failure is None, "description unification failed"
    if objdescs is None:
        objdescs = []
    # cast needed because list[ParquetDataObject] isn't assignment
    # compatible with list[DataObject] for tedious type theory reasons
    objects = cast(
        list[DataObject],
        [ParquetDataObject.from_text(yaml.dump(o)) for o in objdescs],
    )
    assert not any(o.errors for o in objects)
    ft_in = Filetype(
        filename=[
            FilePattern(pattern=re.compile(r"(?:/|^)[0-9]+\.parquet"))
        ],
        standard="parquet",
        objects=objects,
        validation_options=FiletypeValidationOptions(skip=[]),
    )
    assert_no_errors(
        ft_in.errors, "invalid filetype reconstructed from description"
    )
    for p in paths:
        pqfile = pq.ParquetFile(p)
        try:
            errors = validation.parquet.check_file(pqfile, ft_in)
        finally:
            pqfile.close()
        assert_no_errors(errors, "table does not conform to described schema")
