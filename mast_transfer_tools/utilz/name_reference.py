import re

from functools import wraps

from typing import Any, Protocol

from mast_transfer_tools.types import TransferType, TransferEntity


class BucketNamer(Protocol):
    def __call__(self, s: str, /, *args: Any, **kwargs: Any) -> str: ...

def regularize_bucket_name(func: BucketNamer) -> BucketNamer:

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
    return f"{stem}-{dataset}-{delivery_id}-{transfer_type}"


@regularize_bucket_name
def control_bucket(
    stem: str,
    dataset: str,
    delivery_id: str,
    az_id: str,
) -> str:
    return f"{stem}-{dataset}-{delivery_id}-control--{az_id}--x-s3"


def validation_task(dataset: str, delivery_id: str) -> str:
    return f"{dataset}-{delivery_id}-validator"


def index_key(
    dataset: str, delivery_id: str, transfer_type: TransferType
) -> str:
    return f"{dataset}-{delivery_id}-{transfer_type}-index.csv"


def log_key(
    transfer_type: TransferType, writer: TransferEntity
) -> str:
    if writer == "lambda":
        return "log/lambda"
    elif writer in ("client", "validator"):
        return f"log/{writer}_{transfer_type}"
    raise ValueError(f"Unknown entity {writer}")


def label_key(dataset_name: str, delivery_id: str | int) -> str:
    return f"{dataset_name}-{delivery_id}-label.yaml"


def lock_key(writer: TransferEntity) -> str:
    return f"lock/{writer}"
