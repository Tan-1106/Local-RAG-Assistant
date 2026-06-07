import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from typing import Optional

from app.config import settings
from app.db.redis_store import get_redis_client


_ROTATE_REFRESH_SCRIPT = """
local session_id = redis.call('GET', KEYS[1])
if not session_id then
  return nil
end

local session_key = ARGV[1] .. session_id
local session_raw = redis.call('GET', session_key)
if not session_raw then
  redis.call('DEL', KEYS[1])
  return nil
end

local session_data = cjson.decode(session_raw)
if session_data['refresh_hash'] ~= ARGV[2] then
  return nil
end

session_data['refresh_hash'] = ARGV[3]
redis.call('DEL', KEYS[1])
redis.call('SET', KEYS[2], session_id, 'EX', ARGV[4])
redis.call('SET', session_key, cjson.encode(session_data), 'EX', ARGV[4])
redis.call('EXPIRE', ARGV[5] .. session_data['username'], ARGV[4])
return {session_id, session_data['username']}
"""


@dataclass(frozen=True)
class AuthSession:
    session_id: str
    username: str
    refresh_token: str


class AuthSessionService:
    """Redis-backed login sessions with refresh-token rotation."""

    def __init__(self, redis_client=None):
        self._redis = redis_client or get_redis_client()
        self._ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"auth:session:{session_id}"

    @staticmethod
    def _refresh_key(token_hash: str) -> str:
        return f"auth:refresh:{token_hash}"

    @staticmethod
    def _user_sessions_key(username: str) -> str:
        return f"auth:user-sessions:{username}"

    def create(self, username: str) -> AuthSession:
        session_id = uuid.uuid4().hex
        refresh_token = secrets.token_urlsafe(48)
        token_hash = self._hash_token(refresh_token)
        session_data = json.dumps({
            "username": username,
            "refresh_hash": token_hash,
        })

        with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(self._session_key(session_id), session_data, ex=self._ttl)
            pipe.set(self._refresh_key(token_hash), session_id, ex=self._ttl)
            pipe.sadd(self._user_sessions_key(username), session_id)
            pipe.expire(self._user_sessions_key(username), self._ttl)
            pipe.execute()

        return AuthSession(session_id, username, refresh_token)

    def exists(self, session_id: str) -> bool:
        return bool(self._redis.exists(self._session_key(session_id)))

    def rotate(self, refresh_token: str) -> Optional[AuthSession]:
        old_hash = self._hash_token(refresh_token)
        old_refresh_key = self._refresh_key(old_hash)
        new_token = secrets.token_urlsafe(48)
        new_hash = self._hash_token(new_token)
        result = self._redis.eval(
            _ROTATE_REFRESH_SCRIPT,
            2,
            old_refresh_key,
            self._refresh_key(new_hash),
            "auth:session:",
            old_hash,
            new_hash,
            self._ttl,
            "auth:user-sessions:",
        )
        if not result:
            return None
        session_id, username = result
        return AuthSession(session_id, username, new_token)

    def revoke(self, refresh_token: Optional[str] = None, session_id: Optional[str] = None) -> None:
        if refresh_token and not session_id:
            token_hash = self._hash_token(refresh_token)
            session_id = self._redis.get(self._refresh_key(token_hash))
        if not session_id:
            return

        session_key = self._session_key(session_id)
        session_raw = self._redis.get(session_key)
        if not session_raw:
            return

        session_data = json.loads(session_raw)
        refresh_hash = session_data.get("refresh_hash")
        username = session_data.get("username")

        with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(session_key)
            if refresh_hash:
                pipe.delete(self._refresh_key(refresh_hash))
            if username:
                pipe.srem(self._user_sessions_key(username), session_id)
            pipe.execute()

    def revoke_all(self, username: str) -> None:
        user_key = self._user_sessions_key(username)
        session_ids = self._redis.smembers(user_key)
        for session_id in session_ids:
            self.revoke(session_id=session_id)
        self._redis.delete(user_key)


def get_auth_session_service() -> AuthSessionService:
    return AuthSessionService()
