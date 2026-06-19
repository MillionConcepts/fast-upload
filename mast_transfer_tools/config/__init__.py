"""Shared configuration module for the upload client, setup lambda, and
validation server. Some 'configuration' values are instead fetched from
Parameter Store or S3 objects, but this contains at least values necessary to
'bootstrap' those fetches.

It may at some point be a better idea to distribute multiple versions of this
a different way. Module currently contains values for the MAST dev deployment.
"""

import botocore.config

from mast_transfer_tools.types import CognitoConfiguration

LABEL_PREFIX = "labels/accepted"

MAX_TRANSFER_FAILURES = 10

NETWORK_CONFIG_PARAMETER = "/mast-fast/delivery"

RESOURCE_TAG_PARAMETER = "/mast-fast/resource-tags"

VAL_PIPE_SETTINGS = {
    "keepalive_threshold": 10,
    "n_val_threads": 3,
    "transfer_timeout": 480,
    "missing_timeout": 240,
    "loop_rate": 0.25,
}

COGCONFIG = CognitoConfiguration(
    domain="us-east-1ombs0ceea.auth.us-east-1.amazoncognito.com",
    client_id="4dhejsq62i6amu71r9lc3alhns",
    redirect_uri="http://localhost:3000",
    region="us-east-1",
    user_pool_id="us-east-1_oMbs0cEea",
    identity_pool_id="us-east-1:df0e1fac-bc76-4d8c-ae81-e4c03b9ec9b9",
)

LAMBDA_CLIENT_CONFIG = botocore.config.Config(
    retries={"total_max_attempts": 1, "mode": "standard"},
    read_timeout=300,
    connect_timeout=10,
)

VAL_PIPE_SQS_QUEUE_URL = "mast-fast-data-validation"
