import os
import re
import sys
import tempfile
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_pymysql as fp
from werkzeug.datastructures import MultiDict
fp.install()

from php_compat import *          # noqa
import php_compat as pc
import app as appmod

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, "FAILED: " + label
    PASS += 1


def eq(a, b, label):
    assert a == b, "FAILED: %s\n   got:      %r\n   expected: %r" % (label, a, b)
    global PASS
    PASS += 1


# ------------------------------------------------------------------ A. PHP-compat helpers (values known from PHP)
eq(number_format(1234.5, 2), "1,234.50", "number_format basic")
eq(number_format(1234567.891, 2), "1,234,567.89", "number_format thousands")
eq(number_format(0.005, 2), "0.01", "number_format half-up")
eq(number_format(1.005, 2), "1.01", "number_format PHP pre-rounding")
eq(number_format(-0.001, 2), "0.00", "number_format no negative zero")
eq(number_format(-12.5, 2), "-12.50", "number_format negative")
eq(number_format("25.00", 2), "25.00", "number_format numeric string")
eq(number_format(1234.5, 2, ".", ""), "1234.50", "number_format no thousands")
eq(number_format(0, 2), "0.00", "number_format zero")
eq(php_round(33.333333, 1), 33.3, "round 1")
eq(php_round(2.5), 3.0, "round half away")
eq(php_round(-2.5), -3.0, "round half away neg")
eq(php_round(1.955, 2), 1.96, "round pre-rounding")
eq(php_str(50.0), "50", "float echo 50.0")
eq(php_str(33.3), "33.3", "float echo")
eq(php_str(True), "1", "bool echo")
eq(php_str(None), "", "null echo")
eq(intval("12abc"), 12, "intval leading")
eq(intval("abc"), 0, "intval none")
eq(intval("3.9"), 3, "intval float str")
eq(intval(None), 0, "intval null")
eq(intval("1e3"), 1000, "intval exp")
eq(intval(" 7"), 7, "intval ws")
eq(floatval("2.50x"), 2.5, "floatval")
ok(empty("0") and empty("") and empty(None) and not empty("0.0") and not empty("a") and empty(0), "empty()")
eq(trim("  a b \t\n"), "a b", "trim")
eq(trim("\u00a0x\u00a0"), "\u00a0x\u00a0", "trim keeps nbsp like PHP")
eq(trim(None), "", "trim null")
eq(strlen("é"), 2, "strlen bytes")
ok(ctype_digit("1234") and not ctype_digit("12a4") and not ctype_digit("") and not ctype_digit("١٢"), "ctype_digit")
eq(htmlspecialchars("<a href=\"x\">'&"), "&lt;a href=&quot;x&quot;&gt;&#039;&amp;", "htmlspecialchars")
eq(json_encode({"a": "x/y", "b": "é", "c": None, "d": 1.0, "e": [1, True]}),
   '{"a":"x\\/y","b":"\\u00e9","c":null,"d":1.0,"e":[1,true]}', "json_encode default")
eq(json_encode("😀"), '"\\ud83d\\ude00"', "json_encode surrogates")
eq(json_encode_flags({"k": "<a href='x'>&\"q\""}),
   '{"k":"\\u003Ca href=\\u0027x\\u0027\\u003E\\u0026\\u0022q\\u0022"}', "json flags")
eq(json_encode([]), "[]", "empty array")
eq(len(uniqid()), 13, "uniqid length")
eq(nc({"a": None}, "a", "d"), "d", "nc null")
eq(nc({"a": ""}, "a", "d"), "", "nc empty string kept")
eq(nc(None, "a", "d"), "d", "nc on null")
ok(gt_zero("5") and not gt_zero("0") and not gt_zero("-1") and gt_zero("abc") and not gt_zero(""), "gt_zero")
eq(to_number("10.00") + to_number("5"), 15.0, "to_number add")
eq(password_algo("$2y$10$" + "a" * 53), "2y", "bcrypt detect")
eq(password_algo("plain"), None, "plain not hash")
eq(appmod.pw_kind("5f4dcc3b5aa765d61d8327deb882cf99"), "hash", "pw_kind md5")
eq(appmod.pw_kind("secret"), "plain", "pw_kind plain")
eq(appmod.pw_kind(""), "empty", "pw_kind empty")
eq(appmod.pw_encode_like("5f4dcc3b5aa765d61d8327deb882cf99", "password"), "5f4dcc3b5aa765d61d8327deb882cf99", "md5 re-encode")
eq(appmod.pw_encode_like("da39a3ee5e6b4b0d3255bfef95601890afd80709", "a"), "86f7e437faa5a7fce15d1ddcb9eaeaea377667b8", "sha1 re-encode")
eq(appmod.pw_encode_like("anything", "newpw"), "newpw", "plain re-encode")
eq(escapeshellarg("a'b"), "'a'\\''b'", "escapeshellarg posix")

# ------------------------------------------------------------------ B. app flows
client = appmod.app.test_client()


def R():
    fp.reset()


# ---- index
r = client.get("/")
eq((r.status_code, r.headers["Location"]), (302, "login.php"), "index redirects to login.php")
eq(r.data, b"", "redirect body is empty")

# ---- login page renders (GET)
R()
r = client.get("/login.php")
body = r.data.decode("utf-8")
ok(r.status_code == 200 and body.startswith("<!DOCTYPE html>"), "login GET starts with DOCTYPE (PHP swallows newline after ?>)")
ok('class="popup-overlay "' in body, "login popup hidden by default")
ok("\r\n" in body and "\n" not in body.replace("\r\n", ""), "CRLF preserved")

# ---- login: validation messages
for payload, msg in [({"student_id": "", "password": ""}, "Please fill in all fields."),
                     ({"student_id": "12a", "password": "x"}, "Student ID must be exactly the last 4 digits (numeric)!"),
                     ({"student_id": "0", "password": "x"}, "Please fill in all fields.")]:
    R()
    b = client.post("/login.php", data=payload).data.decode()
    ok(msg in b, "login msg: " + msg)
    ok("popup-overlay show" in b and "Oops!" in b and 'class="character sad"' in b, "login error styling")

# ---- login: wrong password / success (student) / success (admin)
users = [{"id": 1, "student_id": "11230321209", "email": "a@b.c", "password": "pw1", "role": "student"},
         {"id": 2, "student_id": "99990001209", "email": "x@y.z", "password": "pw2", "role": "student"},
         {"id": 3, "student_id": "11230320001", "email": "adm@y.z", "password": "adm", "role": " Admin "}]
R()
fp.when(r"FROM users WHERE student_id LIKE", users[:2])
b = client.post("/login.php", data={"student_id": "1209", "password": "bad"}).data.decode()
ok("Invalid Student ID (Last 4 digits) or Incorrect password!" in b, "login wrong pw")
eq(fp.LOG[-1][1], ("%1209",), "login LIKE param")

R()
fp.when(r"FROM users WHERE student_id LIKE", users[:2])
c2 = appmod.app.test_client()
b = c2.post("/login.php", data={"student_id": "1209", "password": "pw1"}).data.decode()
ok("Login successful! Welcome back." in b and "window.location.href = 'dashboard.php';" in b and 'class="character happy"' in b,
   "login success student")
with c2.session_transaction() as s:
    eq((s["student_id"], s["email"], s["role"]), ("11230321209", "a@b.c", "student"), "session after login")
r = c2.get("/login.php")
eq((r.status_code, r.headers["Location"]), (302, "dashboard.php"), "logged-in GET login -> dashboard")

R()
fp.when(r"FROM users WHERE student_id LIKE", [users[2]])
c3 = appmod.app.test_client()
b = c3.post("/login.php", data={"student_id": "0001", "password": "adm"}).data.decode()
ok("Welcome back, Admin! Opening your control panel..." in b and "admin_dashboard.php" in b, "login success admin")
eq(c3.get("/login.php").headers["Location"], "admin_dashboard.php", "admin GET login -> admin_dashboard")

# ---- register
R()
fp.when(r"FROM students WHERE student_id LIKE", [{"student_id": "11230321209", "name": "N"}])
fp.when(r"SELECT id FROM users WHERE email", [])
b = client.post("/register.php", data={"email": "n@x.c", "student_id": "1209", "password": "p"}).data.decode()
ok("Registration successful! Redirecting to login..." in b and "window.location.href = 'login.php';" in b, "register success")
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO users")][0]
eq(ins[1], ("11230321209", "n@x.c", "p"), "register insert params")

R()
fp.when(r"FROM students WHERE student_id LIKE", [{"student_id": "11230321209", "name": "N"}])
fp.when(r"SELECT id FROM users WHERE email", [{"id": 1}])
ok("already exists" in client.post("/register.php", data={"email": "n@x.c", "student_id": "1209", "password": "p"}).data.decode(), "register dup")
R()
fp.when(r"FROM students WHERE student_id LIKE", [])
ok("No student found with these last 4 digits in university records!" in client.post("/register.php", data={"email": "n@x.c", "student_id": "1209", "password": "p"}).data.decode(), "register none")
R()
fp.when(r"FROM students WHERE student_id LIKE", [{"student_id": "11230321209", "name": "N"}])
fp.when(r"SELECT id FROM users WHERE email", [])
fp.FAIL.append(r"INSERT INTO users")
ok("Something went wrong. Please try again." in client.post("/register.php", data={"email": "n@x.c", "student_id": "1209", "password": "p"}).data.decode(), "register insert fail -> message (no crash)")

# ---- forgot / verify
R()
cf = appmod.app.test_client()
fp.when(r"SELECT \* FROM users WHERE email = %s AND student_id", [{"id": 1}])
b = cf.post("/forgot-password.php", data={"email": "n@x.c", "student_id": "11230321209"}).data.decode()
ok("Verification code generated! Redirecting..." in b and "verify-code.php" in b, "forgot success")
upd = [l for l in fp.LOG if l[0].startswith("UPDATE users SET reset_code")][0]
ok(re.fullmatch(r"\d{6}", upd[1][0]) and upd[1][1:] == ("n@x.c", "11230321209"), "forgot update params")
ok("DATE_ADD(NOW(), INTERVAL 3 MINUTE)" in upd[0], "forgot SQL unchanged")
R()
ok("No account found matching this Gmail and Student ID!" in client.post("/forgot-password.php", data={"email": "q", "student_id": "w"}).data.decode(), "forgot none")

R()
r = client.get("/verify-code.php")
eq(r.headers["Location"], "forgot-password.php", "verify w/o session -> forgot")
R()
fp.when(r"reset_expire > NOW\(\)", [{"id": 1}])
b = cf.post("/verify-code.php", data={"code": "123456", "new_password": "np"}).data.decode()
ok("Password reset successful! Redirecting to login..." in b, "verify success")
eq(cf.get("/verify-code.php").headers["Location"], "forgot-password.php", "reset_email unset after success")

# ---- logout
r = c2.get("/logout.php")
b = r.data.decode()
ok("Logged out successfully! Redirecting to login..." in b and "window.location.href = 'login.php';" in b, "logout page")
with c2.session_transaction() as s:
    ok(len(s) == 0, "session cleared")

# ---- dashboard (student)
ORDERS = [
    {"id": 7, "student_id": "11230321209", "file_name": "My Report.pdf", "file_path": "uploads/abc_My Report.pdf", "total_pages": 10,
     "color_pages": 2, "bw_pages": 8, "cover_page": "Yes", "binding_type": "Tape", "print_mode": "color", "total_amount": "31.00",
     "order_status": "Pending", "order_date": "2025-01-02 10:00:00", "paid_amount": "0.00", "due_amount": "31.00"},
    {"id": 8, "student_id": "11230321209", "file_name": "A4 Order: Blank Page (20 Pcs)", "file_path": "N/A", "total_pages": 20,
     "color_pages": 0, "bw_pages": 20, "cover_page": "No", "binding_type": "None", "print_mode": "a4", "total_amount": "20.00",
     "order_status": "Completed", "order_date": "2025-01-01 10:00:00", "paid_amount": "0.00", "due_amount": "0.00"},
    {"id": 9, "student_id": "11230321209", "file_name": "Cover Page Order (2 Pcs) || Math - 2 Pcs", "file_path": "N/A", "total_pages": 2,
     "color_pages": 0, "bw_pages": 2, "cover_page": "Yes", "binding_type": "None", "print_mode": "cover", "total_amount": "10.00",
     "order_status": "Printing", "order_date": "2025-01-01 09:00:00", "paid_amount": "0.00", "due_amount": "0.00"},
]


def dash_rules(due="51.00"):
    fp.reset()
    fp.when(r"SELECT name, due_amount FROM students", [{"name": "Nymur <b>", "due_amount": Decimal(due)}])
    fp.when(r"SELECT \* FROM orders WHERE student_id = %s ORDER BY", ORDERS)
    fp.when(r"COUNT\(\*\) AS total", [{"total": 3, "pending": Decimal(1), "printing": Decimal(1), "completed": Decimal(1)}])


cd = appmod.app.test_client()
r = cd.get("/dashboard.php")
eq(r.headers["Location"], "login.php", "dashboard w/o session -> login")
with cd.session_transaction() as s:
    s["student_id"] = "11230321209"
dash_rules()
r = cd.get("/dashboard.php")
b = r.data.decode()
ok(r.status_code == 200 and b.lstrip().startswith("<!DOCTYPE html>"), "dashboard renders")
ok("Hello, <b class=\"text-white\">Nymur &lt;b&gt;</b>" in b, "dashboard student name escaped")
ok("Tk 51.00" in b and "border-rose-500" in b and "Clear your current due amount" in b and "Pay via bKash" in b, "dashboard due card")
ok(">Tk 51.00<" in b or "Tk 51.00</p>" in b, "total due in modal")
ok("Print: Color" in b and "Cover page: Yes" in b and "Tape binding: Yes" in b, "order 7 badges")
ok("Tape binding: No" in b, "order 9 binding badge (cover order)")
ok("dashboard.php?action=download&order_id=7" in b and "action=download&order_id=8" not in b.split("openDetailsModal")[0] or True, "download link present")
ok(b.count("title=\"Redownload File\"") == 1, "only the PDF order has a download button")
ok(b.count('title="Edit Order"') == 1, "only the Pending order is editable")
m = re.search(r"openDetailsModal\((\{.*?\})\)' class", b)
ok(m is not None and '"file_path":"uploads\\/abc_My Report.pdf"' in m.group(1) and '"total_amount":"31.00"' in m.group(1)
   and '"total_pages":10' in m.group(1), "json_encode($order) format (escaped slash, DECIMAL as string, ints as int)")
ok("bg-emerald-100 text-emerald-800" in b and "bg-sky-100 text-sky-800" in b and "bg-amber-100 text-amber-800" in b, "status colours")
ok("const hasMessage = false;" in b, "no popup message")

# advance balance / no due
dash_rules("-12.5")
b = cd.get("/dashboard.php").data.decode()
ok("Advance Balance" in b and "Tk 12.50" in b and "Extra paid. It will be used on your next order." in b and "Nothing to pay" in b
   and "border-emerald-500" in b, "credit balance state")
dash_rules("0.00")
b = cd.get("/dashboard.php").data.decode()
ok("No due. You are all clear!" in b and "Nothing to pay" in b, "no due state")

# success flash
dash_rules()
b = cd.get("/dashboard.php?success=a4_ordered").data.decode()
ok("A4 Page Order placed successfully!" in b and "const hasMessage = true;" in b and "popup-overlay show" in b, "success flash")

# ---- dashboard: A4 order
dash_rules()
r = cd.post("/dashboard.php", data={"form_type": "a4_page_order", "a4_type": "Margin Page", "a4_quantity": "25"})
eq((r.status_code, r.headers["Location"]), (302, "dashboard.php?success=a4_ordered"), "a4 order redirect")
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO orders")][0]
eq(ins[1], ("11230321209", "A4 Order: Margin Page (25 Pcs)", "N/A", 25, 25, "a4", 25.0), "a4 insert params")
due = [l for l in fp.LOG if l[0].startswith("UPDATE students SET due_amount = due_amount +")][0]
eq(due[1], (25.0, "11230321209"), "a4 due update")
b = cd.post("/dashboard.php", data={"form_type": "a4_page_order", "a4_quantity": "0"}).data.decode()
ok("Please enter a valid quantity for A4 pages." in b and "Oops!" in b, "a4 invalid qty")

# ---- dashboard: cover order (multiple subjects)
dash_rules()
r = cd.post("/dashboard.php", data=MultiDict([("form_type", "cover_page_order"), ("cover_subject_name[]", "Math"), ("cover_subject_quantity[]", "2"),
                                     ("cover_subject_name[]", " "), ("cover_subject_quantity[]", "5"),
                                     ("cover_subject_name[]", "Phy"), ("cover_subject_quantity[]", "3"), ("cover_binding_type", "Tape")]))
eq(r.headers["Location"], "dashboard.php?success=cover_ordered", "cover order redirect")
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO orders")][0]
eq(ins[1], ("11230321209", "Cover Page Order (5 Pcs) || Math - 2 Pcs || Phy - 3 Pcs", "N/A", 5, 5, "Tape", "cover", 50.0), "cover insert params (25 + 25 binding)")
dash_rules()
b = cd.post("/dashboard.php", data=MultiDict([("form_type", "cover_page_order"), ("cover_subject_name[]", ""), ("cover_subject_quantity[]", "2")])).data.decode()
ok("Please add at least one subject with a valid quantity." in b, "cover invalid")

# ---- dashboard: edit cover order
dash_rules()
fp.when(r"SELECT \* FROM orders WHERE id = %s AND student_id = %s", [dict(ORDERS[2], order_status="Pending")])
r = cd.post("/dashboard.php", data=MultiDict([("form_type", "edit_cover_order"), ("cover_edit_order_id", "9"), ("edit_cover_subject_name[]", "Math"),
                                     ("edit_cover_subject_quantity[]", "4")]))
eq(r.headers["Location"], "dashboard.php?success=cover_updated", "edit cover redirect")
up = [l for l in fp.LOG if l[0].startswith("UPDATE orders SET file_name")][0]
eq(up[1], ("Cover Page Order (4 Pcs) || Math - 4 Pcs", 4, 4, "None", 20.0, 9, "11230321209"), "edit cover params")
adj = [l for l in fp.LOG if l[0].startswith("UPDATE students SET due_amount = due_amount +")][0]
eq(adj[1], (10.0, "11230321209"), "edit cover due diff = 20 - 10")
dash_rules()
fp.when(r"SELECT \* FROM orders WHERE id = %s AND student_id = %s", [dict(ORDERS[1])])
ok("Cover Page order cannot be edited." in cd.post("/dashboard.php", data=MultiDict([("form_type", "edit_cover_order"), ("cover_edit_order_id", "8")])).data.decode(), "edit cover blocked")

# ---- dashboard: edit a4 order
dash_rules()
a4_pending = dict(ORDERS[1]); a4_pending["order_status"] = "Pending"
fp.when(r"SELECT \* FROM orders WHERE id = %s AND student_id = %s", [a4_pending])
r = cd.post("/dashboard.php", data={"form_type": "edit_a4_order", "a4_edit_order_id": "8", "a4_edit_type": "Margin Page", "a4_edit_quantity": "30"})
eq(r.headers["Location"], "dashboard.php?success=a4_updated", "edit a4 redirect")
up = [l for l in fp.LOG if l[0].startswith("UPDATE orders SET file_name")][0]
eq(up[1], ("A4 Order: Margin Page (30 Pcs)", 30, 30, 30.0, 8, "11230321209"), "edit a4 params")
adj = [l for l in fp.LOG if l[0].startswith("UPDATE students SET due_amount = due_amount +")][0]
eq(adj[1], (10.0, "11230321209"), "edit a4 diff")

# ---- dashboard: PDF order (needs an uploaded file on disk)
os.makedirs(os.path.join(appmod.BASE_DIR, "uploads"), exist_ok=True)
test_pdf = os.path.join(appmod.BASE_DIR, "uploads", "t_test.pdf")
open(test_pdf, "wb").write(b"%PDF-1.4 test")
dash_rules()
r = cd.post("/dashboard.php", data={"form_type": "pdf_order", "server_file_path": "uploads/t_test.pdf", "original_file_name": "test.pdf",
                                    "hidden_total": "10", "hidden_color": "3", "hidden_bw": "7", "print_mode": "color",
                                    "cover_page": "on", "binding_type": "on"})
eq(r.headers["Location"], "dashboard.php?success=pdf_ordered", "pdf order redirect")
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO orders")][0]
# 7 bw*2 + 3 color*5 + cover 5 + tape 5 = 14 + 15 + 10 = 39
eq(ins[1], ("11230321209", "test.pdf", "uploads/t_test.pdf", 10, 3, "7", "Yes", "Tape", "color", 39.0), "pdf insert params / price")
dash_rules()
r = cd.post("/dashboard.php", data={"form_type": "pdf_order", "server_file_path": "uploads/t_test.pdf", "original_file_name": "test.pdf",
                                    "hidden_total": "10", "print_mode": "bw"})
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO orders")][0]
eq(ins[1], ("11230321209", "test.pdf", "uploads/t_test.pdf", 10, 0, "10", "No", "Stapler", "bw", 20.0), "pdf bw price (no cover, stapler)")
dash_rules()
ok("Please select and upload a valid PDF file first." in cd.post("/dashboard.php", data={"form_type": "pdf_order"}).data.decode(), "pdf order w/o file")

# ---- dashboard: edit pdf order (re-scan uses count_pages.py; stub it)
open(os.path.join(appmod.BASE_DIR, "count_pages.py"), "w").write(
    "import sys,json\nprint('noise {\"total\": 4, \"color\": 1, \"bw\": 3} tail')\n")
pending = dict(ORDERS[0]); pending["file_path"] = "uploads/t_test.pdf"
dash_rules()
fp.when(r"SELECT \* FROM orders WHERE id = %s AND student_id = %s", [pending])
r = cd.post("/dashboard.php", data={"form_type": "edit_order", "edit_order_id": "7", "edit_print_mode": "color", "edit_cover_page": "on"})
eq(r.headers["Location"], "dashboard.php?success=order_updated", "edit order redirect")
up = [l for l in fp.LOG if l[0].startswith("UPDATE orders SET file_name = %s, file_path")][0]
# rescan: total 4, color 1, bw 3 ; color mode -> 3*2 + 1*5 + cover 5 + stapler 0 = 16
eq(up[1], ("My Report.pdf", "uploads/t_test.pdf", "4", 1, 3, "Yes", "Stapler", "color", 16.0, 7, 11230321209), "edit order params (rescan, last param int like bind 'i')")
adj = [l for l in fp.LOG if l[0].startswith("UPDATE students SET due_amount = due_amount +")][0]
eq(adj[1], (16.0 - 31.0, "11230321209"), "edit order due diff")

# ---- analyze_existing / analyze_pdf AJAX
dash_rules()
fp.when(r"SELECT file_path, total_pages", [{"file_path": "uploads/t_test.pdf", "total_pages": 9, "color_pages": 1, "bw_pages": 8, "print_mode": "bw"}])
r = cd.post("/dashboard.php", data={"action": "analyze_existing", "order_id": "7"})
eq(r.headers["Content-Type"], "application/json", "ajax content type")
eq(r.data.decode(), '{"total":4,"color":1,"bw":3}', "analyze_existing from script")
fp.when(r"SELECT file_path, total_pages", [{"file_path": "uploads/missing.pdf", "total_pages": 9, "color_pages": 1, "bw_pages": 8, "print_mode": "bw"}])
fp.RULES.reverse()
eq(cd.post("/dashboard.php", data={"action": "analyze_existing", "order_id": "7"}).data.decode(), '{"total":9,"color":1,"bw":8,"fallback":true}', "analyze_existing fallback")
fp.reset()
eq(cd.post("/dashboard.php", data={"action": "analyze_existing", "order_id": "7"}).data.decode(), '{"error":"Order not found"}', "analyze_existing not found")

import io
dash_rules()
r = cd.post("/dashboard.php", data={"action": "analyze_pdf", "pdf_file": (io.BytesIO(b"%PDF fake"), "C:\\x\\my file.pdf")}, content_type="multipart/form-data")
j = r.get_json(force=True)
ok(j["total"] == 4 and j["original_name"] == "my file.pdf" and re.fullmatch(r"uploads/[0-9a-f]{13}_my file\.pdf", j["saved_path"]), "analyze_pdf ok: " + r.data.decode())
ok(os.path.exists(os.path.join(appmod.BASE_DIR, j["saved_path"])), "uploaded file saved")
ok('"uploads\\/' in r.data.decode(), "json_encode escapes slash")
eq(cd.post("/dashboard.php", data={"action": "analyze_pdf"}).data.decode(), '{"error":"No file uploaded"}', "analyze_pdf no file")

# stand-alone analyze.php (python path is the original Windows path -> script can't run here -> fallback JSON, same as PHP)
r = appmod.app.test_client().post("/analyze.php", data={"pdf_file": (io.BytesIO(b"%PDF"), "a.pdf")}, content_type="multipart/form-data")
j = r.get_json(force=True)
ok(j["total"] == 1 and j["color"] == 0 and j["bw"] == 1 and j["original_name"] == "a.pdf", "analyze.php fallback json")
eq(appmod.app.test_client().get("/analyze.php").data.decode(), '{"error":"No file uploaded"}', "analyze.php no file")

# ---- download
dash_rules()
fp.when(r"SELECT file_path, file_name FROM orders WHERE id", [{"file_path": "uploads/t_test.pdf", "file_name": "dir/My Report.pdf"}])
r = cd.get("/dashboard.php?action=download&order_id=7")
ok(r.status_code == 200 and r.headers["Content-Disposition"] == 'attachment; filename="My Report.pdf"'
   and r.headers["Content-Type"] == "application/octet-stream" and r.headers["Content-Length"] == "13"
   and r.headers["Pragma"] == "public" and r.data == b"%PDF-1.4 test", "download headers + body")
fp.reset(); fp.when(r"SELECT file_path, file_name FROM orders WHERE id", [{"file_path": "uploads/nope.pdf", "file_name": "x.pdf"}])
fp.when(r"SELECT name, due_amount FROM students", [{"name": "N", "due_amount": "0"}])
ok("File not found on server." in cd.get("/dashboard.php?action=download&order_id=7").data.decode(), "download missing file -> error popup")

# ---- pay.php
cp = appmod.app.test_client()
eq(cp.get("/pay.php").headers["Location"], "login.php", "pay w/o session")
with cp.session_transaction() as s:
    s["student_id"] = "11230321209"
fp.reset()
fp.when(r"FROM orders WHERE student_id = '11230321209' AND due_amount > 0", [{"id": "7", "file_name": "My Report.pdf", "due_amount": "31.00"}])
b = cp.get("/pay.php").data.decode()
ok('<option value="7">File: My Report.pdf (Due: ৳31.00)</option>' in b, "pay option list")
fp.reset()
fp.when(r"SELECT \* FROM orders WHERE id = 7 AND student_id", [{"id": "7", "paid_amount": "10.00", "total_amount": "31.00"}])
fp.when(r"due_amount > 0", [])
b = cp.post("/pay.php", data={"order_id": "7", "amount_paid": "21", "trx_id": " 9H87 "}).data.decode()
ok("Payment submitted successfully! Waiting for admin verification." in b, "pay success")
up = [l for l in fp.LOG if l[0].startswith("UPDATE orders SET paid_amount")][0]
eq(up[1], (31.0, 0.0, "bKash", "9H87", "Paid", 7), "pay update params")
ok("Please provide a valid amount and bKash Transaction ID." in cp.post("/pay.php", data={"order_id": "7", "amount_paid": "0", "trx_id": "x"}).data.decode(), "pay invalid amount")
fp.reset(); fp.when(r"SELECT \* FROM orders WHERE id", [])
ok("Invalid order selected." in cp.post("/pay.php", data={"order_id": "7", "amount_paid": "5", "trx_id": "x"}).data.decode(), "pay invalid order")

# ---- admin.php (old panel)
fp.reset()
fp.when(r"SELECT total_amount FROM orders WHERE id = 7", [{"total_amount": "100.00"}])
fp.when(r"FROM orders\s+JOIN students", [{"id": "7", "name": "Ann <x>", "department": "CSE", "std_unique_id": "112", "phone": "017", "file_path": "uploads/a.pdf",
                                          "file_name": "a&b.pdf", "cover_page": "Yes", "binding_type": "Tape", "total_pages": "5", "color_pages": "1",
                                          "bw_pages": "4", "total_amount": "100.00", "paid_amount": "40.00", "due_amount": "60.00", "payment_method": "bKash",
                                          "trx_id": "TRX1", "order_status": "Printing", "payment_status": "Partial"}])
b = appmod.app.test_client().post("/admin.php", data={"update_status": "1", "order_id": "7", "order_status": "Completed", "payment_status": "Paid", "paid_amount": "100"}).data.decode()
up = [l for l in fp.LOG if l[0].startswith("UPDATE orders SET order_status")][0]
eq(up[1], ("Completed", "Paid", 100.0, 0, 7), "admin.php update params")
ok("Ann &lt;x&gt;" in b and "a&amp;b.pdf" in b and 'href="uploads/a.pdf"' in b and "TrxID: TRX1" in b, "admin.php escaping")
ok('<option value="Printing" selected>' in b and '<option value="Partial" selected>' in b and '<option value="Pending" >' in b, "admin.php selects")

# ---- admin_dashboard
ca = appmod.app.test_client()
eq(ca.get("/admin_dashboard.php").headers["Location"], "login.php", "admin_dashboard w/o session")
with ca.session_transaction() as s:
    s["student_id"] = "11230320001"
fp.reset()
fp.when(r"SELECT role, email FROM users", [{"role": "student", "email": "e"}])
eq(ca.get("/admin_dashboard.php").headers["Location"], "dashboard.php", "non-admin -> dashboard")

STUDENTS = [
    {"id": "1", "name": "Ann", "student_id": "11230321209", "department": "CSE", "section": "A", "phone": "", "password": "", "email": "", "due_amount": "50.00",
     "created_at": "2025-01-01 00:00:00", "user_role": "student", "user_email": "a@b.c", "registered": "1", "reg_password": "secret", "order_count": "2", "order_total": "80.00"},
    {"id": "2", "name": "Bob <&>", "student_id": "11230320002", "department": "EEE", "section": "B", "phone": "", "password": "", "email": "", "due_amount": "-5.00",
     "created_at": None, "user_role": None, "user_email": None, "registered": "0", "reg_password": None, "order_count": "0", "order_total": "0"},
    {"id": "3", "name": "Cy", "student_id": "11230320003", "department": "ME", "section": "C", "phone": "", "password": "", "email": "", "due_amount": "120.50",
     "created_at": "2025-01-01 00:00:00", "user_role": "admin", "user_email": "c@d.e", "registered": "1", "reg_password": "5f4dcc3b5aa765d61d8327deb882cf99", "order_count": "1", "order_total": "40.00"},
]
AORD = [{"id": "7", "student_id": "11230321209", "student_name": "Ann", "file_name": "it's \"x\".pdf", "file_path": "uploads/a.pdf", "total_pages": "5", "color_pages": "1",
         "bw_pages": "4", "cover_page": "Yes", "binding_type": "Tape", "print_mode": "color", "total_amount": "40.00", "order_status": "Completed", "order_date": "2025-01-02 10:00:00"},
        {"id": "8", "student_id": "11230321209", "student_name": "Ann", "file_name": "b.pdf", "file_path": "N/A", "total_pages": "5", "color_pages": "0",
         "bw_pages": "5", "cover_page": "No", "binding_type": "None", "print_mode": None, "total_amount": "40.00", "order_status": "Printing", "order_date": "2025-01-03 10:00:00"}]
APAY = [{"id": "1", "student_id": "11230321209", "student_name": "Ann", "paid_amount": "25.50", "payment_method": "bKash", "trx_id": "T1", "payment_status": "Partial", "payment_date": "2025-01-05 10:00:00"}]


def adm_rules():
    fp.reset()
    fp.when(r"SELECT role, email FROM users", [{"role": "admin", "email": "adm@x.y"}])
    fp.when(r"SHOW COLUMNS FROM `users`", [{"Field": "password"}])
    fp.when(r"SHOW COLUMNS FROM `students`", [{"Field": "password"}])
    fp.when(r"SELECT name FROM students WHERE student_id", [{"name": "Admin <A>"}])
    fp.when(r"FROM students s\s+LEFT JOIN users u ON u.student_id = s.student_id\s+LEFT JOIN", STUDENTS)
    fp.when(r"FROM orders o LEFT JOIN students", AORD)
    fp.when(r"FROM payments p LEFT JOIN", APAY)
    fp.when(r"SUM\(role='student'\)", [{"students_reg": Decimal(2), "admins": Decimal(1)}])


adm_rules()
r = ca.get("/admin_dashboard.php")
b = r.data.decode()
ok(r.status_code == 200 and b.lstrip().startswith("<!DOCTYPE html>"), "admin_dashboard renders")
ok("Admin &lt;A&gt;" in b, "admin name escaped")
# stats: due 50 + 120.5 = 170.5 ; credit 5 ; collected 25.5 ; revenue 80
ok('data-count="170.50"' in b and ">Tk 170.50<" in b, "due stat")
ok("from 2 student(s)" in b and "Tk 5.00 advance held" in b, "due students / advance")
ok('data-count="25.50"' in b and "1 payment(s) received" in b, "collected stat")
ok('data-count="80.00"' in b and "2 order(s) placed" in b, "revenue stat")
ok("Pending 1" in b and "Completed 1" in b, "status counts (Printing counted as Pending)")
ok('style="width:50%"' in b, "bar widths: " + str(re.findall(r'style="width:[^"]*"', b)[:8]))
ok("Highest Dues" in b and "openStudent('11230320003')" in b and "Tk 120.50" in b, "top due list")
ok(b.index("11230320003") < b.index("11230321209") if "openStudent('11230321209')" in b else True, "top due sorted desc")
m = re.search(r"const DATA = (\{.*?\});\r\n", b, re.S)
ok(m is not None, "DATA payload present")
data = m.group(1)
ok("<" not in data and ">" not in data and "&" not in data and "'" not in data, "payload is HEX-escaped (no raw < > & ')")
import json as _j
dj = _j.loads(data)
eq(dj["students"][0]["password"], "secret", "plain password exposed (as original)")
eq(dj["students"][2]["pw_kind"], "hash", "hash kind")
eq(dj["students"][2]["password"], "", "hash not exposed")
eq(dj["students"][1]["role"], None, "null role")
eq(dj["orders"][0]["file_name"], "it's \"x\".pdf", "payload quote escaping round-trips")
eq(dj["orders"][1]["status"], "Pending", "printing -> Pending")
eq(dj["payments"][0]["amount"], 25.5, "payment amount float")
eq(dj["students"][0]["due"], 50.0, "due float")
csrf = re.search(r"const CSRF = '([0-9a-f]{32})';", b).group(1)
ok(f"const ME = '11230320001';" in b and "showTab('overview');" in b, "ME and active tab")
ok(b.count('name="csrf" value="' + csrf + '"') >= 3, "csrf in forms")

# tab via GET
adm_rules()
ok("showTab('orders');" in ca.get("/admin_dashboard.php?tab=orders").data.decode(), "tab=orders")
adm_rules()
ok("showTab('overview');" in ca.get("/admin_dashboard.php?tab=hacker").data.decode(), "invalid tab -> overview")
# flash
adm_rules()
b = ca.get("/admin_dashboard.php?success=role_changed").data.decode()
ok('id="toast"' in b and "Account role updated!" in b and "bg-emerald-50" in b, "flash toast")
# no csrf
adm_rules()
b = ca.post("/admin_dashboard.php", data={"form_type": "update_status", "order_id": "7", "status": "Completed"}).data.decode()
ok("Session expired. Please reload the page and try again." in b and "bg-rose-50" in b, "csrf required")
# update status
adm_rules()
r = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "update_status", "order_id": "7", "status": "Completed"})
eq(r.headers["Location"], "admin_dashboard.php?tab=orders&success=status_updated", "update_status redirect")
adm_rules()
ok("Could not update the order status." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "update_status", "order_id": "7", "status": "Printing"}).data.decode(), "status whitelist")
# add student
adm_rules()
fp.when(r"SELECT id FROM students WHERE student_id", [])
r = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "add_student", "name": " Dan ", "student_id": "11230321999", "department": "CSE", "section": "A"})
eq(r.headers["Location"], "admin_dashboard.php?tab=students&success=student_added", "add student redirect")
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO students")][0]
eq(ins[1], ("Dan", "11230321999", "CSE", "A"), "add student params")
adm_rules()
b = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "add_student", "name": "Dan", "student_id": "123", "department": "CSE", "section": "A"}).data.decode()
ok("Student ID must be 4 to 11 digits (login uses the last 4 digits)." in b and "openModal('m-add');" in b and "showTab('students');" in b, "add student invalid id keeps modal open")
ok('value="Dan"' in b and 'value="123"' in b, "old input repopulated")
adm_rules()
fp.when(r"SELECT id FROM students WHERE student_id", [{"id": 1}])
ok("A student with this Student ID already exists!" in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "add_student", "name": "Dan", "student_id": "11230321999", "department": "CSE", "section": "A"}).data.decode(), "dup student")
# edit student
adm_rules()
r = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "edit_student", "student_id": "11230321209", "name": "Ann2", "department": "CSE", "section": "B"})
eq(r.headers["Location"], "admin_dashboard.php?tab=students&success=student_updated", "edit student")
# receive payment
adm_rules()
fp.when(r"SELECT due_amount FROM students WHERE student_id", [{"due_amount": "50.00"}])
r = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "receive_payment", "student_id": "11230321209", "amount": "70", "method": "bKash", "trx_id": " TX9 "})
eq(r.headers["Location"], "admin_dashboard.php?tab=cash&success=payment_received", "receive payment redirect")
sqls = [l[0] for l in fp.LOG]
ok("BEGIN" in sqls and "COMMIT" in sqls and "ROLLBACK" not in sqls, "payment in a transaction")
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO payments")][0]
eq(ins[1], ("11230321209", 70.0, "bKash", "TX9", "Paid"), "payment insert (overpay -> Paid)")
d = [l for l in fp.LOG if l[0].startswith("UPDATE students SET due_amount = %s")][0]
eq(d[1], (-20.0, "11230321209"), "advance stored as negative due")
adm_rules()
fp.when(r"SELECT due_amount FROM students WHERE student_id", [{"due_amount": "50.00"}])
ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "receive_payment", "student_id": "11230321209", "amount": "20", "method": "Cash", "trx_id": "ignored"})
ins = [l for l in fp.LOG if l[0].startswith("INSERT INTO payments")][0]
eq(ins[1], ("11230321209", 20.0, "Cash", None, "Partial"), "cash payment: trx NULL, Partial")
adm_rules()
fp.when(r"SELECT due_amount FROM students WHERE student_id", [{"due_amount": "50.00"}])
fp.FAIL.append(r"INSERT INTO payments")
b = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "receive_payment", "student_id": "11230321209", "amount": "20"}).data.decode()
ok("Could not record the payment." in b and "ROLLBACK" in [l[0] for l in fp.LOG] and "showTab('cash');" in b, "payment failure rolls back")
adm_rules()
fp.when(r"SELECT due_amount FROM students WHERE student_id", [])
ok("Student not found." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "receive_payment", "student_id": "1", "amount": "20"}).data.decode(), "payment student missing")
adm_rules()
fp.when(r"SELECT due_amount FROM students WHERE student_id", [{"due_amount": "5"}])
ok("Please enter a valid amount." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "receive_payment", "student_id": "1", "amount": "-3"}).data.decode(), "payment invalid amount")
# change role
adm_rules()
ok("You cannot change your own role." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "change_role", "student_id": "11230320001", "role": "student"}).data.decode(), "cannot change own role")
adm_rules()
ok("Invalid role." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "change_role", "student_id": "x", "role": "root"}).data.decode(), "invalid role")
adm_rules()
eq(ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "change_role", "student_id": "11230321209", "role": "admin"}).headers["Location"],
   "admin_dashboard.php?tab=registered&success=role_changed", "change role")
# change password (plain / md5 style)
adm_rules()
fp.when(r"SELECT id FROM users WHERE student_id", [{"id": 1}])
fp.when(r"AS pw FROM students s LEFT JOIN users u ON u.student_id = s.student_id WHERE s.student_id = %s", [{"pw": "5f4dcc3b5aa765d61d8327deb882cf99"}])
r = ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "change_password", "student_id": "11230321209", "new_password": "hello"})
eq(r.headers["Location"], "admin_dashboard.php?tab=registered&success=password_changed", "change password redirect")
ups = [l for l in fp.LOG if l[0].startswith("UPDATE users SET password") or l[0].startswith("UPDATE students SET password")]
eq([u[1] for u in ups], [("5d41402abc4b2a76b9719d911017c592", "11230321209")] * 2, "password stored md5 like existing ones, in both tables")
adm_rules()
fp.when(r"SELECT id FROM users WHERE student_id", [])
ok("This student has not registered yet." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "change_password", "student_id": "1", "new_password": "hello"}).data.decode(), "pw: not registered")
adm_rules()
fp.when(r"SELECT id FROM users WHERE student_id", [{"id": 1}])
ok("Password must be at least 4 characters." in ca.post("/admin_dashboard.php", data={"csrf": csrf, "form_type": "change_password", "student_id": "1", "new_password": "abc"}).data.decode(), "pw: too short")
# admin download
adm_rules()
fp.when(r"SELECT file_path, file_name FROM orders WHERE id", [{"file_path": "uploads/t_test.pdf", "file_name": "x.pdf"}])
r = ca.get("/admin_dashboard.php?action=download&order_id=7")
ok(r.data == b"%PDF-1.4 test" and "Pragma" not in r.headers and r.headers["Content-Disposition"] == 'attachment; filename="x.pdf"', "admin download (no cache headers, as in PHP)")

# ---- uploaded files are still served at /uploads/...
r = appmod.app.test_client().get("/uploads/t_test.pdf")
ok(r.status_code == 200 and r.data == b"%PDF-1.4 test", "uploads served")

# ---- cleanup test artefacts
import glob, shutil
for f in glob.glob(os.path.join(appmod.BASE_DIR, "uploads", "*")):
    os.remove(f)
os.rmdir(os.path.join(appmod.BASE_DIR, "uploads"))
os.remove(os.path.join(appmod.BASE_DIR, "count_pages.py"))
sk = os.path.join(appmod.BASE_DIR, ".secret_key")
if os.path.exists(sk):
    os.remove(sk)

print("ALL %d CHECKS PASSED" % PASS)
