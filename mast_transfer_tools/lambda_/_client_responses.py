from __future__ import annotations

from typing import Callable, Any

import yaml


def err_response(func: Callable) -> Callable:
    def dump_err_response(*args: Any, **kwargs: Any) -> str:
        step, details = func(*args, **kwargs)
        msg = {"status": "error", "step": step, "details": details}
        return yaml.dump(msg)

    return dump_err_response


@err_response
def llock_err_response(_ex: Exception) -> tuple[str, str]:
    return "lambda lock check", "duplicate function execution, terminating"


@err_response
def cbucket_err_response(_ex: Exception) -> tuple[str, str]:
    return "control bucket access", "unable to find/access control bucket"


@err_response
def conf_bucket_err_response(_ex: Exception) -> tuple[str, str]:
    return "config bucket access", "something wrong with config bucket"


@err_response
def task_run_err_response(_ex: Exception) -> tuple[str, str]:
    return "task launch", "task failed to launch"


@err_response
def task_setup_err_response(_ex: Exception) -> tuple[str, str]:
    return "task setup", "task setup failed"


@err_response
def iconfig_err_response(_ex: Exception) -> tuple[str, str]:
    return "task config read", "bad task config"


@err_response
def tlock_err_response(_ex: Exception) -> tuple[str, str]:
    return "lockfile check", "transfer app lockfile invalid or not present"


@err_response
def vtask_running_err_response() -> tuple[str, str]:
    return (
        "validation task check",
        "a validation task is already running for this transfer"
    )


@err_response
def noconfig_err_response() -> tuple[str, str]:
    return (
        "task config read",
        "Neither dataset-specific nor default task configuration "
        "found. This error cannot be addressed by the user. Please "
        "contact system administrators."
    )


@err_response
def lock_write_err_response() -> tuple[str, str]:
    return (
        "lambda lock file write",
        "lambda function could not write lock file. "
        "This error cannot be addressed by the user. "
        "Please contact system administrators."
    )


@err_response
def log_write_err_response() -> tuple[str, str]:
    return (
        "lambda log file write",
        "lambda function could not write log file. "
        "This error cannot be addressed by the user. "
        "Please contact system administrators."
    )


@err_response
def lambda_main_execution_error(_ex: Exception) -> tuple[str, str]:
    return "lambda execution", "unclassified lambda execution failure"


def pipeline_exec_success_msg() -> str:
    return yaml.dump({"status": "success"})
