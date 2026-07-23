import csv
import json
import time
import functools
import logging
from typing import Callable, Any, Type, Sequence

logger = logging.getLogger("rpa_core")


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Sequence[Type[BaseException]] = (Exception,),
) -> Callable:
    """
    Decorator for retrying a function upon encountering specified exceptions.
    Implements exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"[Retry] Function '{func.__name__}' failed after {max_attempts} attempts. Error: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"[Retry] Function '{func.__name__}' failed (Attempt {attempt}/{max_attempts}). "
                        f"Retrying in {current_delay:.2f}s... Error: {e}"
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def load_csv(filepath: str, delimiter: str = ",", encoding: str = "utf-8-sig") -> list[dict[str, Any]]:
    """Load a CSV file and return rows as a list of dictionaries with cleaned keys."""
    with open(filepath, mode="r", encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        cleaned_rows = []
        for raw_row in reader:
            cleaned_row = {}
            for k, v in raw_row.items():
                if k is not None:
                    # Cleans headers (e.g. " invoice_num " becomes "invoice_num")
                    clean_key = k.strip('\ufeff\ufeef\r\n\t ')
                    # Cleans the values as well to prevent float() errors later
                    cleaned_row[clean_key] = v.strip() if isinstance(v, str) else v
            cleaned_rows.append(cleaned_row)
        return cleaned_rows


def save_csv(filepath: str, rows: list[dict[str, Any]], fieldnames: Sequence[str] | None = None, delimiter: str = ",", encoding: str = "utf-8") -> None:
    """Save a list of dictionaries to a CSV file."""
    if not rows and not fieldnames:
        return
    
    keys = fieldnames or list(rows[0].keys())
    with open(filepath, mode="w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=keys, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def load_json(filepath: str, encoding: str = "utf-8") -> Any:
    """Load and parse a JSON file."""
    with open(filepath, mode="r", encoding=encoding) as f:
        return json.load(f)


def save_json(filepath: str, data: Any, indent: int = 2, encoding: str = "utf-8") -> None:
    """Save a data structure as a formatted JSON file."""
    with open(filepath, mode="w", encoding=encoding) as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask a secret string showing only the last few characters."""
    if not secret:
        return ""
    if len(secret) <= visible_chars:
        return "*" * len(secret)
    return "*" * (len(secret) - visible_chars) + secret[-visible_chars:]
