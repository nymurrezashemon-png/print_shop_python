"""
Print Shop - Python (Flask) version of the original PHP project.

Every PHP file became one route with the SAME URL (login.php, register.php, dashboard.php ...),
so every href / form action / fetch('') inside the unchanged HTML keeps working.
Logic, SQL, messages, prices and validation are ported line by line.

File map
    index.php            -> index()
    login.php            -> login()
    register.php         -> register()
    forgot-password.php  -> forgot_password()
    verify-code.php      -> verify_code()
    logout.php           -> logout()
    dashboard.php        -> dashboard()
    admin_dashboard.php  -> admin_dashboard()
    admin.php            -> admin()
    pay.php              -> pay()
    analyze.php          -> analyze()
    db.php               -> db.py
"""
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import subprocess

from flask import Flask, Response, g, request, send_from_directory, session, render_template

import db as dbmod
from php_compat import (
    trim, strlen, strtolower, ctype_digit, htmlspecialchars, h, php_str, e, floatval, intval,
    to_number, gt_zero, php_round, number_format, php_abs, php_max, php_count, empty, nc,
    json_encode, json_encode_flags, uniqid, escapeshellarg, client_basename, password_algo,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))     # PHP __DIR__


# ======================================================================== Flask setup
class PhpStyleFlask(Flask):
    # custom delimiters so that nothing inside the original HTML / CSS / JS can be mistaken for template code
    jinja_options = {
        **Flask.jinja_options,
        "block_start_string": "<%PY", "block_end_string": "PY%>",
        "variable_start_string": "<%=", "variable_end_string": "=%>",
        "comment_start_string": "<%#", "comment_end_string": "#%>",
        "autoescape": False,                 # PHP `echo` does not escape; escaping is explicit (h / htmlspecialchars)
        "newline_sequence": "\r\n",          # the original files use CRLF
        "keep_trailing_newline": True,
    }


app = PhpStyleFlask(__name__, template_folder="templates", static_folder=None)


def _load_secret_key():
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app.secret_key = _load_secret_key()           # needed for Flask sessions (PHP did this with PHPSESSID)

app.jinja_env.globals.update(
    e=e, h=h, htmlspecialchars=htmlspecialchars, number_format=number_format, php_abs=php_abs,
    php_max=php_max, php_round=php_round, php_count=php_count, empty=empty, nc=nc,
    floatval=floatval, intval=intval, json_encode=json_encode, json_encode_flags=json_encode_flags,
    strtolower=strtolower, gt_zero=gt_zero,
)

METHODS = ["GET", "POST"]


# ======================================================================== request helpers
def get_conn():
    """include 'db.php';"""
    if "conn" not in g:
        g.conn = dbmod.connect()
    return g.conn


@app.teardown_appcontext
def _close_db(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


@app.errorhandler(dbmod.ConnectionFailed)
def _conn_failed(ex):
    return Response(str(ex), mimetype="text/html")      # die("Connection Failed: ...")


def _php_array(pairs, last_wins=True):
    out = {}
    for k, v in pairs:
        if k.endswith("[]"):
            base = k[:-2]
            if not isinstance(out.get(base), list):
                out[base] = []
            out[base].append(v)
        else:
            out[k] = v
    return out


def POST():
    if "_post" not in g:
        g._post = _php_array(request.form.items(multi=True)) if request.method == "POST" else {}
    return g._post


def GET():
    if "_get" not in g:
        g._get = _php_array(request.args.items(multi=True))
    return g._get


def php_redirect(url):
    """header("Location: ..."); exit();"""
    return Response("", status=302, headers={"Location": url})


def json_response(obj):
    """header('Content-Type: application/json'); echo json_encode(...);"""
    return Response(json_encode(obj), content_type="application/json")


def render(name, **ctx):
    return Response(render_template(name + ".html", **ctx))


def isset_session(key):
    return session.get(key) is not None


def php_basename(name):
    return client_basename(php_str(name))


def shell_exec(cmd):
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    except Exception:
        return None
    out = r.stdout.decode("utf-8", "replace")
    return out if out != "" else None


def parse_counter_output(output):
    """preg_match('/\\{.*\\}/s', $output, $m); json_decode($m[0], true)"""
    data = None
    mo = re.search(r"\{.*\}", output or "", re.S)
    if mo:
        try:
            data = json.loads(mo.group(0))
        except ValueError:
            data = None
    return data


def has_total(data):
    return bool(data) and isinstance(data, dict) and data.get("total") is not None


def download_response(file_path, file_name, dashboard_style):
    size = os.path.getsize(file_path)

    def stream():
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    disp = 'attachment; filename="' + php_basename(file_name) + '"'
    headers = {
        "Content-Description": "File Transfer",
        "Content-Type": "application/octet-stream",
        # PHP sends the raw bytes of the name - keep them as UTF-8 on the wire
        "Content-Disposition": disp.encode("utf-8").decode("latin-1"),
    }
    if dashboard_style:
        headers.update({"Expires": "0", "Cache-Control": "must-revalidate", "Pragma": "public"})
    headers["Content-Length"] = str(size)
    return Response(stream(), headers=headers)


# ======================================================================== index.php
@app.route("/", methods=METHODS)
@app.route("/index.php", methods=METHODS)
def index():
    # Redirect users directly to the login page
    return php_redirect("login.php")


# ======================================================================== login.php
def dashboard_for_role(role):
    return "admin_dashboard.php" if strtolower(trim(php_str(role))) == "admin" else "dashboard.php"


@app.route("/login.php", methods=METHODS)
def login():
    conn = get_conn()

    error = ""
    success = ""
    redirect = False
    redirect_url = ""

    # Already logged in? Send the user straight to the dashboard of their role
    if request.method != "POST" and isset_session("student_id"):
        return php_redirect(dashboard_for_role(session.get("role", "")))

    if request.method == "POST":
        post = POST()
        student_id_input = trim(post.get("student_id"))
        password = trim(post.get("password"))

        if not empty(student_id_input) and not empty(password):
            if strlen(student_id_input) == 4 and ctype_digit(student_id_input):
                # Find users where student_id in users table ends with the given 4 digits
                stmt = conn.prepare("SELECT * FROM users WHERE student_id LIKE ?")
                search_param = "%" + student_id_input
                stmt.bind_param("s", search_param)
                stmt.execute()
                result = stmt.get_result()

                login_success = False
                matched_user = None

                while True:
                    row = result.fetch_assoc()
                    if row is None:
                        break
                    db_last_four = php_str(row["student_id"])[-4:]
                    if db_last_four == student_id_input:
                        # Password check
                        if password == row["password"]:
                            matched_user = row
                            login_success = True
                            break

                if login_success and matched_user:
                    user_role = strtolower(trim(php_str(matched_user["role"])))

                    # session_regenerate_id(true): Flask signs a brand-new cookie on every change
                    session["student_id"] = matched_user["student_id"]
                    session["email"] = matched_user["email"]
                    session["role"] = user_role

                    redirect = True
                    redirect_url = dashboard_for_role(user_role)
                    success = ("Welcome back, Admin! Opening your control panel..."
                               if user_role == "admin" else "Login successful! Welcome back.")
                else:
                    error = "Invalid Student ID (Last 4 digits) or Incorrect password!"
            else:
                error = "Student ID must be exactly the last 4 digits (numeric)!"
        else:
            error = "Please fill in all fields."

    return render("login", error=error, success=success, redirect=redirect, redirect_url=redirect_url)


# ======================================================================== register.php
@app.route("/register.php", methods=METHODS)
def register():
    conn = get_conn()

    error = ""
    success = ""
    redirect = False
    redirect_url = "login.php"

    if request.method == "POST":
        post = POST()
        email = trim(post.get("email"))
        student_id_input = trim(post.get("student_id"))
        password = trim(post.get("password"))

        if not empty(email) and not empty(student_id_input) and not empty(password):
            if strlen(student_id_input) == 4 and ctype_digit(student_id_input):
                # Check if students table has an ID ending with these 4 digits
                check_student = conn.prepare("SELECT student_id, name FROM students WHERE student_id LIKE ?")
                search_param = "%" + student_id_input
                check_student.bind_param("s", search_param)
                check_student.execute()
                result_student = check_student.get_result()

                matched_full_student_id = ""
                while True:
                    row_s = result_student.fetch_assoc()
                    if row_s is None:
                        break
                    if php_str(row_s["student_id"])[-4:] == student_id_input:
                        matched_full_student_id = row_s["student_id"]
                        break

                if not empty(matched_full_student_id):
                    check_stmt = conn.prepare("SELECT id FROM users WHERE email = ? OR student_id = ?")
                    check_stmt.bind_param("ss", email, matched_full_student_id)
                    check_stmt.execute()
                    check_stmt.store_result()

                    if check_stmt.num_rows > 0:
                        error = "An account with this Email or Student ID already exists!"
                    else:
                        stmt = conn.prepare("INSERT INTO users (student_id, email, password, role) VALUES (?, ?, ?, 'student')")
                        stmt.bind_param("sss", matched_full_student_id, email, password)

                        if stmt.execute():
                            success = "Registration successful! Redirecting to login..."
                            redirect = True
                        else:
                            error = "Something went wrong. Please try again."
                else:
                    error = "No student found with these last 4 digits in university records!"
            else:
                error = "Student ID must be exactly the last 4 digits (numeric)!"
        else:
            error = "Please fill in all fields."

    return render("register", error=error, success=success, redirect=redirect, redirect_url=redirect_url)


# ======================================================================== forgot-password.php
@app.route("/forgot-password.php", methods=METHODS)
def forgot_password():
    conn = get_conn()

    error = ""
    success = ""
    redirect = False
    redirect_url = "verify-code.php"

    if request.method == "POST":
        post = POST()
        email = trim(post.get("email"))
        student_id = trim(post.get("student_id"))

        if not empty(email) and not empty(student_id):
            stmt = conn.prepare("SELECT * FROM users WHERE email = ? AND student_id = ?")
            stmt.bind_param("ss", email, student_id)
            stmt.execute()
            result = stmt.get_result()

            row = result.fetch_assoc()
            if row:
                reset_code = random.randint(100000, 999999)
                update_stmt = conn.prepare(
                    "UPDATE users SET reset_code = ?, reset_expire = DATE_ADD(NOW(), INTERVAL 3 MINUTE) WHERE email = ? AND student_id = ?")
                update_stmt.bind_param("sss", reset_code, email, student_id)

                if update_stmt.execute():
                    session["reset_email"] = email
                    success = "Verification code generated! Redirecting..."
                    redirect = True
                else:
                    error = "Something went wrong. Please try again."
            else:
                error = "No account found matching this Gmail and Student ID!"
        else:
            error = "Please fill in all fields."

    return render("forgot-password", error=error, success=success, redirect=redirect, redirect_url=redirect_url)


# ======================================================================== verify-code.php
@app.route("/verify-code.php", methods=METHODS)
def verify_code():
    conn = get_conn()

    error = ""
    success = ""
    redirect = False
    redirect_url = "login.php"

    if not isset_session("reset_email"):
        return php_redirect("forgot-password.php")

    email = session["reset_email"]

    if request.method == "POST":
        post = POST()
        code = trim(post.get("code"))
        new_password = trim(post.get("new_password"))

        if not empty(code) and not empty(new_password):
            stmt = conn.prepare("SELECT * FROM users WHERE email = ? AND reset_code = ? AND reset_expire > NOW()")
            stmt.bind_param("ss", email, code)
            stmt.execute()
            result = stmt.get_result()

            row = result.fetch_assoc()
            if row:
                update_stmt = conn.prepare("UPDATE users SET password = ?, reset_code = NULL, reset_expire = NULL WHERE email = ?")
                update_stmt.bind_param("ss", new_password, email)

                if update_stmt.execute():
                    session.pop("reset_email", None)
                    success = "Password reset successful! Redirecting to login..."
                    redirect = True
                else:
                    error = "Something went wrong. Please try again."
            else:
                error = "Invalid or expired verification code!"
        else:
            error = "Please fill in all fields."

    return render("verify-code", error=error, success=success, redirect=redirect, redirect_url=redirect_url)


# ======================================================================== logout.php
@app.route("/logout.php", methods=METHODS)
def logout():
    # Unset all session variables / destroy session cookie / destroy session
    session.clear()

    success = "Logged out successfully! Redirecting to login..."
    redirect_url = "login.php"
    return render("logout", success=success, redirect_url=redirect_url)


# ======================================================================== analyze.php
@app.route("/analyze.php", methods=METHODS)
def analyze():
    f = request.files.get("pdf_file")
    if f is not None and f.filename != "":                      # $_FILES['pdf_file']['error'] == 0
        file_name = php_basename(f.filename)
        upload_dir = BASE_DIR + os.sep + "uploads" + os.sep

        if not os.path.isdir(upload_dir):
            os.makedirs(upload_dir, mode=0o777, exist_ok=True)

        new_file_name = uniqid() + "_" + file_name
        upload_full_path = upload_dir + new_file_name
        db_file_path = "uploads/" + new_file_name

        try:
            f.save(upload_full_path)                            # move_uploaded_file
            moved = True
        except OSError:
            moved = False

        if moved:
            python_path = "C:\\Users\\nymur\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
            script_path = BASE_DIR + os.sep + "count_pages.py"

            command = python_path + " " + escapeshellarg(script_path) + " " + escapeshellarg(upload_full_path)
            output = shell_exec(command)

            data = parse_counter_output(output)

            if has_total(data):
                data["saved_path"] = db_file_path
                data["original_name"] = file_name
                return json_response(data)
            else:
                return json_response({"total": 1, "color": 0, "bw": 1, "saved_path": db_file_path, "original_name": file_name})
        else:
            return json_response({"error": "Upload failed"})
    else:
        return json_response({"error": "No file uploaded"})


# ======================================================================== uploaded files (Apache served /uploads/* directly)
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(os.path.join(BASE_DIR, "uploads"), filename)


# ======================================================================== pay.php
@app.route("/pay.php", methods=METHODS)
def pay():
    conn = get_conn()

    # Redirect to login if student is not authenticated
    if not isset_session("student_id"):
        return php_redirect("login.php")

    student_id = session["student_id"]
    success = ""
    error = ""

    if request.method == "POST":
        post = POST()
        order_id = post.get("order_id")
        amount_paid = post.get("amount_paid")
        trx_id = trim(post.get("trx_id"))
        payment_method = "bKash"

        if not empty(trx_id) and gt_zero(amount_paid):
            # Fetch specific order details
            order_query = conn.query("SELECT * FROM orders WHERE id = %s AND student_id = '%s'" % (php_str(order_id), php_str(student_id)))
            if order_query.num_rows > 0:
                order = order_query.fetch_assoc()

                new_paid = to_number(order["paid_amount"]) + to_number(amount_paid)
                new_due = to_number(order["total_amount"]) - new_paid
                if new_due < 0:
                    new_due = 0

                payment_status = "Paid" if new_due == 0 else "Partial"

                # Update payment information in the database
                update = conn.prepare("UPDATE orders SET paid_amount = ?, due_amount = ?, payment_method = ?, trx_id = ?, payment_status = ? WHERE id = ?")
                update.bind_param("ddsssi", new_paid, new_due, payment_method, trx_id, payment_status, order_id)

                if update.execute():
                    success = "Payment submitted successfully! Waiting for admin verification."
                else:
                    error = "Failed to update payment information."
            else:
                error = "Invalid order selected."
        else:
            error = "Please provide a valid amount and bKash Transaction ID."

    # Fetch orders with remaining due amount for this student
    orders = conn.query("SELECT * FROM orders WHERE student_id = '%s' AND due_amount > 0" % php_str(student_id))
    return render("pay", success=success, error=error, orders=orders.rows)


# ======================================================================== admin.php
@app.route("/admin.php", methods=METHODS)
def admin():
    conn = get_conn()

    # Update order status and payment details
    post = POST()
    if "update_status" in post:
        order_id = post.get("order_id")
        order_status = post.get("order_status")
        payment_status = post.get("payment_status")
        paid_amount = post.get("paid_amount")

        result = conn.query("SELECT total_amount FROM orders WHERE id = %s" % php_str(order_id))
        order = result.fetch_assoc()
        total_amount = nc(order, "total_amount", None)

        # Recalculate due amount
        due_amount = to_number(total_amount) - to_number(paid_amount)
        if due_amount < 0:
            due_amount = 0

        update_sql = "UPDATE orders SET order_status = ?, payment_status = ?, paid_amount = ?, due_amount = ? WHERE id = ?"
        stmt = conn.prepare(update_sql)
        stmt.bind_param("ssddi", order_status, payment_status, paid_amount, due_amount, order_id)
        stmt.execute()

    # Fetch all orders joining with students table
    query = ("SELECT orders.*, students.name, students.department, students.student_id AS std_unique_id, students.phone "
             "FROM orders "
             "JOIN students ON orders.student_id = students.student_id "
             "ORDER BY orders.order_date DESC")
    orders_result = conn.query(query)
    return render("admin", orders=orders_result.rows)


# ======================================================================== dashboard.php
def run_page_counter(full_path):
    """Helper: run count_pages.py on a PDF and return ['total'=>, 'color'=>, 'bw'=>] or None"""
    python_path = "python"
    script_path = BASE_DIR + "/count_pages.py"
    command = python_path + " " + escapeshellarg(script_path) + " " + escapeshellarg(full_path)
    output = shell_exec(command)
    if not empty(output):
        data = parse_counter_output(output)
        if has_total(data):
            return data
    return None


def _cover_items(subject_names, subject_quantities):
    if not isinstance(subject_names, list):
        subject_names = [subject_names]
    if not isinstance(subject_quantities, list):
        subject_quantities = [subject_quantities]

    items = []
    total_quantity = 0
    row_count = max(len(subject_names), len(subject_quantities))
    for i in range(row_count):
        subject = trim(subject_names[i] if i < len(subject_names) else "")
        qty = intval(subject_quantities[i] if i < len(subject_quantities) else 0)

        if subject != "" and qty > 0:
            items.append({"subject": subject, "quantity": qty})
            total_quantity += qty
    return items, total_quantity


def _cover_file_name(items, total_quantity):
    summary_parts = [item["subject"] + " - " + php_str(item["quantity"]) + " Pcs" for item in items]
    return "Cover Page Order (" + php_str(total_quantity) + " Pcs) || " + " || ".join(summary_parts)


@app.route("/dashboard.php", methods=METHODS)
def dashboard():
    conn = get_conn()

    if not isset_session("student_id"):
        return php_redirect("login.php")

    student_id = session["student_id"]

    success = ""
    error = ""
    post = POST()
    get = GET()
    is_post = request.method == "POST"

    # ---- Handle Redownload Request
    if get.get("action") == "download" and "order_id" in get:
        dl_id = intval(get["order_id"])
        dl_stmt = conn.prepare("SELECT file_path, file_name FROM orders WHERE id = ? AND student_id = ?")
        dl_stmt.bind_param("is", dl_id, student_id)
        dl_stmt.execute()
        dl_res = dl_stmt.get_result().fetch_assoc()

        if dl_res and not empty(dl_res["file_path"]) and dl_res["file_path"] != "N/A":
            file_path = BASE_DIR + "/" + dl_res["file_path"]
            if os.path.exists(file_path):
                return download_response(file_path, dl_res["file_name"], True)
            else:
                error = "File not found on server."

    # ---- Handle Redirect Success Messages
    if "success" in get:
        if get["success"] == "pdf_ordered":
            success = "Print order placed successfully!"
        elif get["success"] == "a4_ordered":
            success = "A4 Page Order placed successfully!"
        elif get["success"] == "a4_updated":
            success = "A4 Page Order updated successfully!"
        elif get["success"] == "cover_ordered":
            success = "Cover Page Order placed successfully!"
        elif get["success"] == "cover_updated":
            success = "Cover Page Order updated successfully!"
        elif get["success"] == "order_updated":
            success = "Order updated successfully!"

    # ---- AJAX endpoint: re-scan the already uploaded PDF of an existing order (used by Edit Modal)
    if post.get("action") == "analyze_existing":
        ex_id = intval(nc(post, "order_id", 0))
        ex_q = conn.prepare("SELECT file_path, total_pages, color_pages, bw_pages, print_mode FROM orders WHERE id = ? AND student_id = ?")
        ex_q.bind_param("is", ex_id, student_id)
        ex_q.execute()
        ex = ex_q.get_result().fetch_assoc()

        if not ex:
            return json_response({"error": "Order not found"})

        ex_path = BASE_DIR + "/" + php_str(ex["file_path"])
        if not empty(ex["file_path"]) and ex["file_path"] != "N/A" and os.path.isfile(ex_path):
            data = run_page_counter(ex_path)
            if data:
                return json_response(data)
        # Fallback: use what is stored in the database
        return json_response({
            "total": intval(ex["total_pages"]),
            "color": intval(ex["color_pages"]),
            "bw": intval(ex["bw_pages"]),
            "fallback": True,
        })

    # ---- AJAX endpoint for scanning PDF pages (Used for both New Order & Edit Modal)
    if post.get("action") == "analyze_pdf":
        f = request.files.get("pdf_file")
        if f is not None and f.filename != "":
            file_name = php_basename(f.filename)
            upload_dir = BASE_DIR + "/uploads/"

            if not os.path.isdir(upload_dir):
                os.makedirs(upload_dir, mode=0o777, exist_ok=True)

            new_file_name = uniqid() + "_" + file_name
            upload_full_path = upload_dir + new_file_name
            db_file_path = "uploads/" + new_file_name

            try:
                f.save(upload_full_path)
                moved = True
            except OSError:
                moved = False

            if moved:
                python_path = "python"
                script_path = BASE_DIR + "/count_pages.py"

                command = python_path + " " + escapeshellarg(script_path) + " " + escapeshellarg(upload_full_path)
                output = shell_exec(command)
                data = parse_counter_output(output)

                if has_total(data):
                    data["saved_path"] = db_file_path
                    data["original_name"] = file_name
                    return json_response(data)
                else:
                    return json_response({"total": 1, "color": 0, "bw": 1, "saved_path": db_file_path, "original_name": file_name})
            else:
                return json_response({"error": "Upload failed"})
        else:
            return json_response({"error": "No file uploaded"})

    # ---- Handle PDF Print Order submission
    if is_post and "form_type" in post and post["form_type"] == "pdf_order":
        binding_type = "Tape" if "binding_type" in post else "Stapler"
        cover_page = "Yes" if "cover_page" in post else "No"
        print_mode = nc(post, "print_mode", "bw")

        db_file_path = nc(post, "server_file_path", "")
        file_name = nc(post, "original_file_name", "")
        total_pages = intval(nc(post, "hidden_total", 1))

        detected_color = intval(nc(post, "hidden_color", 0))
        detected_bw = intval(nc(post, "hidden_bw", total_pages))

        if print_mode == "color":
            color_pages = detected_color
            bw_pages = detected_bw
        else:
            color_pages = 0
            bw_pages = total_pages

        if not empty(db_file_path) and os.path.exists(BASE_DIR + "/" + php_str(db_file_path)):
            bw_cost = bw_pages * 2
            color_cost = color_pages * 5
            pages_cost = bw_cost + color_cost

            cover_cost = 5 if cover_page == "Yes" else 0
            binding_cost = 5 if binding_type == "Tape" else 0

            total_amount = pages_cost + cover_cost + binding_cost

            insert_order = ("INSERT INTO orders (student_id, file_name, file_path, total_pages, color_pages, bw_pages, cover_page, "
                            "binding_type, print_mode, total_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
            stmt = conn.prepare(insert_order)
            stmt.bind_param("sssiissssd", student_id, file_name, db_file_path, total_pages, color_pages, bw_pages,
                            cover_page, binding_type, print_mode, total_amount)

            if stmt.execute():
                update_due = "UPDATE students SET due_amount = due_amount + ? WHERE student_id = ?"
                stmt_due = conn.prepare(update_due)
                stmt_due.bind_param("ds", total_amount, student_id)
                stmt_due.execute()

                return php_redirect("dashboard.php?success=pdf_ordered")
            else:
                error = "Failed to save order to the database."
        else:
            error = "Please select and upload a valid PDF file first."

    # ---- Handle standalone Cover Page Order submission (multiple subjects in ONE order)
    if is_post and "form_type" in post and post["form_type"] == "cover_page_order":
        subject_names = nc(post, "cover_subject_name", [])
        subject_quantities = nc(post, "cover_subject_quantity", [])
        cover_binding = "Tape" if nc(post, "cover_binding_type", "") == "Tape" else "None"

        items, total_quantity = _cover_items(subject_names, subject_quantities)

        if len(items) > 0 and total_quantity > 0:
            binding_cost = (total_quantity * 5.00) if cover_binding == "Tape" else 0.00
            total_amount = (total_quantity * 5.00) + binding_cost
            file_name = _cover_file_name(items, total_quantity)
            db_file_path = "N/A"
            print_mode = "cover"

            insert_cover = ("INSERT INTO orders (student_id, file_name, file_path, total_pages, color_pages, bw_pages, cover_page, "
                            "binding_type, print_mode, total_amount) VALUES (?, ?, ?, ?, 0, ?, 'Yes', ?, ?, ?)")
            stmt = conn.prepare(insert_cover)
            stmt.bind_param("sssiissd", student_id, file_name, db_file_path, total_quantity, total_quantity,
                            cover_binding, print_mode, total_amount)

            if stmt.execute():
                update_due = "UPDATE students SET due_amount = due_amount + ? WHERE student_id = ?"
                stmt_due = conn.prepare(update_due)
                stmt_due.bind_param("ds", total_amount, student_id)
                stmt_due.execute()

                return php_redirect("dashboard.php?success=cover_ordered")
            else:
                error = "Failed to save Cover Page order."
        else:
            error = "Please add at least one subject with a valid quantity."

    # ---- Handle Cover Page Order edit (all subjects remain in ONE order)
    if is_post and "form_type" in post and post["form_type"] == "edit_cover_order":
        cover_edit_id = intval(nc(post, "cover_edit_order_id", 0))
        subject_names = nc(post, "edit_cover_subject_name", [])
        subject_quantities = nc(post, "edit_cover_subject_quantity", [])
        cover_binding = "Tape" if nc(post, "edit_cover_binding_type", "") == "Tape" else "None"

        items, total_quantity = _cover_items(subject_names, subject_quantities)

        cover_chk = conn.prepare("SELECT * FROM orders WHERE id = ? AND student_id = ?")
        cover_chk.bind_param("is", cover_edit_id, student_id)
        cover_chk.execute()
        cover_old = cover_chk.get_result().fetch_assoc()

        if (not cover_old or strtolower(nc(cover_old, "order_status", "Pending")) != "pending"
                or nc(cover_old, "print_mode", "") != "cover"):
            error = "Cover Page order cannot be edited."
        elif len(items) < 1 or total_quantity < 1:
            error = "Please keep at least one valid subject and quantity."
        else:
            binding_cost = (total_quantity * 5.00) if cover_binding == "Tape" else 0.00
            new_amount = (total_quantity * 5.00) + binding_cost
            diff = new_amount - floatval(cover_old["total_amount"])
            new_file_name = _cover_file_name(items, total_quantity)

            cover_up = conn.prepare("UPDATE orders SET file_name = ?, total_pages = ?, color_pages = 0, bw_pages = ?, cover_page = 'Yes', "
                                    "binding_type = ?, print_mode = 'cover', total_amount = ? WHERE id = ? AND student_id = ?")
            cover_up.bind_param("siisdis", new_file_name, total_quantity, total_quantity, cover_binding, new_amount,
                                cover_edit_id, student_id)

            if cover_up.execute():
                if diff != 0:
                    cover_adj = conn.prepare("UPDATE students SET due_amount = due_amount + ? WHERE student_id = ?")
                    cover_adj.bind_param("ds", diff, student_id)
                    cover_adj.execute()
                return php_redirect("dashboard.php?success=cover_updated")
            else:
                error = "Failed to update Cover Page order."

    # ---- Handle A4 Page Direct Order submission
    if is_post and "form_type" in post and post["form_type"] == "a4_page_order":
        a4_type = nc(post, "a4_type", "Blank Page")
        a4_quantity = intval(nc(post, "a4_quantity", 0))

        if a4_quantity > 0:
            total_amount = a4_quantity * 1.00
            file_name = "A4 Order: " + php_str(a4_type) + " (" + php_str(a4_quantity) + " Pcs)"
            db_file_path = "N/A"
            print_mode = "a4"

            insert_a4 = ("INSERT INTO orders (student_id, file_name, file_path, total_pages, color_pages, bw_pages, cover_page, "
                         "binding_type, print_mode, total_amount) VALUES (?, ?, ?, ?, 0, ?, 'No', 'None', ?, ?)")
            stmt = conn.prepare(insert_a4)
            stmt.bind_param("sssiisd", student_id, file_name, db_file_path, a4_quantity, a4_quantity, print_mode, total_amount)

            if stmt.execute():
                update_due = "UPDATE students SET due_amount = due_amount + ? WHERE student_id = ?"
                stmt_due = conn.prepare(update_due)
                stmt_due.bind_param("ds", total_amount, student_id)
                stmt_due.execute()

                return php_redirect("dashboard.php?success=a4_ordered")
            else:
                error = "Failed to save A4 page order."
        else:
            error = "Please enter a valid quantity for A4 pages."

    # ---- Handle A4 Page Order edit (paper type + quantity)
    if is_post and "form_type" in post and post["form_type"] == "edit_a4_order":
        a4_edit_id = intval(nc(post, "a4_edit_order_id", 0))
        a4_new_type = "Margin Page" if nc(post, "a4_edit_type", "") == "Margin Page" else "Blank Page"
        a4_new_qty = intval(nc(post, "a4_edit_quantity", 0))

        a4_chk = conn.prepare("SELECT * FROM orders WHERE id = ? AND student_id = ?")
        a4_chk.bind_param("is", a4_edit_id, student_id)
        a4_chk.execute()
        a4_old = a4_chk.get_result().fetch_assoc()

        if not a4_old or strtolower(nc(a4_old, "order_status", "Pending")) != "pending" or a4_old["print_mode"] != "a4":
            error = "Order cannot be edited."
        elif a4_new_qty < 1:
            error = "Please enter a valid quantity for A4 pages."
        else:
            a4_new_amount = a4_new_qty * 1.00
            a4_diff = a4_new_amount - to_number(a4_old["total_amount"])
            a4_new_name = "A4 Order: " + a4_new_type + " (" + php_str(a4_new_qty) + " Pcs)"

            a4_up = conn.prepare("UPDATE orders SET file_name = ?, total_pages = ?, color_pages = 0, bw_pages = ?, total_amount = ? WHERE id = ? AND student_id = ?")
            a4_up.bind_param("siidis", a4_new_name, a4_new_qty, a4_new_qty, a4_new_amount, a4_edit_id, student_id)

            if a4_up.execute():
                if a4_diff != 0:
                    a4_adj = conn.prepare("UPDATE students SET due_amount = due_amount + ? WHERE student_id = ?")
                    a4_adj.bind_param("ds", a4_diff, student_id)
                    a4_adj.execute()
                return php_redirect("dashboard.php?success=a4_updated")
            else:
                error = "Failed to update A4 order."

    # ---- Handle Edit Order submission
    if is_post and "form_type" in post and post["form_type"] == "edit_order":
        edit_order_id = intval(post.get("edit_order_id"))
        new_cover = "Yes" if "edit_cover_page" in post else "No"
        new_binding = "Tape" if "edit_binding_type" in post else "Stapler"
        new_print_mode = nc(post, "edit_print_mode", "bw")

        chk_st = conn.prepare("SELECT * FROM orders WHERE id = ? AND student_id = ?")
        chk_st.bind_param("is", edit_order_id, student_id)
        chk_st.execute()
        ord_data = chk_st.get_result().fetch_assoc()

        if ord_data and strtolower(nc(ord_data, "order_status", "Pending")) == "pending":
            old_amount = ord_data["total_amount"]

            if not empty(post.get("edit_server_file_path")):
                new_file_path = post["edit_server_file_path"]
                new_file_name = post.get("edit_original_file_name")
            else:
                new_file_path = ord_data["file_path"]
                new_file_name = ord_data["file_name"]

            new_total_pages = intval(nc(post, "edit_hidden_total", ord_data["total_pages"]))
            det_color = intval(nc(post, "edit_hidden_color", ord_data["color_pages"]))
            det_bw = intval(nc(post, "edit_hidden_bw", ord_data["bw_pages"]))

            # No new file chosen -> re-scan the existing file so B&W <-> Color switching always uses real page counts
            if empty(post.get("edit_server_file_path")) and not empty(ord_data["file_path"]) and ord_data["file_path"] != "N/A":
                exist_full = BASE_DIR + "/" + ord_data["file_path"]
                if os.path.isfile(exist_full):
                    rescan = run_page_counter(exist_full)
                    if rescan:
                        new_total_pages = intval(rescan["total"])
                        det_color = intval(rescan["color"])
                        det_bw = intval(rescan["bw"])

            if new_print_mode == "color":
                new_color_pages = det_color
                new_bw_pages = det_bw
            else:
                new_color_pages = 0
                new_bw_pages = new_total_pages

            bw_cost = new_bw_pages * 2
            color_cost = new_color_pages * 5
            pages_cost = bw_cost + color_cost

            cover_cost = 5 if new_cover == "Yes" else 0
            binding_cost = 5 if new_binding == "Tape" else 0

            new_amount = pages_cost + cover_cost + binding_cost
            diff = new_amount - to_number(old_amount)

            up_q = ("UPDATE orders SET file_name = ?, file_path = ?, total_pages = ?, color_pages = ?, bw_pages = ?, cover_page = ?, "
                    "binding_type = ?, print_mode = ?, total_amount = ? WHERE id = ? AND student_id = ?")
            up_st = conn.prepare(up_q)
            up_st.bind_param("sssiisssdii", new_file_name, new_file_path, new_total_pages, new_color_pages, new_bw_pages,
                             new_cover, new_binding, new_print_mode, new_amount, edit_order_id, student_id)

            if up_st.execute():
                if diff != 0:
                    adj_st = conn.prepare("UPDATE students SET due_amount = due_amount + ? WHERE student_id = ?")
                    adj_st.bind_param("ds", diff, student_id)
                    adj_st.execute()

                return php_redirect("dashboard.php?success=order_updated")
            else:
                error = "Failed to update order."
        else:
            error = "Order cannot be edited."

    # ---- Fetch student data & orders
    stmt_student = conn.prepare("SELECT name, due_amount FROM students WHERE student_id = ?")
    stmt_student.bind_param("s", student_id)
    stmt_student.execute()
    student_data = stmt_student.get_result().fetch_assoc()

    student_name = nc(student_data, "name", session.get("name", "Student"))
    total_due = nc(student_data, "due_amount", 0)
    # A negative due means the student paid extra: it is shown as an advance balance and is used on the next order
    is_credit = floatval(total_due) < -0.001
    has_due = floatval(total_due) > 0.001

    stmt_orders = conn.prepare("SELECT * FROM orders WHERE student_id = ? ORDER BY order_date DESC")
    stmt_orders.bind_param("s", student_id)
    stmt_orders.execute()
    orders_result = stmt_orders.get_result()

    # Order statistics for the dashboard hero
    stat_q = conn.prepare("SELECT COUNT(*) AS total, COALESCE(SUM(order_status='Pending'),0) AS pending, "
                          "COALESCE(SUM(order_status='Printing'),0) AS printing, COALESCE(SUM(order_status='Completed'),0) AS completed "
                          "FROM orders WHERE student_id = ?")
    stat_q.bind_param("s", student_id)
    stat_q.execute()
    stats = stat_q.get_result().fetch_assoc()

    return render("dashboard", error=error, success=success, student_name=student_name, total_due=total_due,
                  is_credit=is_credit, has_due=has_due, orders=orders_result.rows, stats=stats)


# ======================================================================== admin_dashboard.php
def pw_kind(p):
    p = php_str(p)
    if p == "":
        return "empty"
    if password_algo(p):
        return "hash"
    if re.search(r"^[a-f0-9]{32}$", p, re.I) or re.search(r"^[a-f0-9]{40}$", p, re.I):
        return "hash"
    return "plain"


def pw_encode_like(sample, new):
    sample = php_str(sample)
    if sample != "":
        if password_algo(sample):
            import bcrypt            # PHP: password_hash($new, PASSWORD_DEFAULT)  (bcrypt, cost 10)
            hashed = bcrypt.hashpw(php_str(new).encode("utf-8")[:72], bcrypt.gensalt(rounds=10, prefix=b"2b")).decode("ascii")
            return "$2y$" + hashed[4:]
        if re.search(r"^[a-f0-9]{32}$", sample, re.I):
            return hashlib.md5(php_str(new).encode("utf-8")).hexdigest()
        if re.search(r"^[a-f0-9]{40}$", sample, re.I):
            return hashlib.sha1(php_str(new).encode("utf-8")).hexdigest()
    return new      # plain text


def col_exists(conn, table, col):
    r = conn.query("SHOW COLUMNS FROM `" + table + "` LIKE '" + conn.real_escape_string(col) + "'")
    return bool(r) and r.num_rows > 0


def q_all(conn, sql):
    res = conn.query(sql)
    return res.fetch_all() if res else []


@app.route("/admin_dashboard.php", methods=METHODS)
def admin_dashboard():
    conn = get_conn()

    # ---------- Access control: only users.role = 'admin' ----------
    if not isset_session("student_id"):
        return php_redirect("login.php")
    admin_sid = session["student_id"]
    role_stmt = conn.prepare("SELECT role, email FROM users WHERE student_id = ?")
    role_stmt.bind_param("s", admin_sid)
    role_stmt.execute()
    admin_row = role_stmt.get_result().fetch_assoc()
    if not admin_row or admin_row["role"] != "admin":
        return php_redirect("dashboard.php")

    if empty(session.get("csrf")):
        session["csrf"] = secrets.token_hex(16)             # bin2hex(random_bytes(16))

    users_has_pw = col_exists(conn, "users", "password")
    stu_has_pw = col_exists(conn, "students", "password")
    if users_has_pw and stu_has_pw:
        pw_expr = "COALESCE(NULLIF(u.password,''), s.password)"
    elif users_has_pw:
        pw_expr = "u.password"
    elif stu_has_pw:
        pw_expr = "s.password"
    else:
        pw_expr = "''"

    admin_name = admin_row["email"]
    nm = conn.prepare("SELECT name FROM students WHERE student_id = ?")
    nm.bind_param("s", admin_sid)
    nm.execute()
    nm_row = nm.get_result().fetch_assoc()
    if nm_row:
        admin_name = nm_row["name"]

    success = ""
    error = ""
    valid_tabs = ["overview", "orders", "students", "registered", "cash", "payments"]
    post = POST()
    get = GET()
    active_tab = nc(post, "tab", nc(get, "tab", "overview"))
    if active_tab not in valid_tabs:
        active_tab = "overview"
    old = {}
    open_add = False

    # ---------- Download an order's PDF (admin can download any file) ----------
    if get.get("action") == "download" and "order_id" in get:
        dl_id = intval(get["order_id"])
        dl = conn.prepare("SELECT file_path, file_name FROM orders WHERE id = ?")
        dl.bind_param("i", dl_id)
        dl.execute()
        dl_res = dl.get_result().fetch_assoc()
        if dl_res and not empty(dl_res["file_path"]) and dl_res["file_path"] != "N/A":
            file_path = BASE_DIR + "/" + dl_res["file_path"]
            if os.path.exists(file_path):
                return download_response(file_path, dl_res["file_name"], False)
        error = "File not found on server."

    # ---------- Flash messages ----------
    flash = {
        "status_updated": "Order status updated!",
        "student_added": "Student added successfully!",
        "student_updated": "Student information updated!",
        "payment_received": "Cash received! Due updated (any extra is saved as advance).",
        "password_changed": "Password changed successfully!",
        "role_changed": "Account role updated!",
    }
    if "success" in get and get["success"] in flash:
        success = flash[get["success"]]

    # ---------- POST actions ----------
    if request.method == "POST":
        csrf_ok = False
        if "csrf" in post and isinstance(post["csrf"], str):
            csrf_ok = hmac.compare_digest(php_str(session["csrf"]).encode("utf-8"), post["csrf"].encode("utf-8"))
        if not csrf_ok:
            error = "Session expired. Please reload the page and try again."
        else:
            ft = nc(post, "form_type", "")

            # Change order status
            if ft == "update_status":
                oid = intval(nc(post, "order_id", 0))
                st = nc(post, "status", "")
                if st in ["Pending", "Completed"]:
                    u = conn.prepare("UPDATE orders SET order_status = ? WHERE id = ?")
                    u.bind_param("si", st, oid)
                    if u.execute():
                        return php_redirect("admin_dashboard.php?tab=orders&success=status_updated")
                error = "Could not update the order status."

            # Add a new student (university record only - the student registers & sets password/gmail later)
            elif ft == "add_student":
                old = dict(post)
                name = trim(nc(post, "name", ""))
                sid = trim(nc(post, "student_id", ""))
                dept = trim(nc(post, "department", ""))
                sec = trim(nc(post, "section", ""))

                if name == "" or sid == "" or dept == "" or sec == "":
                    error = "Please fill in all fields."
                elif not ctype_digit(sid) or strlen(sid) < 4 or strlen(sid) > 11:
                    error = "Student ID must be 4 to 11 digits (login uses the last 4 digits)."
                else:
                    c = conn.prepare("SELECT id FROM students WHERE student_id = ?")
                    c.bind_param("s", sid)
                    c.execute()
                    c.store_result()
                    if c.num_rows > 0:
                        error = "A student with this Student ID already exists!"
                    else:
                        # phone / password / email are filled in later (email comes from the registration)
                        ins = conn.prepare("INSERT INTO students (name, student_id, department, section, phone, password, email, due_amount) "
                                           "VALUES (?, ?, ?, ?, '', '', '', 0)")
                        ins.bind_param("ssss", name, sid, dept, sec)
                        if ins.execute():
                            return php_redirect("admin_dashboard.php?tab=students&success=student_added")
                        else:
                            error = "Failed to add the student. Please try again."
                active_tab = "students"
                open_add = True

            # Edit student information (name, department, section)
            elif ft == "edit_student":
                sid = trim(nc(post, "student_id", ""))
                name = trim(nc(post, "name", ""))
                dept = trim(nc(post, "department", ""))
                sec = trim(nc(post, "section", ""))
                if name == "" or sid == "":
                    error = "Student name is required."
                else:
                    u = conn.prepare("UPDATE students SET name = ?, department = ?, section = ? WHERE student_id = ?")
                    u.bind_param("ssss", name, dept, sec, sid)
                    if u.execute():
                        return php_redirect("admin_dashboard.php?tab=students&success=student_updated")
                    error = "Failed to update the student."
                active_tab = "students"

            # Receive a payment from a student (reduces due)
            elif ft == "receive_payment":
                sid = trim(nc(post, "student_id", ""))
                amount = php_round(floatval(nc(post, "amount", 0)), 2)
                method = "bKash" if nc(post, "method", "Cash") == "bKash" else "Cash"
                trx = trim(nc(post, "trx_id", ""))
                trx = trx if (method == "bKash" and trx != "") else None

                s = conn.prepare("SELECT due_amount FROM students WHERE student_id = ?")
                s.bind_param("s", sid)
                s.execute()
                stu = s.get_result().fetch_assoc()

                if not stu:
                    error = "Student not found."
                elif amount <= 0:
                    error = "Please enter a valid amount."
                else:
                    # If the student pays more than the due, the extra stays in the database as an advance
                    # (a negative due). It is used automatically by the student's next order.
                    remaining = php_round(floatval(stu["due_amount"]) - amount, 2)
                    pstatus = "Paid" if remaining <= 0.001 else "Partial"
                    conn.begin_transaction()
                    try:
                        p = conn.prepare("INSERT INTO payments (student_id, paid_amount, payment_method, trx_id, payment_status) VALUES (?, ?, ?, ?, ?)")
                        p.bind_param("sdsss", sid, amount, method, trx, pstatus)
                        p.execute_or_raise()
                        d = conn.prepare("UPDATE students SET due_amount = ? WHERE student_id = ?")
                        d.bind_param("ds", remaining, sid)
                        d.execute_or_raise()
                        conn.commit()
                        return php_redirect("admin_dashboard.php?tab=cash&success=payment_received")
                    except Exception:
                        conn.rollback()
                        error = "Could not record the payment."
                active_tab = "cash"

            # Change the role of a registered account (student <-> admin)
            elif ft == "change_role":
                sid = trim(nc(post, "student_id", ""))
                new_role = nc(post, "role", "")
                active_tab = "registered"
                if new_role not in ("student", "admin") or not isinstance(new_role, str):
                    error = "Invalid role."
                elif sid == php_str(admin_sid):
                    error = "You cannot change your own role."
                else:
                    ur = conn.prepare("UPDATE users SET role = ? WHERE student_id = ?")
                    ur.bind_param("ss", new_role, sid)
                    if ur.execute():
                        return php_redirect("admin_dashboard.php?tab=registered&success=role_changed")
                    error = "Could not change the role."

            # Change a registered student's password
            elif ft == "change_password":
                sid = trim(nc(post, "student_id", ""))
                newpw = php_str(nc(post, "new_password", ""))
                active_tab = "registered"
                chk = conn.prepare("SELECT id FROM users WHERE student_id = ?")
                chk.bind_param("s", sid)
                chk.execute()
                chk.store_result()
                if chk.num_rows == 0:
                    error = "This student has not registered yet."
                elif strlen(newpw) < 4:
                    error = "Password must be at least 4 characters."
                elif not users_has_pw and not stu_has_pw:
                    error = "No password column found in the database."
                else:
                    # use the same storage style as the existing passwords (plain / md5 / sha1 / hash)
                    sample = ""
                    g_ = conn.prepare("SELECT " + pw_expr + " AS pw FROM students s LEFT JOIN users u ON u.student_id = s.student_id WHERE s.student_id = ?")
                    g_.bind_param("s", sid)
                    g_.execute()
                    gr = g_.get_result().fetch_assoc()
                    sample = php_str(nc(gr, "pw", ""))
                    if sample == "":
                        any_ = conn.query("SELECT " + pw_expr + " AS pw FROM students s LEFT JOIN users u ON u.student_id = s.student_id "
                                          "WHERE (" + pw_expr + ") IS NOT NULL AND (" + pw_expr + ") <> '' LIMIT 1")
                        if any_:
                            ar = any_.fetch_assoc()
                            if ar:
                                sample = php_str(ar["pw"])
                    enc = pw_encode_like(sample, newpw)
                    conn.begin_transaction()
                    try:
                        if users_has_pw:
                            u1 = conn.prepare("UPDATE users SET password = ? WHERE student_id = ?")
                            u1.bind_param("ss", enc, sid)
                            u1.execute_or_raise()
                        if stu_has_pw:
                            u2 = conn.prepare("UPDATE students SET password = ? WHERE student_id = ?")
                            u2.bind_param("ss", enc, sid)
                            u2.execute_or_raise()
                        conn.commit()
                        return php_redirect("admin_dashboard.php?tab=registered&success=password_changed")
                    except Exception:
                        conn.rollback()
                        error = "Could not change the password."

    # ---------- Load data ----------
    students = q_all(conn, "SELECT s.*, u.role AS user_role, u.email AS user_email, (u.id IS NOT NULL) AS registered, "
                           + pw_expr + " AS reg_password, COALESCE(o.cnt,0) AS order_count, COALESCE(o.amt,0) AS order_total\n"
                           "    FROM students s\n"
                           "    LEFT JOIN users u ON u.student_id = s.student_id\n"
                           "    LEFT JOIN (SELECT student_id, COUNT(*) AS cnt, SUM(total_amount) AS amt FROM orders GROUP BY student_id) o ON o.student_id = s.student_id\n"
                           "    ORDER BY s.name ASC")
    orders = q_all(conn, "SELECT o.*, s.name AS student_name FROM orders o LEFT JOIN students s ON s.student_id = o.student_id ORDER BY o.order_date DESC")
    payments = q_all(conn, "SELECT p.*, s.name AS student_name FROM payments p LEFT JOIN students s ON s.student_id = p.student_id ORDER BY p.payment_date DESC")
    user_counts = q_all(conn, "SELECT SUM(role='student') AS students_reg, SUM(role='admin') AS admins FROM users")
    user_counts = user_counts[0] if user_counts else {"students_reg": 0, "admins": 0}

    stats = {"students": len(students), "registered": intval(user_counts["students_reg"]), "admins": intval(user_counts["admins"]),
             "orders": len(orders), "Pending": 0, "Completed": 0,
             "due": 0.0, "collected": 0.0, "revenue": 0.0, "due_students": 0, "credit": 0.0, "credit_students": 0}
    modes = {"bw": 0, "color": 0, "a4": 0, "cover": 0}
    for o in orders:
        norm = "Completed" if nc(o, "order_status", "") == "Completed" else "Pending"   # only Pending / Completed are used
        stats[norm] += 1
        stats["revenue"] += floatval(o["total_amount"])
        m = nc(o, "print_mode", "bw")
        modes[m] = nc(modes, m, 0) + 1
    for s in students:
        dv = floatval(s["due_amount"])
        if dv > 0:
            stats["due"] += dv
            stats["due_students"] += 1
        elif dv < 0:
            stats["credit"] += -dv
            stats["credit_students"] += 1
    for p in payments:
        stats["collected"] += floatval(p["paid_amount"])

    top_due = sorted(students, key=lambda s_: floatval(s_["due_amount"]), reverse=True)   # usort(... <=>) is stable in PHP 8
    top_due = [s_ for s_ in top_due[:5] if floatval(s_["due_amount"]) > 0]
    maxdue = max(floatval(s_["due_amount"]) for s_ in top_due) if top_due else 0

    reg_count = len([s_ for s_ in students if not empty(s_.get("registered"))])
    payload = {"students": [], "orders": [], "payments": []}
    for s in students:
        kind = pw_kind(nc(s, "reg_password", ""))
        payload["students"].append({
            "id": intval(s["id"]), "name": s["name"], "student_id": s["student_id"], "department": s["department"], "section": s["section"],
            "email": php_str(nc(s, "user_email", "")), "due": floatval(s["due_amount"]), "registered": intval(s["registered"]),
            "role": s["user_role"], "order_count": intval(s["order_count"]), "order_total": floatval(s["order_total"]),
            "created_at": s.get("created_at"),
            "pw_kind": kind, "password": php_str(s["reg_password"]) if kind == "plain" else "",
        })
    for o in orders:
        payload["orders"].append({
            "id": intval(o["id"]), "student_id": o["student_id"], "student_name": o["student_name"], "file_name": o["file_name"],
            "file_path": o["file_path"], "total_pages": intval(o["total_pages"]), "color_pages": intval(o["color_pages"]),
            "bw_pages": intval(o["bw_pages"]), "cover_page": o["cover_page"], "binding_type": o["binding_type"],
            "print_mode": o["print_mode"], "amount": floatval(o["total_amount"]),
            "status": "Completed" if nc(o, "order_status", "") == "Completed" else "Pending", "date": o["order_date"],
        })
    for p in payments:
        payload["payments"].append({
            "id": intval(p["id"]), "student_id": p["student_id"], "student_name": p["student_name"], "amount": floatval(p["paid_amount"]),
            "method": p["payment_method"], "trx": p["trx_id"], "status": p["payment_status"], "date": p["payment_date"],
        })

    mode_rows = [("bw", ["Black & White", "bg-slate-500"]), ("color", ["Color Print", "bg-fuchsia-400"]),
                 ("a4", ["A4 Pages", "bg-sky-400"]), ("cover", ["Cover Pages", "bg-violet-400"])]

    return render("admin_dashboard", admin_name=admin_name, admin_sid=admin_sid, success=success, error=error,
                  stats=stats, payments=payments, reg_count=reg_count, modes=modes, mode_rows=mode_rows,
                  top_due=top_due, maxdue=maxdue, csrf=session["csrf"], old=old, payload=payload,
                  active_tab=active_tab, open_add=open_add)


# ======================================================================== run
if __name__ == "__main__":
    # http://localhost:5000/login.php
    app.run(host="127.0.0.1", port=5000, debug=False)
