"""
ahpt_routes.py – AHPT-Einstellungen API für Ilija OS Web-Interface
Verwaltet den AHPT-Agent auf dem EliteBook (systemd user service).
"""

import os
import re
import json
import subprocess
from flask import Blueprint, jsonify, request, render_template

_AHPT_DIR   = os.environ.get("AHPT_DIR", "/home/manuel/.ahpt")
_TOML_PATH = os.path.join(_AHPT_DIR, "agent_elitebook.toml")
_KEY_PATH   = os.path.join(_AHPT_DIR, "agent_elitebook.key")
_PUB_PATH   = os.path.join(_AHPT_DIR, "agent_elitebook.pub")
_STAND_PATH = os.path.join(_AHPT_DIR, "einrichten_stand.json")
_SERVICE    = "ahpt-elitebook"


def _read_toml_field(path, field):
    """Liest einen einzelnen Scalar-Wert aus einer TOML-Datei (keine Secrets)."""
    try:
        with open(path, "r") as f:
            content = f.read()
        m = re.search(rf'^\s*{re.escape(field)}\s*=\s*"([^"]*)"', content, re.M)
        if m:
            return m.group(1)
        m = re.search(rf'^\s*{re.escape(field)}\s*=\s*([^\n#]+)', content, re.M)
        if m:
            return m.group(1).strip()
    except FileNotFoundError:
        pass
    return None


def _read_toml_clients(path):
    """Liest die clients-Liste aus der TOML-Datei."""
    try:
        with open(path, "r") as f:
            content = f.read()
        m = re.search(r'clients\s*=\s*\[(.*?)\]', content, re.S)
        if m:
            raw = m.group(1)
            keys = re.findall(r'"([0-9a-f]{64})"', raw)
            return keys
    except FileNotFoundError:
        pass
    return []


def _read_toml_dienste(path):
    """Liest alle [[dienst]]-Blöcke aus der TOML-Datei."""
    dienste = []
    try:
        with open(path, "r") as f:
            content = f.read()
        blocks = re.split(r'\[\[dienst\]\]', content)
        for block in blocks[1:]:
            d = {}
            for key in ("name", "art", "wurzel", "max_bytes"):
                m = re.search(rf'^\s*{key}\s*=\s*"?([^"\n]+)"?', block, re.M)
                if m:
                    d[key] = m.group(1).strip().strip('"')
            aktionen_m = re.search(r'aktionen\s*=\s*\[([^\]]*)\]', block)
            if aktionen_m:
                d["aktionen"] = re.findall(r'"([^"]+)"', aktionen_m.group(1))
            endungen_m = re.search(r'endungen\s*=\s*\[([^\]]*)\]', block)
            if endungen_m:
                d["endungen"] = re.findall(r'"([^"]+)"', endungen_m.group(1))
            if "name" in d:
                dienste.append(d)
    except FileNotFoundError:
        pass
    return dienste


def _get_pubkey():
    """Liest den öffentlichen Schlüssel aus der .pub-Datei (o+r, kein Secret)."""
    try:
        with open(_PUB_PATH, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        pass
    # Fallback: einrichten_stand.json
    try:
        with open(_STAND_PATH, "r") as f:
            stand = json.load(f)
        return stand.get("agent_oeffentlich", "")
    except Exception:
        return ""


def _service_status():
    """Gibt den Status des AHPT-Agent-Prozesses zurück."""
    try:
        r = subprocess.run(
            ["pgrep", "-fa", "relay_agent.py"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and "agent_elitebook" in r.stdout:
            return "active"
        return "inactive"
    except Exception:
        return "unknown"


def register_ahpt_routes(app):
    bp = Blueprint("ahpt", __name__)

    @bp.route("/api/ahpt-settings", methods=["GET"])
    def ahpt_get():
        return jsonify({
            "relay":      _read_toml_field(_TOML_PATH, "basis") or "",
            "geheimnis":  _read_toml_field(_TOML_PATH, "geheimnis_datei") or "",
            "key":        _read_toml_field(_TOML_PATH, "schluessel") or "",
            "pubkey":     _get_pubkey(),
            "clients":    _read_toml_clients(_TOML_PATH),
            "dienste":    _read_toml_dienste(_TOML_PATH),
            "status":     _service_status(),
        })

    @bp.route("/api/ahpt-settings", methods=["POST"])
    def ahpt_save():
        data = request.get_json(force=True) or {}
        try:
            with open(_TOML_PATH, "r") as f:
                content = f.read()

            # clients-Liste aktualisieren
            new_clients = data.get("clients", [])
            clients_str = ", ".join(f'"{k}"' for k in new_clients)
            content = re.sub(
                r'clients\s*=\s*\[[^\]]*\]',
                f'clients = [{clients_str}]',
                content, flags=re.S)

            # dms_import-Pfad in [[dienst]] mit name="dms_import" aktualisieren
            new_dms_path = data.get("dms_import_pfad", "")
            if new_dms_path:
                def replace_wurzel(m):
                    block = m.group(0)
                    block = re.sub(r'wurzel\s*=\s*"[^"]*"',
                                   f'wurzel = "{new_dms_path}"', block)
                    return block

                # Nur den dms_import-Dienst-Block patchen
                parts = re.split(r'(\[\[dienst\]\])', content)
                result = []
                i = 0
                while i < len(parts):
                    if parts[i] == "[[dienst]]" and i + 1 < len(parts):
                        block = parts[i + 1]
                        nm = re.search(r'name\s*=\s*"dms_import"', block)
                        if nm:
                            block = re.sub(r'wurzel\s*=\s*"[^"]*"',
                                           f'wurzel = "{new_dms_path}"', block)
                        result.append(parts[i] + block)
                        i += 2
                    else:
                        result.append(parts[i])
                        i += 1
                content = "".join(result)

            with open(_TOML_PATH, "w") as f:
                f.write(content)

            return jsonify({"ok": True, "message": "AHPT-Einstellungen gespeichert."})
        except FileNotFoundError:
            return jsonify({"ok": False, "message": f"Konfigurationsdatei nicht gefunden: {_TOML_PATH}"}), 404
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @bp.route("/api/ahpt-status", methods=["GET"])
    def ahpt_status():
        state = _service_status()
        return jsonify({"status": state, "running": state == "active"})

    @bp.route("/api/ahpt-control", methods=["POST"])
    def ahpt_control():
        data = request.get_json(force=True) or {}
        action = data.get("action", "")
        if action not in ("start", "stop", "restart"):
            return jsonify({"ok": False, "message": "Ungültige Aktion."}), 400
        try:
            # systemctl --user muss als manuel-User laufen (XDG_RUNTIME_DIR setzen)
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = "/run/user/1000"
            r = subprocess.run(
                ["sudo", "-u", "manuel", "systemctl", "--user", action, _SERVICE],
                capture_output=True, text=True, timeout=10, env=env)
            ok = r.returncode == 0
            status = _service_status()
            return jsonify({
                "ok": ok,
                "message": f"Service {action}: {'OK' if ok else (r.stderr.strip() or r.stdout.strip())}",
                "status": status,
            })
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @bp.route("/tools/relay-builder")
    def relay_builder():
        return render_template("ahpt_relay_builder.html")

    app.register_blueprint(bp)
