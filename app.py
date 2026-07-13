"""
BulkMailer — Free Multi-User Bulk Email SaaS
Uses Brevo HTTP API (works on PythonAnywhere free plan)
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3, csv, io, time, hashlib, os, json
import urllib.request, urllib.error
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bulkmailer-secret-2083")
DB = "bulkmailer.db"

# ── DATABASE ───────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS credentials (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT,
            sender_email TEXT,
            sender_name TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, name TEXT, subject TEXT,
            plain TEXT, html TEXT, image_url TEXT,
            created TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, subject TEXT,
            total INTEGER, sent INTEGER, failed INTEGER,
            sent_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)

init_db()

# ── HELPERS ────────────────────────────────────────────────
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "Not logged in"}), 401
        return f(*args, **kwargs)
    return decorated

def get_creds(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM credentials WHERE user_id=?", (user_id,)).fetchone()

# ── BREVO HTTP API SENDER ──────────────────────────────────
def send_via_brevo_api(api_key, sender_email, sender_name, to_email, to_name, subject, plain, html):
    """Send one email using Brevo HTTP API — works on PythonAnywhere free plan."""
    url = "https://api.brevo.com/v3/smtp/email"
    payload = json.dumps({
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "textContent": plain,
        "htmlContent": html
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("api-key", api_key)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201, 202), None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {e.code}: {body[:200]}"
    except Exception as ex:
        return False, str(ex)

# ── AUTH ───────────────────────────────────────────────────
@app.route("/")
def index():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw    = request.form.get("password","")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=? AND password=?",
                              (email, hash_pw(pw))).fetchone()
        if user:
            session["user_id"]   = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        error = "Invalid email or password."
    return render_template("login.html", error=error, mode="login")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        name  = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        pw    = request.form.get("password","")
        pw2   = request.form.get("password2","")
        if not name or not email or not pw:
            error = "All fields are required."
        elif pw != pw2:
            error = "Passwords do not match."
        elif len(pw) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO users (name,email,password) VALUES (?,?,?)",
                               (name, email, hash_pw(pw)))
                    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                    session["user_id"]   = user["id"]
                    session["user_name"] = user["name"]
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                error = "Email already registered. Please log in."
    return render_template("login.html", error=error, mode="signup")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── DASHBOARD ──────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    uid   = session["user_id"]
    creds = get_creds(uid)
    with get_db() as db:
        hist       = db.execute("SELECT * FROM history WHERE user_id=? ORDER BY sent_at DESC LIMIT 10", (uid,)).fetchall()
        templates  = db.execute("SELECT * FROM templates WHERE user_id=? ORDER BY created DESC", (uid,)).fetchall()
        total_sent = db.execute("SELECT COALESCE(SUM(sent),0) as s FROM history WHERE user_id=?", (uid,)).fetchone()["s"]
        campaigns  = db.execute("SELECT COUNT(*) as c FROM history WHERE user_id=?", (uid,)).fetchone()["c"]
    return render_template("dashboard.html",
        user_name=session["user_name"], creds=creds,
        history=hist, templates=templates,
        total_sent=total_sent, campaigns=campaigns)

@app.route("/guide")
@login_required
def guide():
    return render_template("guide.html")

# ── CREDENTIALS ────────────────────────────────────────────
@app.route("/api/credentials", methods=["POST"])
@api_login_required
def save_credentials():
    uid = session["user_id"]
    d   = request.json
    with get_db() as db:
        existing = db.execute("SELECT 1 FROM credentials WHERE user_id=?", (uid,)).fetchone()
        if existing:
            db.execute("UPDATE credentials SET api_key=?,sender_email=?,sender_name=? WHERE user_id=?",
                       (d["api_key"], d["sender_email"], d["sender_name"], uid))
        else:
            db.execute("INSERT INTO credentials (user_id,api_key,sender_email,sender_name) VALUES (?,?,?,?)",
                       (uid, d["api_key"], d["sender_email"], d["sender_name"]))
    return jsonify({"message": "Credentials saved!"})

@app.route("/api/credentials", methods=["GET"])
@api_login_required
def get_credentials():
    creds = get_creds(session["user_id"])
    if creds:
        return jsonify({"sender_email": creds["sender_email"],
                        "sender_name":  creds["sender_name"],
                        "has_key": bool(creds["api_key"])})
    return jsonify({})

# ── TEMPLATES ──────────────────────────────────────────────
@app.route("/api/templates", methods=["POST"])
@api_login_required
def save_template():
    uid = session["user_id"]
    d   = request.json
    with get_db() as db:
        db.execute("INSERT INTO templates (user_id,name,subject,plain,html,image_url) VALUES (?,?,?,?,?,?)",
                   (uid, d["name"], d["subject"], d["plain"], d.get("html",""), d.get("image_url","")))
    return jsonify({"message": "Template saved!"})

@app.route("/api/templates", methods=["GET"])
@api_login_required
def list_templates():
    with get_db() as db:
        rows = db.execute("SELECT * FROM templates WHERE user_id=? ORDER BY created DESC",
                          (session["user_id"],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/templates/<int:tid>", methods=["DELETE"])
@api_login_required
def delete_template(tid):
    with get_db() as db:
        db.execute("DELETE FROM templates WHERE id=? AND user_id=?", (tid, session["user_id"]))
    return jsonify({"message": "Deleted"})

# ── CSV PARSE ──────────────────────────────────────────────
@app.route("/api/parse-csv", methods=["POST"])
@api_login_required
def parse_csv():
    f = request.files.get("csv_file")
    if not f: return jsonify({"error": "No file"}), 400
    try:
        content  = f.read().decode("utf-8")
        reader   = csv.DictReader(io.StringIO(content))
        contacts = [{k.strip().lower(): v.strip() for k, v in r.items()}
                    for r in reader]
        contacts = [c for c in contacts if c.get("email","").strip()]
        return jsonify({"contacts": contacts, "count": len(contacts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── SEND via Brevo HTTP API ────────────────────────────────
@app.route("/api/send", methods=["POST"])
@api_login_required
def send():
    uid   = session["user_id"]
    d     = request.json
    creds = get_creds(uid)

    if not creds or not creds["api_key"]:
        return jsonify({"error": "Missing Brevo API key. Go to Settings and save your credentials first."}), 400

    contacts     = d.get("contacts", [])
    subject      = d.get("subject", "")
    plain_body   = d.get("plain_body", "")
    html_body    = d.get("html_body", "")
    image_url    = d.get("image_url", "")
    sender_email = creds["sender_email"]
    sender_name  = creds["sender_name"]
    api_key      = creds["api_key"]

    if not contacts:
        return jsonify({"error": "No contacts loaded"}), 400
    if not subject or not plain_body:
        return jsonify({"error": "Subject and email body cannot be empty"}), 400

    sent_count   = 0
    failed_count = 0
    log          = []

    for c in contacts:
        name  = c.get("name", "there")
        email = c.get("email", "")
        if not email:
            continue

        subj  = subject.replace("{name}", name)
        plain = plain_body.replace("{name}", name)
        html  = html_body.replace("{name}", name).replace("IMAGE_URL_HERE", image_url)

        ok, err = send_via_brevo_api(api_key, sender_email, sender_name,
                                     email, name, subj, plain, html)
        if ok:
            sent_count += 1
            log.append(f"✓ {name} <{email}>")
        else:
            failed_count += 1
            log.append(f"✗ {email} — {err}")

        time.sleep(0.2)  # stay within rate limits

    # Save to history
    with get_db() as db:
        db.execute("INSERT INTO history (user_id,subject,total,sent,failed) VALUES (?,?,?,?,?)",
                   (uid, subject, len(contacts), sent_count, failed_count))

    return jsonify({
        "done": True,
        "total": len(contacts),
        "sent": sent_count,
        "failed": failed_count,
        "log": log
    })

# ── HISTORY ────────────────────────────────────────────────
@app.route("/api/history")
@api_login_required
def history():
    with get_db() as db:
        rows = db.execute("SELECT * FROM history WHERE user_id=? ORDER BY sent_at DESC LIMIT 20",
                          (session["user_id"],)).fetchall()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  BulkMailer running at http://localhost:{port}\n")
    app.run(debug=False, host="0.0.0.0", port=port)