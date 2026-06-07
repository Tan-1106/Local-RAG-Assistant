import hashlib
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.config import settings
from app.db.redis_store import get_redis_client


_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(self, redis_client=None):
        self._redis = redis_client or get_redis_client()

    def enforce(self, scope: str, identity: str, policy: RateLimit) -> None:
        identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        window = int(time.time()) // policy.window_seconds
        key = f"rate:{scope}:{identity_hash}:{window}"
        current, ttl = self._redis.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            key,
            policy.window_seconds,
        )
        if int(current) > policy.limit:
            retry_after = max(int(ttl), 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if settings.TRUST_PROXY_HEADERS and forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def get_rate_limiter() -> RateLimiter:
    return RateLimiter()
