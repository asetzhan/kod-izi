"""Login attempt limiting (spec 14.1, "Кіру" row)."""

import hashlib

from redis import Redis


class LoginRateLimiter:
    def __init__(self, redis: Redis, max_attempts: int, window_seconds: int) -> None:
        self._redis = redis
        self._max = max_attempts
        self._window = window_seconds

    @staticmethod
    def _key(email: str, ip: str | None) -> str:
        digest = hashlib.sha256(f"{email}|{ip or '-'}".encode()).hexdigest()
        return f"login_fail:{digest}"

    def is_blocked(self, email: str, ip: str | None) -> bool:
        value = self._redis.get(self._key(email, ip))
        return value is not None and int(value) >= self._max

    def register_failure(self, email: str, ip: str | None) -> None:
        key = self._key(email, ip)
        if self._redis.incr(key) == 1:
            self._redis.expire(key, self._window)

    def reset(self, email: str, ip: str | None) -> None:
        self._redis.delete(self._key(email, ip))
