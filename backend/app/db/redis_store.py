import redis
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# Initialize a global connection pool
_redis_pool = None

def get_redis_client() -> redis.Redis:
    """
    Returns a configured Redis client instance using a connection pool.
    """
    global _redis_pool
    if _redis_pool is None:
        logger.info(f"Initializing Redis connection pool to {settings.REDIS_URL}")
        _redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
    
    return redis.Redis(connection_pool=_redis_pool)
