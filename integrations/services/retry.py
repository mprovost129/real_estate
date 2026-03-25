import time


def backoff_delay_seconds(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    factor: float = 2.0,
    max_seconds: float = 30.0,
):
    """
    Exponential backoff delay for a given 1-based attempt number.
    attempt=1 -> base_seconds
    attempt=2 -> base_seconds * factor
    ...
    """
    if attempt < 1:
        attempt = 1
    delay = base_seconds * (factor ** (attempt - 1))
    return min(max_seconds, max(0.0, delay))


def sleep_with_backoff(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    factor: float = 2.0,
    max_seconds: float = 30.0,
):
    delay = backoff_delay_seconds(
        attempt,
        base_seconds=base_seconds,
        factor=factor,
        max_seconds=max_seconds,
    )
    if delay > 0:
        time.sleep(delay)
    return delay
