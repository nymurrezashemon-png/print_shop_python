"""
db.py   (converted from db.php)

<?php
$host = "localhost";
$username = "root";
$password = "";
$database = "print_shop_db";
$conn = new mysqli($host, $username, $password, $database);
if ($conn->connect_error) { die("Connection Failed: " . $conn->connect_error); }

The classes below give PyMySQL the same interface the PHP code used from mysqli
($conn->query, ->prepare, ->bind_param, ->execute, ->get_result, ->store_result,
->num_rows, ->fetch_assoc, ->fetch_all, ->begin_transaction, ->commit, ->rollback,
->real_escape_string), so the converted logic can stay line-for-line identical.
"""
import datetime
from decimal import Decimal

import pymysql

from php_compat import php_str, intval, floatval

# ---- same credentials as db.php -------------------------------------------
host = "localhost"
username = "root"
password = ""
database = "print_shop_db"


class ConnectionFailed(Exception):
    """db.php:  die("Connection Failed: " . $conn->connect_error);"""


# ---------------------------------------------------------------- row typing
def _native(v):
    """Prepared-statement rows (mysqli binary protocol): ints stay int, DECIMAL -> str, dates -> str."""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time, datetime.timedelta)):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("utf-8", "replace")
    return v


def _text(v):
    """$conn->query() rows (mysqli text protocol): every non-NULL value is a string."""
    if v is None:
        return None
    v = _native(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    return v if isinstance(v, str) else php_str(v)


class Result:
    """mysqli_result"""

    def __init__(self, rows):
        self.rows = rows
        self.num_rows = len(rows)
        self._i = 0

    def fetch_assoc(self):
        if self._i >= len(self.rows):
            return None
        row = self.rows[self._i]
        self._i += 1
        return row

    def fetch_all(self):
        return list(self.rows)

    def __iter__(self):
        while True:
            r = self.fetch_assoc()
            if r is None:
                return
            yield r


class Stmt:
    """mysqli_stmt"""

    def __init__(self, conn, sql):
        self._conn = conn
        # mysqli uses ?  - PyMySQL uses %s
        self._sql = sql.replace("%", "%%").replace("?", "%s")
        self._params = ()
        self.num_rows = 0
        self._rows = []
        self.error = None

    def bind_param(self, types, *vars_):
        out = []
        for t, v in zip(types, vars_):
            if v is None:
                out.append(None)
            elif t == "i":
                out.append(intval(v))
            elif t == "d":
                out.append(floatval(v))
            else:
                out.append(php_str(v))
        self._params = tuple(out)
        return True

    def _run(self):
        with self._conn.cursor() as cur:
            cur.execute(self._sql, self._params)
            self._rows = [{k: _native(v) for k, v in r.items()} for r in cur.fetchall()] if cur.description else []
            self.num_rows = len(self._rows)

    def execute(self):
        """Returns True / False (like mysqli without exceptions)."""
        try:
            self._run()
            return True
        except pymysql.MySQLError as ex:
            self.error = ex
            return False

    def execute_or_raise(self):
        """Same as execute() but raises (used inside the original try { } catch (Throwable) blocks)."""
        self._run()
        return True

    def get_result(self):
        return Result(self._rows)

    def store_result(self):
        return True


class Db:
    """mysqli connection object"""

    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return self._raw.cursor(pymysql.cursors.DictCursor)

    def prepare(self, sql):
        return Stmt(self, sql)

    def query(self, sql):
        """Text-protocol query. SELECT -> Result, anything else -> True, error -> False."""
        try:
            with self.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    rows = [{k: _text(v) for k, v in r.items()} for r in cur.fetchall()]
                    return Result(rows)
                return True
        except pymysql.MySQLError:
            return False

    def real_escape_string(self, s):
        return self._raw.escape_string(s)

    def begin_transaction(self):
        self._raw.begin()

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


def connect():
    try:
        raw = pymysql.connect(host=host, user=username, password=password, database=database,
                              charset="utf8mb4", autocommit=True)
    except pymysql.MySQLError as ex:
        msg = ex.args[1] if len(ex.args) > 1 else str(ex)
        raise ConnectionFailed("Connection Failed: " + str(msg))
    return Db(raw)
