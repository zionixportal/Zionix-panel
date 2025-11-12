# app.py (Supabase integrated version)
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from supabase import create_client, Client
from datetime import datetime
from functools import wraps
import json, requests

# ---------------- App Config ----------------
app = Flask(__name__)
app.secret_key = "change_this_to_a_random_string_please"

# Supabase Credentials (replace with yours if needed)
SUPABASE_URL = "https://vkecgwzzhvusnjpmasen.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZrZWNnd3p6aHZ1c25qcG1hc2VuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI5NTcwODUsImV4cCI6MjA3ODUzMzA4NX0.vjKvOsUZq2qFvRjhxat8CcPvEX1kTFxUvA_zCfNTlpE"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_SECRET = "yuwer@3PxZ"
ADMIN_SESSION_KEY = "is_admin"

# ---------------- Decorators ----------------
def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if session.get(ADMIN_SESSION_KEY):
            return f(*a, **kw)
        token = request.headers.get("X-ADMIN-SECRET") or request.args.get("admin_secret")
        if token and token == ADMIN_SECRET:
            session[ADMIN_SESSION_KEY] = True
            return f(*a, **kw)
        return redirect(url_for('login', next=request.path))
    return wrap

# ---------------- Helpers ----------------
def log_request(client_ip, api_id, apitype, term, status_code):
    supabase.table("logs").insert({
        "client_ip": client_ip,
        "api_id": api_id,
        "apitype": apitype,
        "term": term,
        "status_code": status_code,
        "created_at": datetime.utcnow().isoformat()
    }).execute()

def clean_json_recursive(obj, strip_keys):
    if isinstance(obj, dict):
        return {k: clean_json_recursive(v, strip_keys) for k, v in obj.items() if k not in strip_keys}
    if isinstance(obj, list):
        return [clean_json_recursive(x, strip_keys) for x in obj]
    return obj

# ---------------- Public Proxy ----------------
@app.route("/api", methods=["GET", "POST"])
def proxy():
    apiname = request.args.get("type") or request.args.get("name")
    term = request.args.get("term", "")
    if not apiname:
        return jsonify({"success": False, "error": "missing type/name parameter"}), 400

    data = supabase.table("apis").select("*").eq("name", apiname.lower()).execute()
    if not data.data:
        return jsonify({"success": False, "error": f"Unknown API type '{apiname}'"}), 404

    row = data.data[0]
    if not row.get("active", True):
        return jsonify({"success": False, "error": "This API is disabled"}), 403

    expected_key = row.get("api_key")
    key_location = row.get("key_location", "query")
    provided_key = None
    if key_location == "query":
        provided_key = request.args.get("key")
    elif key_location == "header":
        provided_key = request.headers.get("X-API-KEY")
    elif key_location == "cookie":
        provided_key = request.cookies.get(row.get("cookie_name", "x_api_key"))

    if expected_key:
        if not provided_key or provided_key != expected_key:
            return jsonify({"success": False, "error": "Invalid or missing proxy API key"}), 401

    target = (row.get("url_template") or "").replace("{term}", term)

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

    content_type = upstream.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = upstream.json()
        except Exception:
            return upstream.text, status
        strip_fields = [s.strip() for s in (row.get("strip_fields") or "").split(",") if s.strip()]
        data = clean_json_recursive(data, strip_fields)
        if row.get("add_fields"):
            try:
                extra = json.loads(row["add_fields"])
                if isinstance(data, dict):
                    data.update(extra)
            except Exception:
                pass
        return jsonify(data), status

    return upstream.content, status

# ---------------- Auth ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        secret = request.form.get("secret") or (request.json and request.json.get("secret"))
        if secret == ADMIN_SECRET:
            session[ADMIN_SESSION_KEY] = True
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid secret")
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.pop(ADMIN_SESSION_KEY, None)
    return redirect(url_for("login"))

# ---------------- Admin Dashboard ----------------
@app.route("/dashboard")
@admin_required
def dashboard():
    apis = supabase.table("apis").select("*").order("id", desc=True).execute().data
    total = len(apis)
    active = len([a for a in apis if a["active"]])
    inactive = len([a for a in apis if not a["active"]])
    logs = supabase.table("logs").select("*").execute().data
    total_requests = len(logs)
    return render_template("dashboard.html",
                           total=total, active=active, inactive=inactive,
                           total_requests=total_requests, apis=apis)

# ---------------- Admin API Endpoints ----------------
@app.route("/admin/list_apis")
@admin_required
def admin_list_apis():
    rows = supabase.table("apis").select("*").order("id", desc=True).execute().data
    return jsonify(rows)

@app.route("/admin/add_api", methods=["POST"])
@admin_required
def admin_add_api():
    d = request.get_json()
    if not d.get("name") or not d.get("url_template"):
        return jsonify({"success": False, "error": "name and url_template required"}), 400
    try:
        supabase.table("apis").insert({
            "name": d["name"].lower(),
            "url_template": d["url_template"],
            "api_key": d.get("api_key", ""),
            "key_location": d.get("key_location", "query"),
            "cookie_name": d.get("cookie_name", "x_api_key"),
            "strip_fields": d.get("strip_fields", ""),
            "add_fields": d.get("add_fields", ""),
            "owner_credit": d.get("owner_credit", ""),
            "active": True,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/admin/update_api/<int:api_id>", methods=["POST"])
@admin_required
def admin_update_api(api_id):
    d = request.get_json()
    try:
        supabase.table("apis").update({
            "url_template": d.get("url_template", ""),
            "api_key": d.get("api_key", ""),
            "key_location": d.get("key_location", "query"),
            "cookie_name": d.get("cookie_name", "x_api_key"),
            "active": bool(d.get("active", True)),
            "strip_fields": d.get("strip_fields", ""),
            "add_fields": d.get("add_fields", ""),
            "owner_credit": d.get("owner_credit", "")
        }).eq("id", api_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/admin/delete_api/<int:api_id>", methods=["POST"])
@admin_required
def admin_delete_api(api_id):
    supabase.table("apis").delete().eq("id", api_id).execute()
    return jsonify({"success": True})

@app.route("/admin/logs")
@admin_required
def admin_logs():
    rows = supabase.table("logs").select("*").order("id", desc=True).limit(300).execute().data
    return jsonify(rows)

@app.route("/admin/update_setting", methods=["POST"])
@admin_required
def admin_update_setting():
    d = request.get_json()
    key, value = d.get("key"), d.get("value")
    if not key:
        return jsonify({"success": False, "error": "key required"}), 400
    supabase.table("settings").upsert({"key": key, "value": value}).execute()
    return jsonify({"success": True})

# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
