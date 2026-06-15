"""
Objects defining lock behavior.
"""
from pathlib import Path

import datetime as dt
import enum

from hostess.aws.s3 import Bucket
from mast_transfer_tools.types import TransferEntity
import mast_transfer_tools.utilz.name_reference as names


class LockStatus(enum.Enum):
    """
    Status of a lock object in relation to a particular entity.

    UNLOCKED: no lock exists
    STALE: lock exists but is old (can be safely overwritten)
    LOCKED: fresh lock exists and is not owned by the entity
    HELD: fresh lock exists and is owned by the entity
    INVALID: lock exists but cannot be decoded as text
    """
    UNLOCKED = enum.auto()
    STALE = enum.auto()
    LOCKED = enum.auto()
    HELD = enum.auto()
    INVALID = enum.auto()


def check_lock(
    bucket: Bucket,
    entity: TransferEntity,
    locker_id: str | None = None,
    staleness_threshold: int | None = None
) -> LockStatus:
    """
    Check the status of a client, validator, or lambda lock object. locker_id
    is the agent_id of the entity that might be expected to hold the lock
    (if the holder is important). See locks.LockStatus for a description of
    returned enum values.
    """
    lock_key = names.lock_key(entity)
    # directory bucket nonsense: can only make a LIST call to 'real' prefixes,
    # i.e. keys that end in "/
    lock_root = str(Path(lock_key).parent) + "/"
    results = bucket.ls(lock_root, formatting="contents")
    results = [r for r in results if r["Key"] == lock_key]
    if len(results) == 0:
        return LockStatus.UNLOCKED
    if (
        staleness_threshold is not None
        and dt.datetime.now().timestamp()
        - results[0]["LastModified"].timestamp()
        > staleness_threshold
    ):
        return LockStatus.STALE
        # don't read some massive accidentally-written file into memory
    if results[0]["Size"] > 2048:
        return LockStatus.INVALID
    try:
        lock_id = bucket.read(lock_key)
    except UnicodeDecodeError:
        return LockStatus.INVALID
    if lock_id != locker_id:
        return LockStatus.LOCKED
    return LockStatus.HELD
