"""
dev (at least) launch script for containerized version
of application. Expects kwargs passed from lambda (or lambda proxy) as compressed JSON in the environment variable
KWARGBLOB. Decodes them,
uses them to initialize the pipeline, starts the core pipeline loop,
waits for it to finish, exits. May also be responsible for
environment-specific cleanup or error reporting TBD.
"""
import atexit
import base64
import gzip
import json
import os
import time
import warnings
from typing import TypedDict

from dustgoggles.dynamic import exc_report
from urllib3.connectionpool import InsecureRequestWarning

from mast_transfer_tools.server.core import ValidationSession
from mast_transfer_tools.types import TransferType

# TODO: this is, hopefully, temporary. it is addressing the log spam from the
#  validator due to unverified SSL certs; we cannot verify the certs from ECS
#  due to STScI's current routing setup.
warnings.filterwarnings(category=InsecureRequestWarning, action="ignore")


class PipelineLaunchParameters(TypedDict):
    """
    Information the validation pipeline expects to receive from the
    pipeline launch lambda on startup in normal operation.
    """
    dataset: str
    delivery_id: str
    transfer_type: TransferType


def load_kwarg_blob(env_var="KWARGBLOB"):
    blob = os.environ.get(env_var)
    if blob is None:
        raise RuntimeError(
            f"Expected pipeline arguments defined in {env_var}, "
            f"none found"
        )
    try:
        decoded = gzip.decompress(base64.b64decode(blob))
        return json.loads(decoded)
    except Exception as e:
        raise RuntimeError(
            f"Could not load arguments from {env_var}: {type(e)}: {e}"
        )


def printexit():
    print("exiting pipeline handler")


def main():
    atexit.register(printexit)
    vs = None
    try:
        kwargs: PipelineLaunchParameters = load_kwarg_blob()
        print(f"Pipeline initialization kwargs: {kwargs}\n")
        vs = ValidationSession.from_launch_parameters(**kwargs)
        print(f"Initializing pipeline\n")
        vs.start()
        while vs.running:
            time.sleep(1)
    except Exception as e:
        print("encountered unhandled exception:\n")
        print(f"{str(exc_report(e)).replace('\n', ' ; ')}\n")
    if vs is None:
        print("validation session failed to initialize")
    elif vs.crashed:
        print("validation session crashed\n")
    print("initiating exit from pipeline handler\n")


if __name__ == "__main__":
    main()
