import secrets
from collections.abc import Collection
from typing import Optional


def is_origin_allowed(origin: Optional[str], allowed_origins: Collection[str]) -> bool:
    """Allow non-browser clients without Origin and known browser origins."""
    return origin is None or origin in allowed_origins


def is_csrf_token_valid(
    cookie_token: Optional[str],
    header_token: Optional[str],
) -> bool:
    """Validate a double-submit CSRF token using constant-time comparison."""
    return bool(
        cookie_token
        and header_token
        and secrets.compare_digest(cookie_token, header_token)
    )
