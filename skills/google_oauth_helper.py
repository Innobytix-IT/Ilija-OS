"""
google_oauth_helper.py — Zentrale OAuth-Logik für alle Google-Services in Ilija OS

Zweck:
    Backend-Helper für den OAuth2-Flow mit Google. Ersetzt den bisherigen Ansatz
    (flow.run_local_server(open_browser=True)), der nur funktioniert wenn Ilija
    im User-Terminal mit DISPLAY läuft, nicht als systemd-Service.

Design:
    - credentials.json wird zentral erkannt (Desktop-App vs. Webanwendung)
    - Pro Service separater Scope + separate token.json
    - OAuth-State in-memory mit TTL (CSRF-Schutz)
    - redirect_uri wird dynamisch je nach Credential-Typ gebaut

Benutzt von:
    - web_server.py (API-Routen /api/google-oauth-start, /api/google-oauth-callback)
    - skills/google_kalender.py und andere Google-Skills (via get_credentials())
"""

from __future__ import annotations

import json
import os
import secrets
import time
import threading
from typing import Optional

# Zentraler Pfad: credentials.json liegt immer hier (bei Upload über Web-UI)
_BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR         = os.path.join(_BASE_DIR, "data")
_CREDENTIALS_PATH = os.path.join(_DATA_DIR, "google_kalender", "credentials.json")

# Welcher Scope gehört zu welchem Service?
SERVICE_SCOPES = {
    "gmail":            ["https://www.googleapis.com/auth/gmail.readonly",
                         "https://www.googleapis.com/auth/gmail.send"],
    "google_drive":     ["https://www.googleapis.com/auth/drive.file"],
    "google_docs":      ["https://www.googleapis.com/auth/documents"],
    "google_kalender":  ["https://www.googleapis.com/auth/calendar"],
}

# Welche Services kennt Ilija überhaupt?
KNOWN_SERVICES = set(SERVICE_SCOPES.keys())

# In-memory State-Store für CSRF-Schutz; State → Dict mit service + expires
# Thread-safe, da Flask Routes aus mehreren Threads kommen können
_oauth_states: dict[str, dict] = {}
_states_lock = threading.Lock()
_STATE_TTL   = 600  # 10 Minuten


# ─── Credential-Typ-Erkennung ─────────────────────────────────────────────────

def credentials_info() -> dict:
    """
    Liest credentials.json und meldet Status + Typ.

    Return:
        {
            "exists": bool,
            "type": "installed" | "web" | None,
            "client_id": str | None,
            "redirect_uris_configured": list[str],   # aus web-config, sonst []
        }
    """
    if not os.path.exists(_CREDENTIALS_PATH):
        return {"exists": False, "type": None, "client_id": None,
                "redirect_uris_configured": []}

    try:
        with open(_CREDENTIALS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"exists": False, "type": None, "client_id": None,
                "redirect_uris_configured": []}

    for key in ("installed", "web"):
        if key in data:
            inner = data[key]
            return {
                "exists": True,
                "type": key,
                "client_id": inner.get("client_id"),
                "redirect_uris_configured": inner.get("redirect_uris", []),
            }
    return {"exists": True, "type": None, "client_id": None,
            "redirect_uris_configured": []}


# ─── Flow-Start: URL generieren ───────────────────────────────────────────────

def start_oauth(service: str, redirect_uri: str) -> tuple[str, str]:
    """
    Baut die Google-Autorisierungs-URL für einen Service.

    Args:
        service: einer aus KNOWN_SERVICES
        redirect_uri: an welche URL Google nach Login redirecten soll
                      (muss zum Credential-Typ passen)

    Return:
        (auth_url, state)   — state muss im Frontend/Session gespeichert werden
                             und beim Callback verifiziert werden

    Raises:
        ValueError bei unbekanntem Service oder fehlender credentials.json
    """
    if service not in KNOWN_SERVICES:
        raise ValueError(f"Unbekannter Service: {service}")

    info = credentials_info()
    if not info["exists"]:
        raise ValueError("credentials.json fehlt – bitte zuerst hochladen")
    if info["type"] not in ("installed", "web"):
        raise ValueError("credentials.json hat weder 'installed' noch 'web' – "
                         "ist das wirklich eine OAuth-Credentials-Datei?")

    # Lazy import damit Backend ohne Google-Libs starten kann wenn kein User
    # jemals Google benutzt
    from google_auth_oauthlib.flow import Flow  # type: ignore

    scopes = SERVICE_SCOPES[service]
    flow = Flow.from_client_secrets_file(
        _CREDENTIALS_PATH,
        scopes=scopes,
        redirect_uri=redirect_uri,
    )

    state = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",       # garantiert refresh_token im response
        # KEIN include_granted_scopes: Wir fuehren pro Service einen eigenen
        # Token mit genau den noetigen Scopes. include_granted_scopes="true"
        # wuerde Google veranlassen, alle vorher erteilten Scopes dieses
        # Google-Kontos mit zurueckzugeben – der Flow bekaeme dann z.B. beim
        # Drive-Login auch Gmail-Scopes, was zu einem "Scope has changed"-
        # ValueError in google-auth-oauthlib fuehrt.
        state=state,
    )

    # PKCE: flow.authorization_url() hat intern einen code_verifier erzeugt
    # und den code_challenge an Google geschickt. Beim Callback brauchen wir
    # genau diesen code_verifier wieder, um das Token zu bekommen – also mit
    # dem State mitspeichern.
    code_verifier = getattr(flow, "code_verifier", None)

    with _states_lock:
        # Alte expired States aufräumen (lazy GC)
        now = time.time()
        expired = [s for s, v in _oauth_states.items() if v["expires"] < now]
        for s in expired:
            _oauth_states.pop(s, None)
        # Neuen State speichern
        _oauth_states[state] = {
            "service":       service,
            "redirect_uri":  redirect_uri,
            "code_verifier": code_verifier,
            "expires":       now + _STATE_TTL,
        }

    return auth_url, state


# ─── Callback: Code gegen Token tauschen ──────────────────────────────────────

def complete_oauth(code: str, state: str) -> str:
    """
    Verarbeitet den Google-OAuth-Callback: tauscht den code gegen access_token +
    refresh_token und speichert token.json für den entsprechenden Service.

    Args:
        code:  aus dem Query-Parameter ?code=... beim Callback
        state: aus dem Query-Parameter ?state=... beim Callback

    Return:
        service   — welcher Service wurde erfolgreich autorisiert

    Raises:
        ValueError bei unbekanntem/abgelaufenem state oder OAuth-Fehlern
    """
    with _states_lock:
        state_data = _oauth_states.pop(state, None)
    if not state_data:
        raise ValueError("Ungültiger oder abgelaufener OAuth-State. "
                         "Bitte den Autorisierungs-Vorgang neu starten.")
    if state_data["expires"] < time.time():
        raise ValueError("OAuth-Sitzung ist abgelaufen (max. 10 Min). "
                         "Bitte neu starten.")

    service       = state_data["service"]
    redirect_uri  = state_data["redirect_uri"]
    code_verifier = state_data.get("code_verifier")

    from google_auth_oauthlib.flow import Flow  # type: ignore

    scopes = SERVICE_SCOPES[service]
    flow = Flow.from_client_secrets_file(
        _CREDENTIALS_PATH,
        scopes=scopes,
        redirect_uri=redirect_uri,
        state=state,
    )

    # PKCE: code_verifier wiederherstellen, den start_oauth() beim Erzeugen der
    # Autorisierungs-URL verwendet hat – ohne ihn lehnt Google den Token-Tausch
    # mit "invalid_grant: Missing code verifier" ab.
    if code_verifier:
        flow.code_verifier = code_verifier

    flow.fetch_token(code=code)

    # Token in service-spezifischem Ordner ablegen
    token_dir  = os.path.join(_DATA_DIR, service)
    token_path = os.path.join(token_dir, "token.json")
    os.makedirs(token_dir, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(flow.credentials.to_json())

    return service


# ─── Credential-Abruf für Skills ──────────────────────────────────────────────

def get_credentials(service: str):
    """
    Liefert gültige Google-Credentials für einen Service, oder None wenn noch
    nicht autorisiert / Token kaputt. Macht automatischen Refresh wenn möglich.

    Benutzt von: skills/google_kalender.py, skills/datei_lesen.py etc.

    Return:
        google.oauth2.credentials.Credentials | None
    """
    if service not in KNOWN_SERVICES:
        return None

    token_path = os.path.join(_DATA_DIR, service, "token.json")
    if not os.path.exists(token_path):
        return None

    try:
        from google.oauth2.credentials      import Credentials       # type: ignore
        from google.auth.transport.requests import Request           # type: ignore
    except ImportError:
        return None

    scopes = SERVICE_SCOPES[service]
    try:
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    except Exception:
        return None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Aktualisiertes Token speichern (neuer access_token)
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            return creds
        except Exception:
            return None
    return None


def revoke(service: str) -> bool:
    """
    Löscht das token.json eines Services – User kann dann neu autorisieren.
    (Revoke beim Google-Server selbst macht das NICHT, nur lokal entfernen.)

    Return:
        True wenn gelöscht, False wenn Datei nicht existierte
    """
    if service not in KNOWN_SERVICES:
        return False
    token_path = os.path.join(_DATA_DIR, service, "token.json")
    if os.path.exists(token_path):
        try:
            os.remove(token_path)
            return True
        except OSError:
            return False
    return False
