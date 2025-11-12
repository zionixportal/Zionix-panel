# app.py
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, g, Response
import sqlite3, requests, json, os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
# change this to a stable secret in production
app.secret_key = "change_this_to_a_random_string_please"

import tempfile
DB = tempfile.gettempdir() + "/proxy_panel.db"
ADMIN_SECRET = "yuwer@3PxZ"   # single secret key (change if you want)
ADMIN_SESSION_KEY = "is_admin"

# ---------------- DB helpers ----------------
def get_db():
    if '_db' not in g:
        g._db = sqlite3.connect(DB)
        g._db.row_factory = sqlite3.Row
    return g._db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('_db', None)
    if db:
        db.close()

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS apis (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE,
      url_template TEXT,
      api_key TEXT,
      key_location TEXT DEFAULT 'query', -- query/header/cookie
      cookie_name TEXT DEFAULT 'x_api_key',
      active INTEGER DEFAULT 1,
      strip_fields TEXT DEFAULT '',
      add_fields TEXT DEFAULT '',
      owner_credit TEXT DEFAULT '',
      created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      client_ip TEXT,
      api_id INTEGER,
      apitype TEXT,
      term TEXT,
      status_code INTEGER,
      created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    )""")
    # default global settings (optional)
    c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", ("GLOBAL_EXPIRE_AT","2099-01-01T00:00:00"))
    db.commit()

with app.app_context():
    init_db()

# ---------------- helpers ----------------
def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if session.get(ADMIN_SESSION_KEY):
            return f(*a, **kw)
        # allow header-based admin secret too
        token = request.headers.get("X-ADMIN-SECRET") or request.args.get("admin_secret")
        if token and token == ADMIN_SECRET:
            session[ADMIN_SESSION_KEY] = True
            return f(*a, **kw)
        return redirect(url_for('login', next=request.path))
    return wrap

def log_request(client_ip, api_id, apitype, term, status_code):
    db = get_db()
    db.execute("INSERT INTO logs (client_ip, api_id, apitype, term, status_code, created_at) VALUES (?,?,?,?,?,?)",
               (client_ip, api_id, apitype, term, status_code, datetime.utcnow().isoformat()))
    db.commit()

def clean_json_recursive(obj, strip_keys):
    # remove keys (case sensitive) at any depth in dicts
    if isinstance(obj, dict):
        return {k: clean_json_recursive(v, strip_keys) for k,v in obj.items() if k not in strip_keys}
    if isinstance(obj, list):
        return [clean_json_recursive(x, strip_keys) for x in obj]
    return obj

# ---------------- Public proxy ----------------
@app.route("/api", methods=["GET","POST"])
def proxy():
    apiname = request.args.get("type") or request.args.get("name")
    term = request.args.get("term","")
    if not apiname:
        return jsonify({"success": False, "error": "missing type/name parameter"}), 400

    db = get_db()
    c = db.cursor()
    c.execute("SELECT * FROM apis WHERE name=? COLLATE NOCASE", (apiname,))
    row = c.fetchone()
    if not row:
        return jsonify({"success": False, "error": f"Unknown API type '{apiname}'"}), 404

    if not row["active"]:
        return jsonify({"success": False, "error": "This API is disabled"}), 403

    # Validate per-proxy key if set
    expected_key = row["api_key"]
    key_location = row["key_location"] or "query"
    provided_key = None
    if key_location == "query":
        provided_key = request.args.get("key")
    elif key_location == "header":
        provided_key = request.headers.get("X-API-KEY")
    elif key_location == "cookie":
        provided_key = request.cookies.get(row["cookie_name"] or "x_api_key")
    # if proxy has a key, require it
    if expected_key:
        if not provided_key or provided_key != expected_key:
            return jsonify({"success": False, "error": "Invalid or missing proxy API key"}), 401

    # build target URL
    target = (row["url_template"] or "").replace("{term}", term)

    try:
        if request.method == "POST":
            upstream = requests.post(target, json=request.get_json(silent=True), timeout=10)
        else:
            upstream = requests.get(target, timeout=10)
    except requests.RequestException:
        log_request(request.remote_addr, row["id"], apiname, term, 502)
        return jsonify({"success": False, "error": "Upstream request failed"}), 502

    status = upstream.status_code
    log_request(request.remote_addr, row["id"], apiname, term, status)

    # if JSON response: clean and add fields
    content_type = upstream.headers.get("content-type","")
    if "application/json" in content_type:
        try:
            data = upstream.json()
        except Exception:
            return Response(upstream.text, status=status, content_type=content_type)
        # apply strip keys (comma separated)
        strip_fields = [s.strip() for s in (row["strip_fields"] or "").split(",") if s.strip()]
        data = clean_json_recursive(data, strip_fields)
        # add custom fields (add_fields stored as JSON string)
        if row["add_fields"]:
            try:
                extra = json.loads(row["add_fields"])
                if isinstance(data, dict):
                    data.update(extra)
            except Exception:
                pass
        # note: owner_credit is stored but not auto-injected unless added via add_fields (keeps it private)
        return jsonify(data), status

    # non-json pass-through
    return Response(upstream.content, status=status, content_type=upstream.headers.get("content-type","text/plain"))

# ---------------- Admin UI & API ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        secret = request.form.get("secret") or request.json.get("secret")
        if secret == ADMIN_SECRET:
            session[ADMIN_SESSION_KEY] = True
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        return render_template("login.html", error="Invalid secret")
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.pop(ADMIN_SESSION_KEY, None)
    return redirect(url_for("login"))

@app.route("/dashboard")
@admin_required
def dashboard():
    db = get_db()
    c = db.cursor()
    c.execute("SELECT COUNT(*) FROM apis")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM apis WHERE active=1")
    active = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM apis WHERE active=0")
    inactive = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM logs")
    total_requests = c.fetchone()[0]
    # fetch first 100 apis for server-side rendering fallback
    c.execute("SELECT id,name,active,api_key,key_location,cookie_name,strip_fields,add_fields,owner_credit,created_at,url_template FROM apis ORDER BY id DESC")
    apis = c.fetchall()
    return render_template("dashboard.html", total=total, active=active, inactive=inactive, total_requests=total_requests, apis=apis)

# JSON admin endpoints used by panel.js
@app.route("/admin/list_apis")
@admin_required
def admin_list_apis():
    c = get_db().cursor()
    c.execute("SELECT id,name,active,api_key,key_location,cookie_name,strip_fields,add_fields,owner_credit,created_at,url_template FROM apis ORDER BY id DESC")
    rows = [dict(r) for r in c.fetchall()]
    return jsonify(rows)

@app.route("/admin/add_api", methods=["POST"])
@admin_required
def admin_add_api():
    d = request.get_json()
    name = d.get("name","").strip().lower()
    tpl = d.get("url_template","").strip()
    api_key = d.get("api_key","").strip()
    key_location = d.get("key_location","query")
    cookie_name = d.get("cookie_name","x_api_key")
    strip_fields = d.get("strip_fields","").strip()
    add_fields = d.get("add_fields","").strip()
    owner_credit = d.get("owner_credit","").strip()
    if not name or not tpl:
        return jsonify({"success": False, "error": "name and url_template required"}), 400
    db = get_db()
    try:
        db.execute("""INSERT INTO apis (name,url_template,api_key,key_location,cookie_name,strip_fields,add_fields,owner_credit,created_at)
                      VALUES (?,?,?,?,?,?,?,?,?)""",
                   (name, tpl, api_key, key_location, cookie_name, strip_fields, add_fields, owner_credit, datetime.utcnow().isoformat()))
        db.commit()
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "API name exists"}), 400

@app.route("/admin/update_api/<int:api_id>", methods=["POST"])
@admin_required
def admin_update_api(api_id):
    d = request.get_json()
    tpl = d.get("url_template","").strip()
    api_key = d.get("api_key","").strip()
    key_location = d.get("key_location","query")
    cookie_name = d.get("cookie_name","x_api_key")
    active = 1 if d.get("active") else 0
    strip_fields = d.get("strip_fields","").strip()
    add_fields = d.get("add_fields","").strip()
    owner_credit = d.get("owner_credit","").strip()
    db = get_db()
    db.execute("""UPDATE apis SET url_template=?, api_key=?, key_location=?, cookie_name=?, active=?, strip_fields=?, add_fields=?, owner_credit=? WHERE id=?""",
               (tpl, api_key, key_location, cookie_name, active, strip_fields, add_fields, owner_credit, api_id))
    db.commit()
    return jsonify({"success": True})

@app.route("/admin/delete_api/<int:api_id>", methods=["POST"])
@admin_required
def admin_delete_api(api_id):
    db = get_db()
    db.execute("DELETE FROM apis WHERE id=?", (api_id,))
    db.commit()
    return jsonify({"success": True})

@app.route("/admin/logs")
@admin_required
def admin_logs():
    c = get_db().cursor()
    c.execute("""SELECT l.id, l.client_ip, a.name AS api_name, l.apitype, l.term, l.status_code, l.created_at
                 FROM logs l LEFT JOIN apis a ON a.id = l.api_id ORDER BY l.id DESC LIMIT 300""")
    rows = [dict(r) for r in c.fetchall()]
    return jsonify(rows)

@app.route("/admin/update_setting", methods=["POST"])
@admin_required
def admin_update_setting():
    d = request.get_json()
    key = d.get("key"); value = d.get("value")
    if not key:
        return jsonify({"success": False, "error": "key required"}), 400
    db = get_db()
    db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    db.commit()
    return jsonify({"success": True})

# ---------------- run ----------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
