import random
import time


def with_retry(fn, *args, retries: int = 3, base_delay: float = 1.0, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on failure.

    Retries up to `retries` times. Raises the last exception if all attempts fail.
    Delay doubles each attempt with ±0.5s jitter to avoid thundering herd.
    """
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(delay)
