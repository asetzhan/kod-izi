"""Login attempt limiting (spec 14.1, "Кіру" row).

Attempts are counted before the password is checked, so parallel requests cannot all
slip past the limit. Two counters: per (email, ip) and per email from any address.
"""

import hashlib

from redis import Redis

# The per-account limit is looser, so an attacker cannot lock a user out from one address.
ACCOUNT_LIMIT_FACTOR = 4


class LoginRateLimiter:
    def __init__(self, redis: Redis, max_attempts: int, window_seconds: int) -> None:
        self._redis = redis
        self._max = max_attempts
        self._window = window_seconds

    @staticmethod
    def _key(kind: str, value: str) -> str:
        return f"login_attempts:{kind}:{hashlib.sha256(value.encode()).hexdigest()}"

    def _keys(self, email: str, ip: str | None) -> list[tuple[str, int]]:
        return [
            (self._key("pair", f"{email}|{ip or '-'}"), self._max),
            (self._key("account", email), self._max * ACCOUNT_LIMIT_FACTOR),
        ]

    def register_attempt(self, email: str, ip: str | None) -> bool:
        """Count one attempt; return False when a limit is exceeded."""
        allowed = True
        for key, limit in self._keys(email, ip):
            count = int(self._redis.incr(key))
            if count == 1:
                self._redis.expire(key, self._window)
            allowed = allowed and count <= limit
        return allowed

    def reset(self, email: str, ip: str | None) -> None:
        self._redis.delete(*(key for key, _ in self._keys(email, ip)))
