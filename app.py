from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from supabase import create_client, Client
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "zionix_secret_key")

# Supabase setup
SUPABASE_URL = "https://vkecgwzzhvusnjpmasen.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZrZWNnd3p6aHZ1c25qcG1hc2VuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI5NTcwODUsImV4cCI6MjA3ODUzMzA4NX0.vjKvOsUZq2qFvRjhxat8CcPvEX1kTFxUvA_zCfNTlpE"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Config ---
ADMIN_KEY = os.getenv("ADMIN_KEY", "ZIONIX_KEY")
BASE_URL = "https://zionix-x-api.vercel.app"

# ----------------- LOGIN -----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        key = request.form.get("access_key")
        if key == ADMIN_KEY:
            session["logged_in"] = True
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid Access Key")
    return render_template("login.html")

# ----------------- DASHBOARD -----------------
@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    data = supabase.table("apis").select("*").execute()
    apis = data.data if data.data else []
    return render_template("dashboard.html", apis=apis, base_url=BASE_URL)

# ----------------- LOGOUT -----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----------------- CREATE PROXY -----------------
@app.route("/create", methods=["POST"])
def create_proxy():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    name = request.form.get("name")
    api_key = request.form.get("api_key")
    api_url = request.form.get("api_url")
    duration = int(request.form.get("duration", 24))  # default 24 hrs

    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(hours=duration)

    new_proxy = {
        "name": name,
        "api_key": api_key,
        "api_url": api_url,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    supabase.table("apis").insert(new_proxy).execute()
    return redirect("/dashboard")

# ----------------- EDIT PROXY -----------------
@app.route("/edit/<int:proxy_id>", methods=["GET", "POST"])
def edit_proxy(proxy_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name")
        api_key = request.form.get("api_key")
        api_url = request.form.get("api_url")
        duration = int(request.form.get("duration", 24))
        expires_at = datetime.utcnow() + timedelta(hours=duration)

        supabase.table("apis").update({
            "name": name,
            "api_key": api_key,
            "api_url": api_url,
            "expires_at": expires_at.isoformat()
        }).eq("id", proxy_id).execute()

        return redirect("/dashboard")

    data = supabase.table("apis").select("*").eq("id", proxy_id).execute()
    proxy = data.data[0] if data.data else None
    return render_template("edit.html", proxy=proxy)

# ----------------- DELETE PROXY -----------------
@app.route("/delete/<int:proxy_id>")
def delete_proxy(proxy_id):
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    supabase.table("apis").delete().eq("id", proxy_id).execute()
    return redirect("/dashboard")

# ----------------- API ENDPOINT -----------------
@app.route("/api/<key>/<type>/<term>")
def api_proxy(key, type, term):
    data = supabase.table("apis").select("*").eq("api_key", key).execute()
    if not data.data:
        return jsonify({"error": "Invalid key"}), 401

    # Example: Forward to the API URL
    proxy = data.data[0]
    api_url = proxy["api_url"]
    expiry = datetime.fromisoformat(proxy["expires_at"])

    if datetime.utcnow() > expiry:
        return jsonify({"error": "Proxy expired"}), 403

    full_url = f"{api_url}?key={key}&type={type}&term={term}"
    return jsonify({
        "success": True,
        "proxy_url_called": full_url
    })

# ----------------- RUN -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
