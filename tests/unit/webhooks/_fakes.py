"""
_fakes.py — Hand-rolled minimal in-memory Redis double for webhook adapter tests.

Implements only the operations used by RedisWebhookReliabilityAdapter, with
the decode_responses=True flavour (strings in/out, not bytes). No new
dependency on fakeredis is introduced (per Step 4 prompt constraint).

Supported operations:
  set(name, value, nx=False, ex=None) -> True | None   (None = NX guard hit)
  hset(name, mapping)                  -> int (fields written)
  hgetall(name)                        -> dict[str, str]
  delete(*names)                       -> int
  zadd(name, mapping)                  -> int
  zrem(name, *members)                 -> int
  zrangebyscore(name, min, max, start=0, num=None) -> list[str]
  lpush(name, *values)                 -> int (new length)
  lrange(name, start, end)             -> list[str]
  exists(name)                         -> 0 | 1
  ttl(name)                            -> int seconds (-2 missing, -1 no-TTL)

Filename starts with "_" so pytest skips it during collection.
"""

from __future__ import annotations

from collections.abc import Callable
import time


class FakeRedis:
    """Minimal Redis double for webhook adapter unit tests."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._kv: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._lists: dict[str, list[str]] = {}
        self._ttls: dict[str, float] = {}  # absolute expiry epoch seconds
        self._clock = clock or time.time

    def _purge_if_expired(self, name: str) -> None:
        exp = self._ttls.get(name)
        if exp is not None and self._clock() >= exp:
            self._kv.pop(name, None)
            self._hashes.pop(name, None)
            self._zsets.pop(name, None)
            self._lists.pop(name, None)
            self._ttls.pop(name, None)

    def set(
        self,
        name: str,
        value: str,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        self._purge_if_expired(name)
        if nx and name in self._kv:
            return None
        self._kv[name] = str(value)
        if ex is not None:
            self._ttls[name] = self._clock() + ex
        return True

    def hset(self, name: str, mapping: dict) -> int:
        h = self._hashes.setdefault(name, {})
        for k, v in mapping.items():
            h[k] = str(v)
        return len(mapping)

    def hgetall(self, name: str) -> dict[str, str]:
        self._purge_if_expired(name)
        return dict(self._hashes.get(name, {}))

    def delete(self, *names: str) -> int:
        count = 0
        for n in names:
            removed = False
            if n in self._kv:
                del self._kv[n]
                removed = True
            if n in self._hashes:
                del self._hashes[n]
                removed = True
            if n in self._zsets:
                del self._zsets[n]
                removed = True
            if n in self._lists:
                del self._lists[n]
                removed = True
            self._ttls.pop(n, None)
            if removed:
                count += 1
        return count

    def zadd(self, name: str, mapping: dict) -> int:
        z = self._zsets.setdefault(name, {})
        for member, score in mapping.items():
            z[member] = float(score)
        return len(mapping)

    def zrem(self, name: str, *members: str) -> int:
        z = self._zsets.get(name)
        if not z:
            return 0
        cnt = 0
        for m in members:
            if m in z:
                del z[m]
                cnt += 1
        return cnt

    def zrangebyscore(
        self,
        name: str,
        min: float,
        max: float,
        start: int = 0,
        num: int | None = None,
    ) -> list[str]:
        z = self._zsets.get(name, {})
        items = sorted(
            ((score, member) for member, score in z.items() if min <= score <= max),
            key=lambda pair: (pair[0], pair[1]),
        )
        ordered = [member for _, member in items]
        if num is None:
            return ordered[start:]
        return ordered[start : start + num]

    def lpush(self, name: str, *values: str) -> int:
        lst = self._lists.setdefault(name, [])
        for v in values:
            lst.insert(0, str(v))
        return len(lst)

    def lrange(self, name: str, start: int, end: int) -> list[str]:
        lst = self._lists.get(name, [])
        if end == -1:
            return list(lst[start:])
        return list(lst[start : end + 1])

    def exists(self, name: str) -> int:
        self._purge_if_expired(name)
        return (
            1
            if (
                name in self._kv
                or name in self._hashes
                or name in self._zsets
                or name in self._lists
            )
            else 0
        )

    def ttl(self, name: str) -> int:
        self._purge_if_expired(name)
        exp = self._ttls.get(name)
        if exp is None:
            return -1 if name in self._kv else -2
        remaining = int(exp - self._clock())
        return max(0, remaining)
