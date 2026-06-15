"""Error types used throughout FAST."""


# This is only used for locks on AWS buckets; "BucketLockedError" might
# be a better name.
class LockExistsError(PermissionError):
    """
    An S3 bucket is locked by another instance of FAST.
    """


# for similar reasons, "BucketLockStolenError" might be better here
class LockNotFoundError(PermissionError):
    """
    We expected to hold a lock on an S3 bucket but we don't.
    """


class InvalidLockError(PermissionError):
    """
    The lock files in an S3 bucket are malformed or not owned by
    the appropriate actors.
    """


class InvalidFileIndexError(ValueError):
    """index file is malformed"""


class InvalidLabelError(ValueError):
    """
    Something is wrong with a MAST dataset label.
    """


class LogFormatError(Exception):
    """
    The FAST client's record of work it has already done is corrupt.
    """
