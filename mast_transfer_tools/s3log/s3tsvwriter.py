from concurrent.futures import ThreadPoolExecutor
import csv
import threading
import time
from io import StringIO
from itertools import chain
from types import MappingProxyType as MPt
from typing import Sequence, Mapping

from hostess.aws.s3 import Bucket
from hostess.utilities import StoppableFuture

from mast_transfer_tools.s3log.helpers import (
    LogFieldRec, timestamp, yamldump_nested
)


csv.register_dialect(
    "fastlog",
    quotechar='"',
    escapechar="\\",
    delimiter="\t",
    lineterminator="\n"
)


class S3TSVWriter:
    """Manages tail-writes to TSV files stored as S3 Express objects."""
    def __init__(
        self,
        bucket: Bucket,
        key: str,
        fields: Sequence[LogFieldRec],
        fixed: Mapping[str, str] | None = None,
        safe: bool = True,
        add_timestamps: bool = True,
        buftime: float = 0.5,
        shared_lock: threading.Lock | None = None,
        buf_poll_rate: float = 0.08
    ):
        self.fields = tuple(f["name"] for f in fields)
        if add_timestamps is True and "time" not in self.fields:
            raise ValueError(
                "To add timestamps automatically, 'time' must be specified in "
                "fields"
            )
        required = frozenset({f["name"] for f in fields if f["required"]})
        fixed = MPt({}) if fixed is None else MPt(fixed)
        if not set(chain(required, fixed)).issubset(self.fields):
            raise ValueError(
                "If required or fixed fields are specified, they must be "
                "a subset of fields"
            )
        self.required, self.fixed = required, fixed
        self.bucket, self.key, self.safe = bucket, key, safe
        self.offset, self.last_entry_time = None, time.time()
        self.add_timestamps = add_timestamps
        self.buf = StringIO()
        self.writer = csv.writer(self.buf, dialect="fastlog")
        self.exc = ThreadPoolExecutor(1)
        self.lock = threading.Lock() if shared_lock is None else shared_lock
        self.buftime = buftime
        self.buf_poll_rate = buf_poll_rate
        self.write_future = StoppableFuture.launch_into(
            self.exc, self._object_write_loop
        )

    def stop(self):
        """
        Shut this object down. Wait up to 10 seconds to finish writes, then
        stop the write future. There is not a mechanism for restarting:
        construct a new writer.
        """
        start = time.time()
        while self.buf.tell() > 0:
            time.sleep(0.1)
            # NOTE: this is somewhat crude and it would perhaps be better to
            #  flush the buffer more elegantly
            if time.time() - start > 10:
                break
        self.write_future.stop()

    @property
    def stopped(self):
        return self.write_future.done()

    def _bufwait(self, _sigdict) -> bool:
        """
        Wait until the buffer is nonempty or we are signaled to stop. Returns
        True if the buffer is nonempty, False if we have been signaled to stop.
        """
        while self.buf.tell() == 0 or self.elapsed() < self.buftime:
            if _sigdict.get(0) is not None:
                return False
            time.sleep(self.buf_poll_rate)
        return True

    def _object_write_loop(self, _sigdict, _id):
        """
        Top-level loop for writing. Waits for text to appear in self.buf,
        append-writes it to the TSV object at self.key in self.bucket, then
        reinitializes self.buf. This must only run as self.write_future and
        should only be executed during object initialization.
        """
        while self._bufwait(_sigdict):
            with self.lock:
                self.buf.seek(0)
                self.bucket.append(self.buf.read(), self.key, literal_str=True)
                self.buf.close()
                self.buf = StringIO()
                self.writer = csv.writer(self.buf, dialect="fastlog")

    def _write_to_buffer(self, field_values) -> None:
        """Write a TSV row into this object's write buffer."""
        with self.lock:
            self.writer.writerow(
                [field_values.get(f, "") for f in self.fields]
            )

    def write(self, **field_values: str | dict) -> None:
        """Format and submit a write job."""
        if self.write_future.done():
            raise ValueError("Can't write to stopped writer.")
        self.last_entry_time = time.time()
        if self.add_timestamps:
            field_values["time"] = timestamp()
        if not set(field_values.keys()). issubset(self.fields):
            raise ValueError("field values must be a subset of known fields")
        if set(field_values).intersection(self.fixed) != set():
            raise ValueError(
                "Line fields must not intersect fixed field values"
            )
        field_values |= self.fixed
        if not self.required.issubset(field_values.keys()):
            missing = ", ".join(self.required.difference(field_values.keys()))
            raise ValueError(
                f"Write does not contain required fields: {missing}"
            )
        self._write_to_buffer(yamldump_nested(field_values))

    def elapsed(self) -> float:
        """How long has it been since we last saw a new entry in the log?"""
        return time.time() - self.last_entry_time
