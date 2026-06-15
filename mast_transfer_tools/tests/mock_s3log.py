"""
Minimal mocks of s3log objects for upload client & validator tests.
"""

from __future__ import annotations

import datetime as dt
import time
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


FieldSpec = Sequence[Mapping[str, Any] | str]


def _field_names(fields: FieldSpec) -> list[str]:
    """Extract field names from log field specs or plain strings."""
    names: list[str] = []
    for field in fields:
        if isinstance(field, str):
            names.append(field)
        else:
            names.append(str(field["name"]))
    return names


def _required_names(fields: FieldSpec) -> frozenset[str]:
    """Extract required field names from log field specs."""
    required: set[str] = set()
    for field in fields:
        if isinstance(field, str):
            continue
        if field.get("required", False):
            required.add(str(field["name"]))
    return frozenset(required)


def _timestamp() -> str:
    """Small local timestamp helper; precise format is not important here."""
    return dt.datetime.now(dt.UTC).isoformat()


class MockS3TSVWriter:
    """Synchronous, in-memory mock of ``S3TSVWriter``."""

    def __init__(
        self,
        bucket: Any,
        key: str,
        fields: FieldSpec,
        fixed: Mapping[str, str] | None = None,
        safe: bool = True,
        add_timestamps: bool = True,
        buftime: float = 0.5,
        shared_lock: Any = None,
        buf_poll_rate: float = 0.08,
    ):
        self.bucket = bucket
        self.key = key
        self.field_spec = tuple(fields)
        self.fields = tuple(_field_names(fields))
        self.required = _required_names(fields)
        self.fixed = {} if fixed is None else dict(fixed)
        self.safe = safe
        self.add_timestamps = add_timestamps
        self.buftime = buftime
        self.shared_lock = shared_lock
        self.buf_poll_rate = buf_poll_rate

        if self.add_timestamps and "time" not in self.fields:
            raise ValueError(
                "To add timestamps automatically, 'time' must be specified "
                "in fields"
            )
        if not set(self.fixed).issubset(self.fields):
            raise ValueError("fixed field values must be a subset of fields")
        if not self.required.issubset(self.fields):
            raise ValueError("required fields must be a subset of fields")

        self.rows: list[dict[str, Any]] = []
        self.write_calls: list[dict[str, Any]] = []
        self.stopped = False
        self.stop_calls = 0
        self.last_entry_time: float | None = None

    def write(self, **field_values: Any) -> None:
        """Record one log row, applying fixed fields and light validation."""
        if self.stopped:
            raise ValueError("Can't write to stopped writer.")

        values = dict(field_values)
        self.write_calls.append(dict(values))

        if self.add_timestamps:
            values.setdefault("time", _timestamp())
        if not set(values).issubset(self.fields):
            raise ValueError("field values must be a subset of known fields")
        if set(values).intersection(self.fixed):
            raise ValueError(
                "Line fields must not intersect fixed field values"
            )

        values |= self.fixed
        if not self.required.issubset(values):
            missing = ", ".join(sorted(self.required.difference(values)))
            raise ValueError(
                f"Write does not contain required fields: {missing}"
            )

        self.rows.append(
            {field: values.get(field, "") for field in self.fields}
        )
        self.last_entry_time = dt.datetime.now(dt.UTC).timestamp()

    def elapsed(self) -> float:
        if self.last_entry_time is None:
            return 0.0
        return dt.datetime.now(dt.UTC).timestamp() - self.last_entry_time

    def stop(self) -> None:
        """Mark the mock writer stopped."""
        self.stop_calls += 1
        self.stopped = True


class MockS3TSVReader:
    """Push-driven mock of ``S3TSVReader``."""

    def __init__(self, bucket: Any, key: str, fields: FieldSpec):
        self.bucket = bucket
        self.key = key
        self.field_spec = tuple(fields)
        self.fields = _field_names(fields)
        self.required_fields = list(_required_names(fields))
        self.last_log = pd.DataFrame([], columns=self.fields)
        self.log = pd.DataFrame([], columns=self.fields)

        self._pending: deque[pd.DataFrame] = deque()
        self._running = False
        self._crashed = False
        self.update_exception: BaseException | None = None
        self.start_calls = 0
        self.stop_calls = 0
        self.update_calls = 0

    @property
    def running(self) -> bool:
        """Whether the mock reader is running."""
        return self._running

    @property
    def crashed(self) -> bool:
        """Whether the mock reader has been marked crashed."""
        return self._crashed

    def start(self, *, force: bool = False) -> None:
        """Start the mock reader."""
        if self.running:
            raise ValueError("Already running")
        if self.crashed and not force:
            raise ValueError("Reader crashed. Pass 'force=True' to restart.")
        self.start_calls += 1
        self._running = True
        if force:
            self._crashed = False

    def stop(self) -> None:
        """Stop the mock reader."""
        self.stop_calls += 1
        self._running = False

    def crash(self, exception: BaseException | None = None) -> None:
        """Mark the reader crashed and optionally make future updates raise."""
        self._running = False
        self._crashed = True
        if exception is not None:
            self.update_exception = exception

    def push(
        self,
        rows: pd.DataFrame | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    ) -> None:
        """Queue a batch of parsed log rows for the next ``update()``.

        ``rows`` may be a DataFrame, one mapping, or a sequence of mappings.
        Missing known fields are filled with empty strings; unknown fields
        raise, because the real reader would not produce surprise columns.
        """
        if isinstance(rows, pd.DataFrame):
            frame = rows.copy()
        elif isinstance(rows, Mapping):
            frame = pd.DataFrame([dict(rows)])
        else:
            frame = pd.DataFrame([dict(row) for row in rows])

        unknown = set(frame.columns).difference(self.fields)
        if unknown:
            raise ValueError(
                "unknown log fields: " + ", ".join(sorted(map(str, unknown)))
            )
        for field in self.fields:
            if field not in frame.columns:
                frame[field] = ""
        self._pending.append(frame.loc[:, self.fields].astype(object))

    def update(self) -> bool:
        """Expose one queued batch of log rows, if any."""
        self.update_calls += 1
        if self.update_exception is not None:
            self._crashed = True
            raise self.update_exception
        if not self._pending:
            return False
        self.last_log = self._pending.popleft()
        self.log = pd.concat([self.log, self.last_log]).reset_index(drop=True)
        return True


__all__ = ["MockS3TSVReader", "MockS3TSVWriter"]
