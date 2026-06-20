from collections import deque
from io import StringIO
from typing import Sequence

from hostess.aws.s3 import Bucket
from hostess.utilities import StoppableFuture
import pandas as pd

from mast_transfer_tools.errors import LogFormatError
from mast_transfer_tools.s3log.helpers import LogFieldRec
from mast_transfer_tools.utilz.futures import is_crashed, is_running


class S3TSVReader:
    """Tails a TSV file stored as an S3 Express object."""
    def __init__(
        self,
        bucket: Bucket,
        key: str,
        fields: Sequence[LogFieldRec]
    ) -> None:
        self._logtail = deque()
        self.field_spec = tuple(fields)
        self.fields = [f["name"] for f in fields]
        self.required_fields = [
            f["name"] for f in self.field_spec if f["required"]
        ]
        self.last_log = pd.DataFrame([], columns=self.fields)
        self.log = pd.DataFrame([], columns=self.fields)
        self.tail_future: StoppableFuture | None = None
        self.bucket = bucket
        self.key = key

    @property
    def running(self) -> bool:
        """Does the reader appear to be running?"""
        return is_running(self.tail_future)

    @property
    def crashed(self) -> bool:
        """Does the reader appear to have crashed?"""
        return is_crashed(self.tail_future)

    def start(self, *, force: bool = False) -> None:
        """Start or restart the log reader."""
        if self.running:
            raise ValueError("Already running")
        if self.crashed is True and force is False:
            raise ValueError("Reader crashed. Pass 'force=True' to restart.")
        self.tail_future = self.bucket.tail(
            self.key, self._logtail, permit_missing=True
        )

    def stop(self) -> None:
        """
        Stops the log reader. Note that, unlike S3TSVWriter, there is no
        expectation that the log reader will drain the queue during stop:
        stop() is intended to just stop. This is because, in expected use,
        stop() should be called when subsequent reads from the log would have
        no effect on behavior; i.e., the consumer of the log information has
        already received a shutdown instruction, completed its work, entered
        an invalid state, etc.
        """
        if self.tail_future is not None:
            self.tail_future.stop()

    def _raise_bad_log_format(self, log: pd.DataFrame) -> None:
        """Raise a LogFormatError if a log chunk appears invalid."""
        if len(log.columns) != len(self.fields):
            raise LogFormatError(
                f"wrong number of columns: expected {len(self.fields)}, "
                f"got {len(log.columns)}"
            )

        log.columns = self.fields

        missing_required = [
            field
            for field in self.required_fields
            if log[field].isna().any() or (log[field].astype(str) == "").any()
        ]

        if missing_required:
            raise LogFormatError(
                f"missing required fields: {', '.join(missing_required)}"
            )

    def _logpop(self) -> str:
        """
        Pop all asynchronously-written chunks of text from `self._logtail`
        and return them concatenated. Returns `""` if there are no entries.

        Subroutine of update(). Don't call this directly or you may
        permanently lose log entries.
        """
        chunks = []
        while self._logtail:
            chunks.append(self._logtail.popleft())
        return "".join(chunks)

    def update(self) -> bool:
        """
        Check if any log entries have been retrieved asynchronously, and, if
        so, write them into `self.logbuf`, concatenate them to `self.log`,
        and assign them to `self.last_log`.

        Note: clears `self.logtail` on execution.

        Returns:
            True if there are any new log entries, False if not.
        """
        if len((text := self._logpop())) == 0:
            return False
        tab = pd.read_csv(
            StringIO(text),
            sep="\t",
            header=None,
            dtype=str,
            keep_default_na=False,
        )
        self._raise_bad_log_format(tab)
        tab.columns = self.fields
        self.log = pd.concat([self.log, tab]).reset_index(drop=True)
        self.last_log = tab
        return True
