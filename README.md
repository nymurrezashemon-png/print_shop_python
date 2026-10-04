# Print Shop - Python (Flask) version

PHP project-ti Python e convert kora hoyeche. URL gulo **hubohu ager moton** (`login.php`, `dashboard.php`, ...),
tai HTML er bhitorer href / form action / fetch('') kono change charai kaj kore.

## Run
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000/login.php

* Ager moton MySQL database `print_shop_db` (user `root`, password empty) - `db.py` te same credentials ache.
* Tomar ager `count_pages.py` ta **ei folder e** (app.py r pashe) rakho. (Seta upload kora hoyni, tai ami chuini.)
* `analyze.php` e original e hard-coded Windows python path chilo (`C:\Users\nymur\...\python.exe`), seta ager moton-i ache.
  `dashboard.php` e `python` command use hoy - ager moton.
* Session secret: `SECRET_KEY` environment variable, na thakle `.secret_key` file auto toiri hoy.

## File map
| PHP | Python |
|---|---|
| db.php | db.py |
| index, login, register, forgot-password, verify-code, logout, dashboard, admin_dashboard, admin, pay, analyze (.php) | app.py (ekta route = ekta PHP file, same URL) |
| HTML/CSS/JS part of each page | templates/*.html (byte-for-byte same, shudhu `<?php ?>` tag gulo template tag hoyeche) |
| PHP built-ins (trim, empty, intval, number_format, round, json_encode, htmlspecialchars ...) | php_compat.py |

## Tests
    python tests/test_app.py     # fake DB diye 193 ta check (MySQL lagbe na)
