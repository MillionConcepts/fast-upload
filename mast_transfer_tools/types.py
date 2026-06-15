"""
Data types used throughout the mast-upload-tools which are not complicated
enough to need their own file.
"""

from typing import Literal, TypedDict, NotRequired

from pandas import DataFrame

from .labels import Label


YAMLString = str


"""alias for strings that can be parsed as valid YAML"""
TransferType = Literal["staging", "sample"]
TransferEntity = Literal["validator", "client", "lambda"]


class ConfigBucketSpec(TypedDict):
    bucket: str
    prefix: str


class LocationSpec(TypedDict):
    config: ConfigBucketSpec
    transfer_bucket_stem: str


class TaskConfig(TypedDict):
    az_id: str
    subnet_id: str
    # name of ecs cluster in which to run task
    cluster: str
    # security group in which to run task
    sg_id: str
    # ecs task family
    family: str
    # instance resource overrides
    cpu: str
    memory: str


class ValPipeSettings(TypedDict):
    transfer_timeout: float
    missing_timeout: float
    log_poll_rate: float
    loop_rate: float
    n_val_threads: int
    keepalive_threshold: float
    az_id: str
    staleness_threshold: NotRequired[int]


class ValIdent(TypedDict):
    cb_name: str
    tb_name: str
    sb_name: str | None
    dataset: str
    delivery_id: str
    transfer_type: TransferType
    agent_id: str
    label: Label
    index: DataFrame


class PipelineNetworkConfig(TypedDict):
    """
    AWS configuration settings necessary for executing various aspects of the
    pipeline but not for initial client auth. Components are expected to fetch
    them from Parameter Store.
    """
    AVAILABILITY_ZONE_ID: str
    BUCKET_STEM: str
    CONFIG_BUCKET: str
    INIT_LAMBDA_ARN: str
    LOCK_STALENESS_THRESHOLD: int
    TASK_CONFIG_PREFIX: str
