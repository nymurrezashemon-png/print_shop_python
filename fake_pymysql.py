"""A tiny fake of PyMySQL used ONLY by the test-suite (the sandbox has no MySQL)."""
import datetime
import re
import sys
import types
from decimal import Decimal

LOG = []        # (sql, params)
RULES = []      # (compiled regex, rows | callable)
FAIL = []       # regexes that should raise MySQLError


class MySQLError(Exception):
    pass


def reset():
    LOG.clear()
    RULES.clear()
    FAIL.clear()


def when(pattern, rows):
    RULES.append((re.compile(pattern, re.S | re.I), rows))


class DictCursor:
    pass


class Cursor:
    def __init__(self):
        self.description = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        LOG.append((" ".join(sql.split()), params))
        for pat in FAIL:
            if re.search(pat, sql, re.S | re.I):
                raise MySQLError(1062, "Duplicate entry")
        for pat, rows in RULES:
            if pat.search(sql):
                r = rows(sql, params) if callable(rows) else rows
                self._rows = [dict(x) for x in r]
                self.description = [("c",)] if self._rows or sql.lstrip().upper().startswith(("SELECT", "SHOW")) else None
                return
        self._rows = []
        self.description = [("c",)] if sql.lstrip().upper().startswith(("SELECT", "SHOW")) else None

    def fetchall(self):
        return self._rows


class Conn:
    def cursor(self, cls=None):
        return Cursor()

    def escape_string(self, s):
        return s.replace("'", "\\'")

    def begin(self):
        LOG.append(("BEGIN", None))

    def commit(self):
        LOG.append(("COMMIT", None))

    def rollback(self):
        LOG.append(("ROLLBACK", None))

    def close(self):
        pass


def connect(**kw):
    return Conn()


def install():
    m = types.ModuleType("pymysql")
    m.MySQLError = MySQLError
    m.connect = connect
    m.cursors = types.SimpleNamespace(DictCursor=DictCursor)
    sys.modules["pymysql"] = m
    return m
