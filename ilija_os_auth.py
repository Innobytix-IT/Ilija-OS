"""Ilija OS – optionale Passwort-Sperre für die Ilija-Weboberfläche.

Wird von web_server.py via install_auth(app) eingehängt. Aktiv, sobald
~/.config/ilija-os/web-auth einen SHA-256-Hex-Hash enthält; ist die Datei leer
oder fehlt sie, bleibt die Oberfläche offen (wie bisher).
"""
import hashlib
import os

from flask import session, request, redirect, render_template_string

_DIR = os.path.expanduser("~/.config/ilija-os")
_AUTH = os.path.join(_DIR, "web-auth")
_SECRET = os.path.join(_DIR, "web-secret")

_LOGIN_HTML = """<!doctype html><html lang=de><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Ilija OS – Anmeldung</title><style>
body{background:#0d0f12;color:#EFE6CF;font-family:'Ubuntu',system-ui,sans-serif;
display:grid;place-items:center;min-height:100vh;margin:0}
form{background:#16191e;border:1px solid #262b33;border-radius:14px;padding:30px;width:300px}
h1{color:#E8C15A;font-size:22px;margin:0 0 4px}p{color:#9a8f77;font-size:13px;margin:0 0 18px}
input{width:100%;padding:11px;border-radius:8px;border:1px solid #2a303a;background:#10131a;
color:#EFE6CF;box-sizing:border-box;font-size:15px}
button{width:100%;margin-top:14px;padding:11px;border:0;border-radius:8px;background:#28B6F6;
color:#04202e;font-weight:600;font-size:15px;cursor:pointer}
.err{color:#E8A05A;font-size:13px;margin-top:10px}</style></head>
<body><form method=post><h1>Ilija OS</h1><p>Bitte anmelden</p>
<input type=password name=pw placeholder="Passwort" autofocus>
<button>Anmelden</button>{{ fehler|safe }}</form></body></html>"""


def _hash() -> str:
    try:
        return open(_AUTH, encoding="utf-8").read().strip()
    except OSError:
        return ""


def _secret() -> bytes:
    try:
        return open(_SECRET, "rb").read()
    except OSError:
        s = os.urandom(24)
        try:
            os.makedirs(_DIR, exist_ok=True)
            with open(_SECRET, "wb") as f:
                f.write(s)
            os.chmod(_SECRET, 0o600)
        except OSError:
            pass
        return s


def install_auth(app) -> None:
    if not getattr(app, "secret_key", None):
        app.secret_key = _secret()

    @app.route("/login", methods=["GET", "POST"])
    def _ilija_login():
        h = _hash()
        if not h:
            return redirect("/")
        fehler = ""
        if request.method == "POST":
            pw = request.form.get("pw", "")
            if hashlib.sha256(pw.encode("utf-8")).hexdigest() == h:
                session["ilija_auth"] = True
                return redirect("/")
            fehler = '<div class="err">Falsches Passwort.</div>'
        return render_template_string(_LOGIN_HTML, fehler=fehler)

    @app.route("/logout")
    def _ilija_logout():
        session.pop("ilija_auth", None)
        return redirect("/login")

    @app.before_request
    def _ilija_gate():
        if not _hash():
            return  # kein Passwort gesetzt -> offen
        p = request.path
        if p in ("/login", "/logout") or p.startswith("/static"):
            return
        if session.get("ilija_auth"):
            return
        if p.startswith("/api"):
            return ("Anmeldung erforderlich", 401)
        return redirect("/login")
