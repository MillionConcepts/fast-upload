"""
Functions defining shared names of various entities in the transfer system.
"""
from functools import wraps
import re
from typing import Any, Protocol

from mast_transfer_tools.types import TransferType, TransferEntity


class BucketNamer(Protocol):
    """Protocol for bucket naming"""
    def __call__(self, s: str, /, *args: Any, **kwargs: Any) -> str: ...


def regularize_bucket_name(func: BucketNamer) -> BucketNamer:
    """Regularize an S3 bucket name"""
    @wraps(func)
    def with_sanitization(s: str, /, *args: Any, **kwargs: Any) -> str:
        # obviously there are other possible cases, but this is the most
        # common one
        return re.sub("_", "-", func(s, *args, **kwargs))

    return with_sanitization


@regularize_bucket_name
def transfer_bucket(
    stem: str, dataset: str, delivery_id: str, transfer_type: TransferType
) -> str:
    """
    Args:
        stem: global bucket name stem
        dataset: dataset as specified in label
        delivery_id: delivery id as specified in label
        transfer_type: 'sample' or 'staging'

    Returns:
       Transfer bucket name.
    """
    return f"{stem}-{dataset}-{delivery_id}-{transfer_type}"


@regularize_bucket_name
def control_bucket(
    stem: str,
    dataset: str,
    delivery_id: str,
    az_id: str,
) -> str:
    """
    Args:
        stem: global bucket name stem
        dataset: dataset as specified in label
        delivery_id: delivery id as specified in label
        az_id: short AWS availability zone ID (e.g. 'use1-az4')

    Returns:
       Control bucket name.
    """
    return f"{stem}-{dataset}-{delivery_id}-control--{az_id}--x-s3"


def validation_task(dataset: str, delivery_id: str) -> str:
    """
    Args:
        dataset: dataset as specified in label
        delivery_id: delivery id as specified in label

    Returns:
       Validation task name.
   """
    return f"{dataset}-{delivery_id}-validator"


def index_key(
    dataset: str, delivery_id: str, transfer_type: TransferType
) -> str:
    """
    Args:
        dataset: dataset as specified in label
        delivery_id: delivery id as specified in label
        transfer_type: 'sample' or 'staging'

    Returns:
       Key of CSV index object.
   """
    return f"{dataset}-{delivery_id}-{transfer_type}-index.csv"


def log_key(transfer_type: TransferType, writer: TransferEntity) -> str:
    """
    Args:
        transfer_type: 'sample' or 'staging'
        writer: 'client' or 'validator'

    Returns:
       Key of TSV log object.
    """
    if writer == "lambda":
        raise ValueError("The upload init lambda does not write a log object")
    if writer in ("client", "validator"):
        return f"log/{writer}_{transfer_type}"
    raise ValueError(f"Unknown entity {writer}")


def label_key(dataset_name: str, delivery_id: str | int) -> str:
    """
    Args:
        dataset_name: dataset as specified in label
        delivery_id: delivery id as specified in label

    Returns:
       Key of YAML label.
    """
    return f"{dataset_name}-{delivery_id}-label.yaml"


def lock_key(writer: TransferEntity) -> str:
    """
    Args:
        writer: 'client', 'validator', or 'lambda'

    Returns:
       Key of lock object containing agent_id of current holder.
    """
    return f"lock/{writer}"
