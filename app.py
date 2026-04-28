"""
=============================================================
  BulkMailer — Free Multi-User Bulk Email SaaS
  Each user has their own account, credentials, history
=============================================================
  Local run:
    pip install -r requirements.txt
    python app.py
  Deploy: Railway.app (see README.md)
=============================================================
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3, smtplib, csv, io, threading, time, hashlib, os, json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bulkmailer-secret-change-in-production")

DB = "bulkmailer.db"

# ── Per-user send state ────────────────────────────────────
user_states = {}  # { user_id: { running, total, sent, failed, log, done, error } }


# ══════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            email     TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            created   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS credentials (
            user_id      INTEGER PRIMARY KEY,
            smtp_login   TEXT,
            smtp_key     TEXT,
            sender_email TEXT,
            sender_name  TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS templates (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            name     TEXT,
            subject  TEXT,
            plain    TEXT,
            html     TEXT,
            image_url TEXT,
            created  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            subject    TEXT,
            total      INTEGER,
            sent       INTEGER,
            failed     INTEGER,
            sent_at    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)

init_db()


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════
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

def get_user(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

def get_creds(user_id):
    with get_db() as db:
        return db.execute("SELECT * FROM credentials WHERE user_id=?", (user_id,)).fetchone()


# ══════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw    = request.form.get("password","")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=? AND password=?",
                              (email, hash_pw(pw))).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        error = "Invalid email or password."
    return render_template("login.html", error=error, mode="login")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
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


# ══════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════
@app.route("/dashboard")
@login_required
def dashboard():
    uid   = session["user_id"]
    creds = get_creds(uid)
    with get_db() as db:
        hist = db.execute(
            "SELECT * FROM history WHERE user_id=? ORDER BY sent_at DESC LIMIT 10", (uid,)
        ).fetchall()
        templates = db.execute(
            "SELECT * FROM templates WHERE user_id=? ORDER BY created DESC", (uid,)
        ).fetchall()
        total_sent = db.execute(
            "SELECT COALESCE(SUM(sent),0) as s FROM history WHERE user_id=?", (uid,)
        ).fetchone()["s"]
        campaigns  = db.execute(
            "SELECT COUNT(*) as c FROM history WHERE user_id=?", (uid,)
        ).fetchone()["c"]
    return render_template("dashboard.html",
        user_name=session["user_name"],
        creds=creds, history=hist,
        templates=templates,
        total_sent=total_sent,
        campaigns=campaigns
    )


# ══════════════════════════════════════════════════════════
#  CREDENTIALS API
# ══════════════════════════════════════════════════════════
@app.route("/api/credentials", methods=["POST"])
@api_login_required
def save_credentials():
    uid = session["user_id"]
    d   = request.json
    with get_db() as db:
        existing = db.execute("SELECT 1 FROM credentials WHERE user_id=?", (uid,)).fetchone()
        if existing:
            db.execute("""UPDATE credentials SET smtp_login=?,smtp_key=?,sender_email=?,sender_name=?
                          WHERE user_id=?""",
                       (d["smtp_login"], d["smtp_key"], d["sender_email"], d["sender_name"], uid))
        else:
            db.execute("""INSERT INTO credentials (user_id,smtp_login,smtp_key,sender_email,sender_name)
                          VALUES (?,?,?,?,?)""",
                       (uid, d["smtp_login"], d["smtp_key"], d["sender_email"], d["sender_name"]))
    return jsonify({"message": "Credentials saved!"})

@app.route("/api/credentials", methods=["GET"])
@api_login_required
def get_credentials():
    creds = get_creds(session["user_id"])
    if creds:
        return jsonify({"smtp_login": creds["smtp_login"], "sender_email": creds["sender_email"],
                        "sender_name": creds["sender_name"], "has_key": bool(creds["smtp_key"])})
    return jsonify({})


# ══════════════════════════════════════════════════════════
#  TEMPLATES API
# ══════════════════════════════════════════════════════════
@app.route("/api/templates", methods=["POST"])
@api_login_required
def save_template():
    uid = session["user_id"]
    d   = request.json
    with get_db() as db:
        db.execute("""INSERT INTO templates (user_id,name,subject,plain,html,image_url)
                      VALUES (?,?,?,?,?,?)""",
                   (uid, d["name"], d["subject"], d["plain"], d["html"], d.get("image_url","")))
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


# ══════════════════════════════════════════════════════════
#  CSV PARSE
# ══════════════════════════════════════════════════════════
@app.route("/api/parse-csv", methods=["POST"])
@api_login_required
def parse_csv():
    f = request.files.get("csv_file")
    if not f:
        return jsonify({"error": "No file"}), 400
    try:
        content = f.read().decode("utf-8")
        reader  = csv.DictReader(io.StringIO(content))
        contacts = [{k.strip(): v.strip() for k, v in r.items()}
                    for r in reader if r.get("email","").strip()]
        return jsonify({"contacts": contacts, "count": len(contacts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ══════════════════════════════════════════════════════════
#  SEND ENGINE
# ══════════════════════════════════════════════════════════
def do_send(uid, contacts, subject, plain, html, image_url, smtp_login, smtp_key, sender_email, sender_name):
    user_states[uid] = {"running": True, "total": len(contacts),
                        "sent": 0, "failed": 0, "log": [], "done": False, "error": None}
    s = user_states[uid]
    try:
        with smtplib.SMTP("smtp-relay.brevo.com", 587) as srv:
            srv.starttls()
            srv.login(smtp_login, smtp_key)
            for c in contacts:
                name  = c.get("name", "there")
                email = c.get("email", "")
                if not email: continue
                try:
                    msg = MIMEMultipart("alternative")
                    msg["From"]    = f"{sender_name} <{sender_email}>"
                    msg["To"]      = email
                    msg["Subject"] = subject.replace("{name}", name)
                    p2 = plain.replace("{name}", name)
                    h2 = html.replace("{name}", name).replace("IMAGE_URL_HERE", image_url)
                    msg.attach(MIMEText(p2, "plain"))
                    msg.attach(MIMEText(h2, "html"))
                    srv.sendmail(sender_email, email, msg.as_string())
                    s["sent"] += 1
                    s["log"].append(f"✓ {name} <{email}>")
                    time.sleep(0.4)
                except Exception as ex:
                    s["failed"] += 1
                    s["log"].append(f"✗ {email} — {ex}")
    except smtplib.SMTPAuthenticationError:
        s["error"] = "Authentication failed! Check your Brevo SMTP login and key."
    except Exception as ex:
        s["error"] = str(ex)

    s["running"] = False
    s["done"]    = True

    # Save to history
    if s["sent"] > 0 or s["failed"] > 0:
        with get_db() as db:
            db.execute("INSERT INTO history (user_id,subject,total,sent,failed) VALUES (?,?,?,?,?)",
                       (uid, subject, s["total"], s["sent"], s["failed"]))


@app.route("/api/send", methods=["POST"])
@api_login_required
def send():
    uid = session["user_id"]
    if user_states.get(uid, {}).get("running"):
        return jsonify({"error": "Already sending! Please wait."}), 400

    d = request.json
    if not d.get("contacts"):
        return jsonify({"error": "No contacts loaded"}), 400

    creds = get_creds(uid)
    smtp_login   = creds["smtp_login"]   if creds else d.get("smtp_login","")
    smtp_key     = creds["smtp_key"]     if creds else d.get("smtp_key","")
    sender_email = creds["sender_email"] if creds else d.get("sender_email","")
    sender_name  = creds["sender_name"]  if creds else d.get("sender_name","")

    if not smtp_login or not smtp_key or not sender_email:
        return jsonify({"error": "Missing Brevo credentials. Go to Settings first."}), 400

    t = threading.Thread(target=do_send, args=(
        uid, d["contacts"], d["subject"], d["plain_body"], d["html_body"],
        d.get("image_url",""), smtp_login, smtp_key, sender_email, sender_name
    ))
    t.daemon = True
    t.start()
    return jsonify({"message": "Started!"})


@app.route("/api/progress")
@api_login_required
def progress():
    uid = session["user_id"]
    return jsonify(user_states.get(uid, {"running": False, "total": 0,
                                         "sent": 0, "failed": 0, "log": [], "done": False}))


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