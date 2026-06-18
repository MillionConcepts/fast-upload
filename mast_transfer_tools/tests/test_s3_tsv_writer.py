from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import csv
import time
from typing import Literal, Any

import pytest

from mast_transfer_tools.s3log.helpers import LogFieldRec
from mast_transfer_tools.s3log.s3tsvwriter import S3TSVWriter
from mast_transfer_tools.tests.mock_buckets import MockBucket


class MockAppendingBucket(MockBucket):
    """fake S3 bucket for testing S3TSVWriter's append-writes."""

    def __init__(self) -> None:
        self.objects = defaultdict(str)
        self.appends = []

    def append(
        self,
        text: str,
        key: str,
        literal_str: Literal[True] = True,  # noqa: FBT002
    ) -> None:
        assert literal_str is True
        self.appends.append((key, text))
        self.objects[key] += text


def wait_for_rows(
    bucket: MockAppendingBucket, key: str, n: int, timeout: float = 1
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = list(
            csv.reader(StringIO(bucket.objects[key]), dialect="fastlog")
        )
        if len(rows) >= n:
            return rows
        time.sleep(0.005)
    raise AssertionError(
        f"timed out waiting for {n} rows; got {bucket.objects[key]!r}"
    )


def test_eventually_appends_one_row() -> None:
    bucket = MockAppendingBucket()
    fields: list[LogFieldRec] = [
        {"name": "time", "required": False},
        {"name": "event", "required": True},
        {"name": "user", "required": False},
    ]

    w = S3TSVWriter(
        bucket,
        "log.tsv",
        fields=fields,
        buftime=0.01,
        buf_poll_rate=0.001,
        add_timestamps=False,
    )

    try:
        w.write(time="t0", event="started", user="x")
        rows = wait_for_rows(bucket, "log.tsv", 1)

        assert rows == [["t0", "started", "x"]]
    finally:
        w.stop()


def test_bursty_writes_are_batched() -> None:
    bucket = MockAppendingBucket()
    fields: list[LogFieldRec] = [
        {"name": "time", "required": False},
        {"name": "event", "required": True},
    ]

    w = S3TSVWriter(
        bucket,
        "log.tsv",
        fields=fields,
        buftime=0.05,
        buf_poll_rate=0.001,
        add_timestamps=False,
    )

    try:
        for i in range(5):
            w.write(time=str(i), event=f"event-{i}")

        rows = wait_for_rows(bucket, "log.tsv", 5)

        assert rows == [[str(i), f"event-{i}"] for i in range(5)]
        assert len(bucket.appends) == 1
    finally:
        w.stop()


def test_fixed_fields_are_added_and_protected() -> None:
    bucket = MockAppendingBucket()
    fields: list[LogFieldRec] = [
        {"name": "time", "required": False},
        {"name": "event", "required": True},
        {"name": "host", "required": True},
    ]

    w = S3TSVWriter(
        bucket,
        "log.tsv",
        fields=fields,
        fixed={"host": "machine-a"},
        buftime=0.01,
        buf_poll_rate=0.001,
        add_timestamps=False,
    )

    try:
        w.write(time="t0", event="started")
        rows = wait_for_rows(bucket, "log.tsv", 1)
        assert rows == [["t0", "started", "machine-a"]]

        with pytest.raises(ValueError, match="fixed"):
            w.write(time="t1", event="oops", host="machine-b")
    finally:
        w.stop()


def test_stop_drains_pending_buffer() -> None:
    bucket = MockAppendingBucket()
    fields: list[LogFieldRec] = [
        {"name": "time", "required": False},
        {"name": "event", "required": True},
    ]

    w = S3TSVWriter(
        bucket,
        "log.tsv",
        fields=fields,
        buftime=0.02,
        buf_poll_rate=0.001,
        add_timestamps=False,
    )

    w.write(time="t0", event="final")

    w.stop()

    rows = list(
        csv.reader(StringIO(bucket.objects["log.tsv"]), dialect="fastlog")
    )
    assert rows == [["t0", "final"]]


def test_concurrent_writes_are_all_present_once() -> None:
    bucket = MockAppendingBucket()
    fields: list[LogFieldRec] = [
        {"name": "time", "required": False},
        {"name": "event", "required": True},
        {"name": "seq", "required": True},
    ]

    w = S3TSVWriter(
        bucket,
        "log.tsv",
        fields=fields,
        buftime=0.01,
        buf_poll_rate=0.001,
        add_timestamps=False,
    )

    n = 100

    try:

        def submit(i: Any) -> None:
            w.write(time="t", event="hit", seq=str(i))

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(submit, range(n)))

        rows = wait_for_rows(bucket, "log.tsv", n, timeout=2)

        seqs = [row[2] for row in rows]
        assert sorted(seqs, key=int) == [str(i) for i in range(n)]
        assert len(seqs) == len(set(seqs))
    finally:
        w.stop()
