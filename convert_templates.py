"""
Converts the HTML part of each PHP page into a template.
 - Everything that is plain HTML / CSS / JS is copied byte-for-byte.
 - Every  <?php ... ?>  block is replaced by an equivalent template tag
   (custom delimiters  <%= ... =%>  and  <%PY ... PY%>  so that no `{{` / `{%`
   inside the JS/CSS can ever clash).
 - PHP swallows ONE newline directly after  ?>  - we do the same.
The mapping is exact-match: if a PHP snippet is not in the table the script stops.
"""
import re
import sys
import os

SRC = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)


def V(expr):   # output tag
    return "<%= " + expr + " =%>"


def B(code):   # block tag
    return "<%PY " + code + " PY%>"


ERR = "not empty(error)"
SUC = "not empty(success)"

M = {}


def m(php, out):
    M[" ".join(php.split())] = out


# ---------------------------------------------------------- shared (login-style popup pages + dashboard)
m("echo (!empty($error) || !empty($success)) ? 'show' : '';", V(f"'show' if ({ERR} or {SUC}) else ''"))
m("echo !empty($error) ? 'error-badge' : '';", V(f"'error-badge' if {ERR} else ''"))
m("echo !empty($error) ? '✕' : '✓';", V(f"'✕' if {ERR} else '✓'"))
m("echo !empty($error) ? 'Oops!' : 'Success!';", V(f"'Oops!' if {ERR} else 'Success!'"))
m("echo !empty($error) ? $error : (!empty($success) ? $success : '');",
  V(f"e(error if {ERR} else (success if {SUC} else ''))"))
m("echo $redirect ? 'happy' : (!empty($error) ? 'sad' : '');", V(f"'happy' if redirect else ('sad' if {ERR} else '')"))
m("if ($redirect):", B("if redirect"))
m("echo $redirect_url;", V("e(redirect_url)"))
m("endif;", B("endif"))
m("if (!empty($error)):", B(f"if {ERR}"))
m("else:", B("else"))
m("endwhile;", B("endfor"))
m("endforeach;", B("endfor"))
m("endforeach; endif;", B("endfor") + B("endif"))

# ---------------------------------------------------------- dashboard.php
m("echo htmlspecialchars($student_name);", V("h(student_name)"))
m("echo ($total_due > 0) ? 'border-rose-500' : 'border-emerald-500';", V("'border-rose-500' if gt_zero(total_due) else 'border-emerald-500'"))
m("echo $is_credit ? 'Advance Balance' : 'Payment';", V("'Advance Balance' if is_credit else 'Payment'"))
m("echo $has_due ? 'text-rose-600' : 'text-emerald-600';", V("'text-rose-600' if has_due else 'text-emerald-600'"))
m("echo number_format(abs($total_due), 2);", V("number_format(php_abs(total_due), 2)"))
m("echo $has_due ? 'text-slate-500' : 'text-emerald-600 font-semibold';", V("'text-slate-500' if has_due else 'text-emerald-600 font-semibold'"))
m("echo $has_due ? 'Clear your current due amount' : ($is_credit ? 'Extra paid. It will be used on your next order.' : 'No due. You are all clear!');",
  V("'Clear your current due amount' if has_due else ('Extra paid. It will be used on your next order.' if is_credit else 'No due. You are all clear!')"))
m("if ($has_due):", B("if has_due"))
m("if($orders_result->num_rows > 0):", B("if orders|length > 0"))
m("while($order = $orders_result->fetch_assoc()):", B("for order in orders"))
m("echo htmlspecialchars($order['file_name']);", V("h(order['file_name'])"))
m("if (($order['print_mode'] ?? '') !== 'cover'): $pm = $order['print_mode'] ?? 'bw';",
  B("if nc(order, 'print_mode', '') != 'cover'") + B("set pm = nc(order, 'print_mode', 'bw')"))
m("echo $pm === 'color' ? 'bg-fuchsia-100 text-fuchsia-700' : 'bg-slate-200 text-slate-700';", V("'bg-fuchsia-100 text-fuchsia-700' if pm == 'color' else 'bg-slate-200 text-slate-700'"))
m("echo $pm === 'color' ? 'Color' : 'B&amp;W';", V("'Color' if pm == 'color' else 'B&amp;W'"))
m("if (($order['print_mode'] ?? '') !== 'cover'): $has_cv = (($order['cover_page'] ?? '') === 'Yes');",
  B("if nc(order, 'print_mode', '') != 'cover'") + B("set has_cv = (nc(order, 'cover_page', '') == 'Yes')"))
m("echo $has_cv ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-500';", V("'bg-violet-100 text-violet-700' if has_cv else 'bg-slate-100 text-slate-500'"))
m("echo $has_cv ? 'Yes' : 'No';", V("'Yes' if has_cv else 'No'"))
m("echo $bt_cls;", V("e(bt_cls)"))
m("echo $bt_txt;", V("e(bt_txt)"))
m("$st_l = strtolower($order['order_status'] ?? 'Pending'); echo $st_l == 'completed' ? 'bg-emerald-100 text-emerald-800' : ($st_l == 'printing' ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800');",
  B("set st_l = strtolower(nc(order, 'order_status', 'Pending'))") +
  V("'bg-emerald-100 text-emerald-800' if st_l == 'completed' else ('bg-sky-100 text-sky-800' if st_l == 'printing' else 'bg-amber-100 text-amber-800')"))
m("echo htmlspecialchars($order['order_status'] ?? 'Pending');", V("h(nc(order, 'order_status', 'Pending'))"))
m("echo json_encode($order);", V("json_encode(order)"))
m("if(!empty($order['file_path']) && $order['file_path'] != 'N/A'):", B("if not empty(order['file_path']) and order['file_path'] != 'N/A'"))
m("echo $order['id'];", V("e(order['id'])"))
m("if(strtolower($order['order_status'] ?? 'Pending') == 'pending'):", B("if strtolower(nc(order, 'order_status', 'Pending')) == 'pending'"))
m("echo number_format(max(0, floatval($total_due)), 2);", V("number_format(php_max(0, floatval(total_due)), 2)"))
m("echo (!empty($success) || !empty($error)) ? 'true' : 'false';", V(f"'true' if ({SUC} or {ERR}) else 'false'"))

# ---------------------------------------------------------- admin_dashboard.php
m("echo h($admin_name);", V("h(admin_name)"))
m("if ($success || $error):", B(f"if {SUC} or {ERR}"))
m("echo $error ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200';",
  V(f"'bg-rose-50 text-rose-700 border border-rose-200' if {ERR} else 'bg-emerald-50 text-emerald-700 border border-emerald-200'"))
m("echo $error ? 'bg-rose-500' : 'bg-emerald-500';", V(f"'bg-rose-500' if {ERR} else 'bg-emerald-500'"))
m("echo $error ? '&#10005;' : '&#10003;';", V(f"'&#10005;' if {ERR} else '&#10003;'"))
m("echo h($error ?: $success);", V(f"h(error if {ERR} else success)"))
m("echo $stats['orders'];", V("e(stats['orders'])"))
m("echo $stats['students'];", V("e(stats['students'])"))
m("echo $reg_count;", V("e(reg_count)"))
m("echo count($payments);", V("e(php_count(payments))"))
m("echo number_format($stats['due'], 2, '.', '');", V("number_format(stats['due'], 2, '.', '')"))
m("echo number_format($stats['due'], 2);", V("number_format(stats['due'], 2)"))
m("echo $stats['due_students'];", V("e(stats['due_students'])"))
m("if ($stats['credit'] > 0):", B("if stats['credit'] > 0"))
m("echo number_format($stats['credit'], 2);", V("number_format(stats['credit'], 2)"))
m("echo number_format($stats['collected'], 2, '.', '');", V("number_format(stats['collected'], 2, '.', '')"))
m("echo number_format($stats['collected'], 2);", V("number_format(stats['collected'], 2)"))
m("echo number_format($stats['revenue'], 2, '.', '');", V("number_format(stats['revenue'], 2, '.', '')"))
m("echo number_format($stats['revenue'], 2);", V("number_format(stats['revenue'], 2)"))
m("echo $stats['Pending'];", V("e(stats['Pending'])"))
m("echo $stats['Completed'];", V("e(stats['Completed'])"))
m("$ot = max(1, $stats['orders']);", B("set ot = php_max(1, stats['orders'])"))
m("echo round($stats['Pending'] / $ot * 100, 1);", V("e(php_round(stats['Pending'] / ot * 100, 1))"))
m("echo round($stats['Completed'] / $ot * 100, 1);", V("e(php_round(stats['Completed'] / ot * 100, 1))"))
m("foreach (['bw' => ['Black & White', 'bg-slate-500'], 'color' => ['Color Print', 'bg-fuchsia-400'], 'a4' => ['A4 Pages', 'bg-sky-400'], 'cover' => ['Cover Pages', 'bg-violet-400']] as $mk => $mv):",
  B("for mk, mv in mode_rows"))
m("echo $mv[0];", V("e(mv[0])"))
m("echo $modes[$mk] ?? 0;", V("e(nc(modes, mk, 0))"))
m("echo $mv[1];", V("e(mv[1])"))
m("echo round(($modes[$mk] ?? 0) / $ot * 100, 1);", V("e(php_round(nc(modes, mk, 0) / ot * 100, 1))"))
m("if (empty($top_due)):", B("if empty(top_due)"))
# `$maxdue = max(array_map(... floatval($s['due_amount']) ..., $top_due))` is computed in app.py (maxdue)
m("else: $maxdue = max(array_map(function ($s) { return floatval($s['due_amount']); }, $top_due)); foreach ($top_due as $s):",
  B("else") + B("for s in top_due"))
m("echo h($s['student_id']);", V("h(s['student_id'])"))
m("echo h($s['name']);", V("h(s['name'])"))
m("echo h($s['department']);", V("h(s['department'])"))
m("echo number_format($s['due_amount'], 2);", V("number_format(s['due_amount'], 2)"))
m("echo round(floatval($s['due_amount']) / $maxdue * 100);", V("e(php_round(floatval(s['due_amount']) / maxdue * 100))"))
m("echo $_SESSION['csrf'];", V("e(csrf)"))
m("echo h($old['name'] ?? '');", V("h(nc(old, 'name', ''))"))
m("echo h($old['student_id'] ?? '');", V("h(nc(old, 'student_id', ''))"))
m("echo h($old['department'] ?? '');", V("h(nc(old, 'department', ''))"))
m("echo h($old['section'] ?? '');", V("h(nc(old, 'section', ''))"))
m("echo json_encode($payload, $JSON_FLAGS);", V("json_encode_flags(payload)"))
m("echo h($admin_sid);", V("h(admin_sid)"))
m("echo $active_tab;", V("e(active_tab)"))
m("if ($open_add):", B("if open_add"))

# ---------------------------------------------------------- logout.php / pay.php
m("echo $success;", V("e(success)"))
m("if($success):", B(f"if {SUC}"))
m("if($error):", B(f"if {ERR}"))
m("echo $error;", V("e(error)"))
m("while($row = $orders->fetch_assoc()):", B("for row in orders"))
m("echo $row['id'];", V("e(row['id'])"))
m("echo $row['file_name'];", V("e(row['file_name'])"))
m("echo $row['due_amount'];", V("e(row['due_amount'])"))

# ---------------------------------------------------------- admin.php
m("while($row = $orders_result->fetch_assoc()):", B("for row in orders"))
m("echo htmlspecialchars($row['name']);", V("h(row['name'])"))
m("echo htmlspecialchars($row['std_unique_id']);", V("h(row['std_unique_id'])"))
m("echo htmlspecialchars($row['department']);", V("h(row['department'])"))
m("echo htmlspecialchars($row['phone']);", V("h(row['phone'])"))
m("echo $row['file_path'];", V("e(row['file_path'])"))
m("echo htmlspecialchars($row['file_name']);", V("h(row['file_name'])"))
for col in ("cover_page", "binding_type", "total_pages", "color_pages", "bw_pages", "total_amount",
            "paid_amount", "payment_method", "trx_id"):
    m("echo $row['%s'];" % col, V("e(row['%s'])" % col))
m("if($row['trx_id']):", B("if not empty(row['trx_id'])"))
for col, val in (("order_status", "Pending"), ("order_status", "Printing"), ("order_status", "Completed"),
                 ("payment_status", "Unpaid"), ("payment_status", "Partial"), ("payment_status", "Paid")):
    m("if($row['%s']=='%s') echo 'selected';" % (col, val), V("'selected' if row['%s'] == '%s' else ''" % (col, val)))

# ---------------------------------------------------------- the multi-line "row_a4" block in dashboard.php
ROW_A4_PREFIX = "$row_a4 = ("
ROW_A4_OUT = (
    B("set row_a4 = (nc(order, 'print_mode', '') != 'cover' and (nc(order, 'print_mode', '') == 'a4' or nc(order, 'file_path', '') == 'N/A'))")
    + B("set row_bt = nc(order, 'binding_type', '')")
    + B("if not row_a4")
    + B("if row_bt == 'Tape'")
    + B("set bt_txt = 'Tape binding: Yes'") + B("set bt_cls = 'bg-sky-100 text-sky-700'")
    + B("else")
    + B("set bt_txt = 'Tape binding: No'") + B("set bt_cls = 'bg-slate-100 text-slate-500'")
    + B("endif")
)
ROW_A4_EXPECTED = (
    "$row_a4 = (($order['print_mode'] ?? '') !== 'cover' && (($order['print_mode'] ?? '') === 'a4' || ($order['file_path'] ?? '') === 'N/A')); "
    "$row_bt = $order['binding_type'] ?? ''; if (!$row_a4): "
    "if ($row_bt === 'Tape') { $bt_txt = 'Tape binding: Yes'; $bt_cls = 'bg-sky-100 text-sky-700'; } "
    "else { $bt_txt = 'Tape binding: No'; $bt_cls = 'bg-slate-100 text-slate-500'; }"
)

PAGES = ["login", "register", "forgot-password", "verify-code", "dashboard", "admin_dashboard", "logout", "pay", "admin"]
used = set()
total_tags = 0
for name in PAGES:
    with open(os.path.join(SRC, name + ".php"), encoding="utf-8", newline="") as f:
        txt = f.read()
    head_end = txt.index("?>") + 2
    if txt[head_end:head_end + 2] == "\r\n":          # PHP swallows the newline after ?>
        head_end += 2
    body = txt[head_end:]

    def repl(mo):
        global total_tags
        snippet = " ".join(mo.group(1).split())
        if snippet.startswith(ROW_A4_PREFIX):
            if snippet != ROW_A4_EXPECTED:
                sys.exit("UNEXPECTED row_a4 block in %s:\n%s" % (name, snippet))
            out = ROW_A4_OUT
            used.add("ROW_A4")
        else:
            if snippet not in M:
                sys.exit("UNMAPPED PHP snippet in %s.php: %r" % (name, snippet))
            out = M[snippet]
            used.add(snippet)
        total_tags += 1
        return out

    # a PHP close tag eats exactly one following newline
    new_body = re.sub(r"<\?php(.*?)\?>(\r\n|\n)?", repl, body, flags=re.S)
    if "<?" in new_body or "?>" in new_body.replace("PY%>", "").replace("=%>", ""):
        sys.exit("leftover PHP tag in " + name)
    with open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8", newline="") as f:
        f.write(new_body)
    print("converted %-18s -> %s.html" % (name + ".php", name))

unused = [k for k in M if k not in used]
print("\nPHP tags converted:", total_tags)
print("mapping entries unused (harmless):", len(unused))
for k in unused:
    print("   ", k[:100])
