import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import ENV_TESTING


@dataclass
class CacheValue:
    expires_at: datetime
    data: any
    is_refreshing: bool = False


class KeyCache:
    class NotFound(KeyError):
        pass

    def __init__(self, refresh_time=0):
        """
        Args:
            refresh_time: The number of seconds to wait before refreshing the cache.
        """
        self._cache = {}
        self.refresh_time = refresh_time

    def get(self, key):
        if key not in self._cache:
            raise self.NotFound(f"Cache key {key} not found.")

        expired = self._cache[key].expires_at < datetime.now() and not self._cache[key].is_refreshing

        return self._cache[key].data, expired

    def set(self, key, value):
        self._cache[key] = CacheValue(datetime.now() + timedelta(seconds=self.refresh_time), value)

    def set_refreshing(self, key):
        if key not in self._cache:
            raise self.NotFound(f"Cache key {key} not found.")

        self._cache[key].is_refreshing = True


class Cache:
    _NOT_SET = object()

    def __init__(self, func: callable, expiration_time=60):
        self._dont_run = os.environ.get("FLASK_ENV") == ENV_TESTING

        self._func = func
        if self._dont_run:
            return

        self._cache = func()
        self._expiration_time = expiration_time
        self._expires_at = datetime.now() + timedelta(seconds=self._expiration_time)
        self._updating = False

    def get(self):
        if self._updating:
            return self._cache

        if self._expires_at < datetime.now():
            if self._dont_run:
                return

            self._updating = True
            self._cache = self._func()
            self._expires_at = datetime.now() + timedelta(seconds=self._expiration_time)
            self._updating = False

        return self._cache
