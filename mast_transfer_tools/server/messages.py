"""
Preformatted error messages for validation pipeline, intended for
writing to S3 log or stdout/cloudwatch
"""

from dustgoggles.dynamic import exc_report


def validation_error_msg(exc: Exception) -> dict[str, str | dict]:
    """Attempt to validate a file encountered an unhandled exception."""
    return {
        "status": "error", "message": exc_report(exc),
    }


def file_load_error_msg(exc: Exception) -> dict[str, str | dict]:
    """Attempt to load a file failed."""
    return {
        "status": "failure", "message": exc_report(exc),
    }


def validation_failure_message(failures: dict) -> dict[str, str | dict]:
    """File did not match definition in label."""
    return {
        "status": "failure", "message": failures
    }


def success_msg():
    """File existed and matched definition in label."""
    return {"status": "ok", "message": None}
