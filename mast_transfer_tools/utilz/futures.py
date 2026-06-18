"""shorthand for checking status of futurelike objects."""

import concurrent.futures
from typing import Any

from hostess.utilities import StoppableFuture


def is_running(
    future: concurrent.futures.Future[Any] | StoppableFuture | None,
) -> bool:
    return not (future is None or future.done() is True)


def is_crashed(
    future: concurrent.futures.Future[Any] | StoppableFuture | None,
) -> bool:
    if future is None or future.done() is False:
        return False
    try:
        future.result()
        return False
    except BaseException:
        return True
