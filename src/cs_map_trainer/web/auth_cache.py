"""PostgreSQL-backed allauth counters and TOTP replay protection."""

import base64
import pickle
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.db import DatabaseCache
from django.db import connections, router
from django.utils import timezone


class SharedAuthenticationCache(DatabaseCache):
    """Keep live security entries; make add atomic even when replacing expired keys."""

    def get_many(self, keys, version=None):
        key_map = {self.make_and_validate_key(key, version=version): key for key in keys}
        if not key_map:
            return {}
        connection = connections[router.db_for_read(self.cache_model_class)]
        table = connection.ops.quote_name(self._table)
        placeholders = ", ".join(["%s"] * len(key_map))
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT cache_key, value FROM {table} "
                f"WHERE cache_key IN ({placeholders}) AND expires > %s",
                [*key_map, timezone.now()],
            )
            rows = cursor.fetchall()
        return {
            key_map[key]: pickle.loads(base64.b64decode(connection.ops.process_clob(value)))
            for key, value in rows
        }

    def _base_set(self, mode, key, value, timeout=DEFAULT_TIMEOUT):
        deadline = self.get_backend_timeout(timeout)
        expires = (
            datetime.max.replace(tzinfo=UTC if settings.USE_TZ else None)
            if deadline is None
            else datetime.fromtimestamp(deadline, tz=UTC if settings.USE_TZ else None)
        )
        connection = connections[router.db_for_write(self.cache_model_class)]
        table = connection.ops.quote_name(self._table)
        now = timezone.now()
        with connection.cursor() as cursor:
            # Never evict unexpired counters or replay markers under cache pressure.
            cursor.execute(
                f"WITH expired AS (SELECT cache_key FROM {table} WHERE expires <= %s "
                "ORDER BY cache_key LIMIT 100 FOR UPDATE SKIP LOCKED) "
                f"DELETE FROM {table} WHERE cache_key IN (SELECT cache_key FROM expired) "
                "AND expires <= %s",
                [now, now],
            )
            if mode == "touch":
                cursor.execute(
                    f"UPDATE {table} SET expires = %s "
                    "WHERE cache_key = %s AND expires > %s RETURNING cache_key",
                    [expires, key, now],
                )
            else:
                encoded = base64.b64encode(pickle.dumps(value, self.pickle_protocol)).decode(
                    "ascii"
                )
                condition = " WHERE existing.expires <= %s" if mode == "add" else ""
                params = [key, encoded, expires]
                if mode == "add":
                    params.append(now)
                cursor.execute(
                    f"INSERT INTO {table} AS existing (cache_key, value, expires) "
                    "VALUES (%s, %s, %s) ON CONFLICT (cache_key) DO UPDATE "
                    "SET value = EXCLUDED.value, expires = EXCLUDED.expires"
                    f"{condition} RETURNING cache_key",
                    params,
                )
            return cursor.fetchone() is not None
