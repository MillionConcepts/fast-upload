from io import StringIO
import time

from typing import Literal, TypeAlias, Any

import dateutil.parser as dtp
import pandas as pd

from mast_transfer_tools.types import Label
from mast_transfer_tools.errors import LogFormatError
from mast_transfer_tools.s3log.s3tsvreader import S3TSVReader

ClientStatus = Literal[
    "unchecked",
    "restarting",
    "initializing",
    "working",
    "quit",
    "done",
    "crashed",
    "invalid",
    "shutting_down",
    "absent",
    "missing"
]

TERMINAL_CLIENT_STATES = ("quit", "done", "crashed", "missing")

FileState = Literal[
    "waiting",
    "validated",
    "queued",
    "invalid",
    "error",
    "missing",
]
"""
Codes for validation states of a file.

Meanings are:

* waiting: Not in bucket, client does not claim to have uploaded it
* validated: In bucket, passed validation
* queued: In bucket, pending validation
* invalid: In bucket, failed validation
* missing: Not in bucket, client claims to have uploaded it
"""

FileIndex: TypeAlias = pd.DataFrame
"""
Alias for a DataFrame created from a file index and a dataset label. It
has the following columns:

* path: path to file from bucket / tree root.
* filename: name of the file
* type: file type (if any) as inferred from filename, based on definitions
 in label
* state: general state of the file; legal values are the members of
  FileState.
* n_fail: number of failed upload attempts as reported by client
"""


class BadConditionError(ValueError):
    pass


class ValidationState:
    """
    The validation pipeline's model of the current state of the transfer.

    Attributes are described inline at the bottom of the class definition.

    Should typically only be used by `fast.validation.ValidationSession`.

    Design note:
        This class is primarily 'informational'. It doesn't need to be a
        bare namespace--parsing and munging methods are acceptable--
        but it should not sprout methods that execute pipeline tasks.
    """

    def __init__(
        self,
        index: FileIndex,
        label: Label,
        reader: S3TSVReader,
        transfer_timeout: float = 600,
        missing_timeout: float = 240,
        max_failures: int = 10,
    ) -> None:
        self.index = index
        self.label = label
        self.extra_files = []
        self.wrong_files = []
        self.transfer_timeout = transfer_timeout
        self.missing_timeout = missing_timeout
        self.max_failures = max_failures
        self.n_expected_files = len(index.loc[index['will_transfer']])
        self.n_completed = 0
        self.n_failures = 0
        self.last_time = time.time()
        self.reader = reader

    @property
    def done(self) -> bool:
        return self.n_expected_files == self.n_completed

    def _check_timeout(self) -> bool:
        """
        Update client_missing and client_absent by checking timeout thresholds.
        Do not call this directly unless you are certain that
        ValidationState.last_time is as up-to-date as it can be. Call
        ValidationState.check_timeout() instead.

        Returns True if the client is absent, False if not.
        """
        if self.client_on is False:
            # the client can't 'time out' if we know it's off
            return False
        elapsed = time.time() - self.last_time
        if elapsed > self.missing_timeout:
            self.client_status = "missing"
        elif elapsed > self.transfer_timeout:
            self.client_status = "absent"
        return self.client_status == "missing"

    def check_timeout(self) -> bool:
        if len(self.last_log) > 0:
            self.last_time = dtp.parse(
                self.last_log["time"].iloc[-1]
            ).timestamp()
        return self._check_timeout()

    def _check_shutdown(self) -> tuple[bool, bool]:
        """
        Returns:
            did_shut_down: does this group of entries indicate that the client
                quit / shut down / crashed?
            did_crash: does it indicate that it crashed?

            Note that these are also recorded in instance attributes, but
            it it is important to know _right when this has changed_.
        """
        shutrows = self.last_log.loc[self.last_log["category"] == "shutdown"]
        stoprows = self.last_log.loc[self.last_log["category"] == "stop"]
        if len(stoprows) > 1:
            raise LogFormatError("Too many stoprows")
        if (
            len(shutrows) > 0
            and shutrows["status"].isin(("error", "failure")).any()
        ):
            self.client_status = "crashed"
            return True, True
        elif len(stoprows) == 1:
            # "quit" means manually terminated the transfer, the client quit
            # on our request, etc. note that a _complete_ transfer does not
            # mean that _everything_ validated.
            self.client_status = "done" if self.transfer_complete else "quit"
            return True, False
        elif len(shutrows) > 0:
            self.client_status = "shutting_down"
            return True, False
        return False, False

    def _check_reported_transfers(self) -> tuple[bool, list[str]]:
        """
        Subroutine of update(). Don't call this directly.

        Returns:
            not_all_ok: True if there are any wrong or failed transfers,
                False if not.
            ok_transfers: list of keys that appear to represent permissible
                object transfers described in the most recent group of log
                entries
        """
        trows = self.last_log.loc[self.last_log["category"] == "transfer"]
        if len(trows) == 0:
            return False, []
        indexed_pred = trows["ref"].isin(self.index["path"])
        ok = True
        # why did you upload these? they're not in the index
        if len(wrong := trows.loc[~indexed_pred]) > 0:
            ok = False
            self.wrong_files += wrong["ref"].tolist()
            self.n_failures += len(wrong)
            indexed = trows.loc[indexed_pred]
        else:
            indexed = trows
        # these are failed uploads, most likely from network glitches --
        # we don't even expect to see them in the bucket
        failpred = indexed["status"].isin(("failure", "error"))
        keys = indexed.loc[~failpred, "ref"]
        if len(keys) < len(trows):
            ok = False
            failpaths = indexed.loc[failpred, "ref"]
            self.index.loc[self.index["path"].isin(failpaths), "n_fail"] += 1
            self.n_failures += len(failpaths)
        return not ok, keys.tolist()

    def update(self) -> tuple[bool, bool, bool, list[str]]:
        """
        Update our knowledge of the progress of the transfer by examining the
        client log and checking our timeout thresholds.

        Returns:
            any_updates: True if there are any messages other than keepalive
                entries; False if there aren't
            stopped_running: True if report or timeout indicates that client
                has stopped running for whatever reason (or is in the process
                of it), False if not
            any_problems: True if there are any error messages or
                impermissible transfers, False if there aren't
            valid_transfers: List of keys that appear to represent permissible
                transfers
        """
        try:
            are_new_messages = self.reader.update()
        except Exception as ex:
            self.client_status = "invalid"
            raise LogFormatError(str(ex))
        if not are_new_messages:
            self._check_timeout()
            return False, False, False, []
        self.client_missing, self.client_absent = False, False
        if self.client_status not in TERMINAL_CLIENT_STATES:
            self.client_status = "working"
        if (self.last_log["category"] == "keepalive").all():
            if self.client_status in ("quit", "crashed", "done"):
                raise BadConditionError(self.client_status)
            return False, False, False, []
        # a timeout _shouldn't_ happen here -- it would imply that _we_ have
        # been delayed in checking the log, or that poll rate and timeout
        # thresholds have been set to unreasonable values -- but we should
        # still check
        client_is_absent = self.check_timeout()
        if self.transfer_complete is True and self.last_log["category"].isin(
            ("transfer", "initialization", "start")
        ).any():
            raise BadConditionError(self.client_status)
        did_shut_down, did_crash = self._check_shutdown()
        # even if the client has quit / crashed, we want to validate
        # any objects it might have written before that happened
        transfers_not_ok, transfers = self._check_reported_transfers()
        stopped_running = client_is_absent + did_shut_down
        any_problems = did_crash + transfers_not_ok + client_is_absent
        return True, stopped_running, any_problems, transfers

    @property
    def client_on(self) -> bool | None:
        """
        True if we believe the client application is running, False if not,
        None if we don't think we know. This is directly derived from
        client_absent and client_status.
        """
        if self.client_status == "unchecked":
            return None
        return not (
            self.client_status in TERMINAL_CLIENT_STATES
            or self.client_absent
        )

    @property
    def should_continue(self) -> bool:
        return not (
            self.client_status in TERMINAL_CLIENT_STATES
            or self.n_failures > self.max_failures
            or self.transfer_complete
            or self.client_absent is True
        )

    @property
    def transfer_complete(self) -> bool:
        """Has the client completed its transfer (valid or not?)"""
        return self.n_completed >= self.n_expected_files

    def __getattr__(self, attr: str) -> Any:
        if attr in ("tail_future", "logtail", "logbuf", "last_log", "log"):
            return getattr(self.reader, attr)
        raise AttributeError(f"ValidationState has no attribute '{attr}'")

    def stop(self) -> None:
        self.reader.stop()

    client_status: ClientStatus = "unchecked"
    """
    Our belief about the general condition of the client application, as
    based strictly on what it has reported and not reported. Our timeouts are
    a backup for cases in which the client stops working but is unable to log
    this fact (e.g. logging bug, power outage, OS-level kill). This attribute,
    together with client_absent and session_invalid, tells us whether we
    should shut down the validation pipeline.
    """
    client_missing: bool = False
    """
    True if the client application didn't tell us it stopped, but it's
    stopped talking for longer than missing_timeout
    """
    client_absent: bool = False
    """
    True if the client application didn't tell us it stopped, but it's
    stopped talking for longer than transfer_timeout
    """
    session_invalid: bool = False
    """
    Have we encountered enough errors that we are going to ask the client to
    shut down, and refuse to validate any more files?
    """
    fileframe: FileIndex | None = None
    """parsed file index as produced by fast.validation.parse_index_file()"""
    extra_files: list[str]
    """
    Files not in index but in bucket, and client does not claim to have
    uploaded them during this session. This condition might indicate a prior
    erroneous upload or an incomplete index, and these should ideally be
    managed by the client.

    # TODO: 'ideally', pending risk-effort tradespace conversations with MAST.
    """
    wrong_files: list[str]
    """
    Files not in index that client claims to have uploaded (or tried to upload)
    during this session. (Something has gone wrong!)
    """
    reader: S3TSVReader
    """
    Object responsible for reading and parsing the client log.
    """

    # the following four attributes are implemented as references to the
    # corresponding attributes of `reader`
    log_tail: list[str]
    """Container for streaming chunks from the client log."""
    log: pd.DataFrame = None
    # TODO: we'll probably chunk this per-session
    """parsed log read so far, or empty dataframe if none yet read"""
    last_log: pd.DataFrame
    """last parsed log chunk, or empty dataframe if none yet read"""
    logbuf: StringIO
    """buffer of concatenated, unparsed text read from log"""
    transfer_timeout: float
    """
    How many seconds we will allow to elapse between messages from the client
    before deciding that they've quit without telling us, and shut ourselves
    down after completing any pending validation tasks.
    """
    missing_timeout: float
    """
    How many seconds we will allow to elapse between messages from the client
    before deciding something funny might be going on; we will log it and
    prepare cleanup tasks but not fully shut down until we hit
    transfer_timeout.
    """
    last_time: float
    """
    Timestamp (as UNIX epoch time) of last client message, or, if there
    aren't any yet, of this object's initialization.
    """
    n_completed: int = 0
    """
    Number of files that have completed transfer (not necessarily passed
    validation)
    """
    n_failures: int = 0
    """
    Number of files that have failed an upload attempt or failed to pass
    validation
    """
