"""
php_compat.py
Small helpers that reproduce the exact behaviour of the PHP built-ins used in
the original Print Shop PHP project (trim, empty, intval, floatval,
number_format, round, htmlspecialchars, json_encode, uniqid, escapeshellarg ...).
Nothing here is project logic - it only exists so the converted code behaves
identically to the PHP code.
"""
import os
import re
import time
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------- strings
_PHP_TRIM_CHARS = " \t\n\r\0\x0b"


def trim(s):
    """PHP trim(): strips only  space \\t \\n \\r \\0 \\x0B  (null -> '')."""
    if s is None:
        return ""
    return php_str(s).strip(_PHP_TRIM_CHARS)


def strlen(s):
    """PHP strlen() counts BYTES, not characters."""
    return len(php_str(s).encode("utf-8"))


def strtolower(s):
    """PHP 8 strtolower(): ASCII-only lower-casing."""
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in php_str(s))


def ctype_digit(s):
    """PHP ctype_digit() for strings: non-empty and only ASCII 0-9."""
    return isinstance(s, str) and s != "" and all("0" <= c <= "9" for c in s)


def htmlspecialchars(s, *_ignored):
    """PHP 8.1+ default flags: ENT_QUOTES | ENT_SUBSTITUTE | ENT_HTML401."""
    s = php_str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#039;"))


h = htmlspecialchars  # admin_dashboard.php: h($v) = htmlspecialchars((string)$v, ENT_QUOTES, 'UTF-8')


def php_str(v):
    """How PHP converts a value to string for echo / string concatenation."""
    if v is None:
        return ""
    if v is True:
        return "1"
    if v is False:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return "NAN"
        if v in (float("inf"), float("-inf")):
            return "INF" if v > 0 else "-INF"
        s = "%.14G" % v           # PHP ini: precision = 14
        if "E" in s:
            mant, exp = s.split("E")
            sign = exp[0]
            digits = exp[1:].lstrip("0") or "0"
            if "." not in mant:
                mant += ".0"
            s = "%sE%s%s" % (mant, sign, digits)
        return s
    return str(v)


e = php_str  # alias used in templates:  echo $x;


# ---------------------------------------------------------------- numbers
_LEADING_NUM = re.compile(r"^[ \t\n\r\v\f]*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_FULL_NUM = re.compile(r"^[ \t\n\r\v\f]*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?[ \t\n\r\v\f]*$")
_INT_MAX = 9223372036854775807
_INT_MIN = -9223372036854775808


def is_numeric_str(s):
    return isinstance(s, str) and _FULL_NUM.match(s) is not None


def floatval(v):
    if v is None:
        return 0.0
    if isinstance(v, (bool, int, float, Decimal)):
        return float(v)
    if isinstance(v, str):
        m = _LEADING_NUM.match(v)
        return float(m.group(1)) if m else 0.0
    return 0.0


def intval(v):
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, (float, Decimal)):
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return 0
        return max(_INT_MIN, min(_INT_MAX, int(f)))
    if isinstance(v, str):
        m = _LEADING_NUM.match(v)
        if not m:
            return 0
        t = m.group(1)
        if re.fullmatch(r"[+-]?\d+", t):
            return max(_INT_MIN, min(_INT_MAX, int(t)))
        f = float(t)
        return max(_INT_MIN, min(_INT_MAX, int(f)))
    return 0


def to_number(v):
    """PHP 8 arithmetic operand conversion (used for  $a + $b  with DB strings)."""
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, str):
        m = _LEADING_NUM.match(v)
        if not m:
            raise TypeError("Unsupported operand types: string")   # PHP 8 TypeError
        t = m.group(1)
        if re.fullmatch(r"[+-]?\d+", t):
            return int(t)
        return float(t)
    raise TypeError("Unsupported operand types")


def gt_zero(v):
    """PHP 8 loose comparison  $v > 0  (v usually a raw $_POST string)."""
    if v is None:
        return False
    if isinstance(v, str):
        if is_numeric_str(v):
            return float(v) > 0
        return v > "0"            # non-numeric string: PHP 8 compares 0 as the string "0"
    return v > 0


def php_round(x, places=0):
    """PHP round(): half away from zero, with PHP's decimal pre-rounding. Returns float."""
    x = floatval(x) if not isinstance(x, (int, float)) else x
    if x != x or x in (float("inf"), float("-inf")):
        return float(x)
    q = Decimal(1).scaleb(-places)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def number_format(num, decimals=0, dec_point=".", thousands_sep=","):
    num = to_number(num) if not isinstance(num, (int, float)) else num
    decimals = max(0, int(decimals))
    d = Decimal(repr(float(num))) if isinstance(num, float) else Decimal(num)
    q = Decimal(1).scaleb(-decimals)
    r = d.quantize(q, rounding=ROUND_HALF_UP)
    neg = r < 0
    txt = format(abs(r), "f")
    if "." in txt:
        int_part, frac = txt.split(".")
    else:
        int_part, frac = txt, ""
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    out = thousands_sep.join(groups)
    if decimals > 0:
        out += dec_point + frac
    if neg and any(c not in "0.," for c in out):      # PHP 8: never "-0.00"
        out = "-" + out
    return out


def php_abs(v):
    n = to_number(v)
    return abs(n)


def php_max(*args):
    return max(args)


def php_count(x):
    return len(x)


def empty(v):
    """PHP empty()."""
    if v is None:
        return True
    if isinstance(v, str):
        return v in ("", "0")
    if isinstance(v, (list, tuple, dict)):
        return len(v) == 0
    if isinstance(v, (bool, int, float, Decimal)):
        return v == 0
    return False


def nc(container, key, default=None):
    """PHP null-coalescing  $container[key] ?? default  (works for dict / list)."""
    try:
        if isinstance(container, dict):
            v = container.get(key)
        elif isinstance(container, (list, tuple)):
            v = container[key]
        else:
            v = None
    except (IndexError, KeyError, TypeError):
        v = None
    return default if v is None else v


# ---------------------------------------------------------------- json_encode
JSON_HEX_TAG = 1
JSON_HEX_AMP = 2
JSON_HEX_APOS = 4
JSON_HEX_QUOT = 8


def _json_str(s, flags):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append("\\u0022" if flags & JSON_HEX_QUOT else '\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "/":
            out.append("\\/")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "<" and flags & JSON_HEX_TAG:
            out.append("\\u003C")
        elif ch == ">" and flags & JSON_HEX_TAG:
            out.append("\\u003E")
        elif ch == "&" and flags & JSON_HEX_AMP:
            out.append("\\u0026")
        elif ch == "'" and flags & JSON_HEX_APOS:
            out.append("\\u0027")
        elif o < 0x20:
            out.append("\\u%04x" % o)
        elif o > 0x7F:
            if o > 0xFFFF:
                o -= 0x10000
                out.append("\\u%04x\\u%04x" % (0xD800 | (o >> 10), 0xDC00 | (o & 0x3FF)))
            else:
                out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def json_encode(v, flags=0):
    """PHP json_encode() (default escaping of '/' and non-ASCII, compact output)."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)          # PHP 7.1+ serialize_precision=-1 -> shortest repr, e.g. 25.0
    if isinstance(v, Decimal):
        return _json_str(str(v), flags)
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str):
        return _json_str(v, flags)
    if isinstance(v, dict):
        if not v:
            return "[]"
        return "{" + ",".join(_json_str(str(k), flags) + ":" + json_encode(val, flags)
                              for k, val in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(json_encode(x, flags) for x in v) + "]"
    return _json_str(str(v), flags)


def json_encode_flags(v):
    """json_encode($payload, JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT|JSON_INVALID_UTF8_SUBSTITUTE)"""
    return json_encode(v, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT)


# ---------------------------------------------------------------- misc
def uniqid():
    """PHP uniqid() (13 hex chars: 8 for seconds, 5 for microseconds)."""
    t = time.time()
    sec = int(t)
    usec = int((t - sec) * 1000000)
    return "%08x%05x" % (sec, usec)


def escapeshellarg(s):
    s = php_str(s)
    if os.name == "nt":      # Windows (the original project runs on XAMPP / Windows)
        return '"' + s.replace('"', " ").replace("%", " ").replace("!", " ") + '"'
    return "'" + s.replace("'", "'\\''") + "'"


def client_basename(name):
    """PHP strips any directory part from $_FILES[..]['name'] (both / and \\)."""
    return re.split(r"[\\/]", name or "")[-1]


# password helpers used by admin_dashboard.php ---------------------------
def password_algo(p):
    """Equivalent of  password_get_info($p)['algo']  (None when not a PHP password hash)."""
    p = php_str(p)
    if len(p) == 60 and p[:4] == "$2y$":
        return "2y"
    if p.startswith("$argon2i$"):
        return "argon2i"
    if p.startswith("$argon2id$"):
        return "argon2id"
    return None
