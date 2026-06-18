from typing import MutableSequence

import pandas as pd
import pytest

from mast_transfer_tools.errors import LogFormatError
from mast_transfer_tools.s3log.helpers import LogFieldRec, LOG_FIELD_SPEC
from mast_transfer_tools.s3log.s3tsvreader import S3TSVReader
from mast_transfer_tools.tests.mock_buckets import MockBucket


class FakeFuture:
    def __init__(self) -> None:
        self.stopped = False
        self.stop_calls = 0

    def stop(self) -> None:
        self.stopped = True
        self.stop_calls += 1


class MockTailingBucket(MockBucket):
    """Fake S3 bucket for testing S3TSVReader's tailing behavior."""

    def __init__(self) -> None:
        self.tail_args = None
        self.tail_queue = None
        self.future = FakeFuture()

    def tail(
        self, key: str, queue: MutableSequence, *, permit_missing: bool
    ) -> FakeFuture:
        self.tail_args = {
            "key": key,
            "permit_missing": permit_missing,
        }
        self.tail_queue = queue
        return self.future

    def push(self, text: str) -> None:
        self.tail_queue.append(text)


TEST_FIELDSPEC: list[LogFieldRec] = [
    {"name": "a", "required": True},
    {"name": "b", "required": True},
]


def test_update_without_new_text_does_nothing() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", TEST_FIELDSPEC)
    reader.start()

    before_log = reader.log.copy()
    before_last = reader.last_log.copy()

    assert reader.update() is False
    pd.testing.assert_frame_equal(reader.log, before_log)
    pd.testing.assert_frame_equal(reader.last_log, before_last)


def test_update_consumes_new_tsv_chunk() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", TEST_FIELDSPEC)
    reader.start()

    bucket.push("one\ttwo\nthree\tfour\n")

    assert reader.update() is True

    expected = pd.DataFrame(
        [["one", "two"], ["three", "four"]],
        columns=["a", "b"],
    )

    assert (reader.last_log == expected).all(axis=None)
    assert (reader.log == expected).all(axis=None)


def test_update_coalesces_multiple_chunks_available_at_once() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", TEST_FIELDSPEC)
    reader.start()

    bucket.push("one\ttwo\n")
    bucket.push("three\tfour\n")

    assert reader.update() is True

    expected = pd.DataFrame(
        [["one", "two"], ["three", "four"]],
        columns=["a", "b"],
    )

    assert (reader.last_log == expected).all(axis=None)
    assert (reader.log == expected).all(axis=None)


def test_update_accepts_single_write_containing_multiple_rows() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", TEST_FIELDSPEC)
    reader.start()

    bucket.push("one\ttwo\nthree\tfour\n")

    assert reader.update() is True

    expected = pd.DataFrame(
        [["one", "two"], ["three", "four"]],
        columns=["a", "b"],
    )

    assert (reader.last_log == expected).all(axis=None)
    assert (reader.log == expected).all(axis=None)


def test_too_few_columns_are_rejected() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", TEST_FIELDSPEC)
    reader.start()

    bucket.push("only_one_field\n")

    with pytest.raises(LogFormatError, match="wrong number of columns"):
        reader.update()


def test_too_many_columns_are_rejected() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", TEST_FIELDSPEC)
    reader.start()

    bucket.push("one\ttwo\tthree\n")

    with pytest.raises(LogFormatError, match="wrong number of columns"):
        reader.update()


def test_batch_with_one_bad_row_is_rejected() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(bucket, "x", LOG_FIELD_SPEC)
    reader.start()

    bucket.push(
        "2026-01-01T00:00:00Z\ttransfer\tabc\tok\tmessage\tagent-1\n"
        "2026-01-01T00:00:01Z\ttransfer\tdef\tok\tmessage\t\n"
    )

    with pytest.raises(LogFormatError, match="agent_id"):
        reader.update()


def test_stop_stops_future_without_draining_pending_log_text() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(
        bucket,
        "logs/foo.tsv",
        [
            {"name": "time", "required": True},
            {"name": "category", "required": True},
            {"name": "ref", "required": True},
            {"name": "status", "required": True},
            {"name": "message", "required": False},
            {"name": "agent_id", "required": True},
        ],
    )

    reader.start()

    bucket.push("2026-01-01T00:00:00Z\ttransfer\tabc\tok\tmessage\tagent-1\n")

    reader.stop()

    assert bucket.future.stop_calls == 1

    assert len(bucket.tail_queue) == 1
    assert reader.log.empty
    assert reader.last_log.empty


def test_stop_before_start_is_noop() -> None:
    bucket = MockTailingBucket()
    reader = S3TSVReader(
        bucket,
        "logs/foo.tsv",
        [{"name": "time", "required": True}],
    )

    reader.stop()

    assert reader.tail_future is None
