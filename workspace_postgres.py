"""Small DB-API adapter for the existing parameterized workflow queries.

Schema is private and migrated out of band; financial writes are SERIALIZABLE.
Serialization conflicts are returned to the caller for an explicit idempotent retry.
"""
from contextlib import contextmanager
import sqlite3
import psycopg
from psycopg.rows import dict_row

SCHEMA_VERSION = '004_reports_notifications'


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        if query.strip().upper() == 'BEGIN IMMEDIATE':
            return Cursor(self.connection.execute('SELECT 1'))
        try:
            # A savepoint preserves SQLite's catch-and-continue behavior on duplicate inserts.
            with self.connection.transaction():
                portable = query.replace('? IS NULL', 'CAST(? AS TEXT) IS NULL')
                return Cursor(self.connection.execute(portable.replace('?', '%s'), params))
        except psycopg.IntegrityError as error:
            raise sqlite3.IntegrityError('Database constraint rejected this write') from error

    def executescript(self, _script):
        # Runtime must never create/alter tables or grant itself privileges.
        version = self.execute('SELECT version FROM schema_migrations WHERE version=?', (SCHEMA_VERSION,)).fetchone()
        if not version:
            raise RuntimeError('Enterprise database migration has not been applied')


class PostgresDatabase:
    def __init__(self, dsn):
        self.dsn = dsn

    @contextmanager
    def __call__(self):
        with psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row, prepare_threshold=None) as connection:
            connection.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
            with connection.transaction():
                connection.execute('SET LOCAL search_path TO enterprise, pg_catalog')
                connection.execute("SET LOCAL statement_timeout TO '10s'")
                connection.execute("SET LOCAL lock_timeout TO '3s'")
                yield Connection(connection)
