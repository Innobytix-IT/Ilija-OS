"""
ahpt_routes.py – AHPT-Einstellungen API für Ilija OS Web-Interface
Verwaltet den AHPT-Agent (systemd user service) des aktuellen Users.

Pfade und Service-Name sind pro Installation dynamisch: HOME des aktiven
Users + Hostname. Fruehere Hardcodes "/home/manuel/.ahpt" und
"ahpt-elitebook" wurden auf Melanis Thin-Client zu Fehlern:
"Unbekannter Benutzer manuel".
"""

import io
import os
import re
import socket
import getpass
import json
import subprocess
import zipfile
from flask import Blueprint, jsonify, request, render_template, send_file

_CURRENT_USER = getpass.getuser()
_HOSTNAME     = socket.gethostname().lower().split(".")[0]  # z.B. "ilijaos-futros930"

# Hostname-Suffix fuer Service- und Dateinamen (nur ASCII-Buchstaben,
# Ziffern, "-" erlaubt – systemd-konform)
_HOST_TAG = re.sub(r'[^a-z0-9-]', '-', _HOSTNAME).strip('-') or "agent"

_AHPT_DIR   = os.environ.get("AHPT_DIR", os.path.expanduser("~/.ahpt"))
_TOML_PATH  = os.path.join(_AHPT_DIR, f"agent_{_HOST_TAG}.toml")
_KEY_PATH   = os.path.join(_AHPT_DIR, f"agent_{_HOST_TAG}.key")
_PUB_PATH   = os.path.join(_AHPT_DIR, f"agent_{_HOST_TAG}.pub")
_STAND_PATH = os.path.join(_AHPT_DIR, "einrichten_stand.json")
_SERVICE    = os.environ.get("AHPT_SERVICE", f"ahpt-{_HOST_TAG}")


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
    """Gibt den Status des AHPT-Agent-systemd-user-services zurueck.
    Hierarchie:
      1. TOML-Config fehlt?           -> 'not-configured'
      2. Service-Unit nicht installiert? -> 'not-installed'
      3. systemctl is-active-Status:  'active' / 'inactive' / 'failed'
    """
    if not os.path.exists(_TOML_PATH):
        return "not-configured"
    try:
        env = os.environ.copy()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        # Erst pruefen ob Service-Unit ueberhaupt existiert
        r_list = subprocess.run(
            ["systemctl", "--user", "list-unit-files", f"{_SERVICE}.service", "--no-legend"],
            capture_output=True, text=True, timeout=5, env=env)
        if not (r_list.stdout or "").strip():
            return "not-installed"
        # Jetzt den Status abfragen
        r = subprocess.run(
            ["systemctl", "--user", "is-active", _SERVICE],
            capture_output=True, text=True, timeout=5, env=env)
        state = (r.stdout or "").strip()
        if state in ("active", "inactive", "failed", "activating", "deactivating"):
            return state
        return "unknown"
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
            "service":    _SERVICE,
            "host":       _HOSTNAME,
            "user":       _CURRENT_USER,
            "home_hint":  os.path.expanduser("~"),
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
        return jsonify({
            "status":  state,
            "running": state == "active",
            "service": _SERVICE,
            "host":    _HOSTNAME,
            "user":    _CURRENT_USER,
        })

    @bp.route("/api/ahpt-control", methods=["POST"])
    def ahpt_control():
        data = request.get_json(force=True) or {}
        action = data.get("action", "")
        if action not in ("start", "stop", "restart"):
            return jsonify({"ok": False, "message": "Ungültige Aktion."}), 400
        # Vorab-Checks: wenn Service nicht da ist, direkt klarer Hinweis
        pre_status = _service_status()
        if pre_status == "not-configured":
            return jsonify({
                "ok": False,
                "status": pre_status,
                "service": _SERVICE,
                "message": "AHPT ist nicht eingerichtet – bitte oben die Konfiguration ausfüllen und speichern.",
            })
        if pre_status == "not-installed":
            return jsonify({
                "ok": False,
                "status": pre_status,
                "service": _SERVICE,
                "message": f"systemd-Unit {_SERVICE}.service ist nicht installiert.",
            })
        try:
            env = os.environ.copy()
            env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            r = subprocess.run(
                ["systemctl", "--user", action, _SERVICE],
                capture_output=True, text=True, timeout=10, env=env)
            ok = r.returncode == 0
            status = _service_status()
            return jsonify({
                "ok": ok,
                "message": f"Service {action}: {'OK' if ok else (r.stderr.strip() or r.stdout.strip())}",
                "status": status,
                "service": _SERVICE,
            })
        except Exception as e:
            return jsonify({"ok": False, "message": str(e)}), 500

    @bp.route("/tools/relay-builder")
    def relay_builder():
        return render_template("ahpt_relay_builder.html")

    # ── Einrichtungs-Assistent (AHPT einrichten.py als Subprozess) ──
    # Startet den mitgelieferten AHPT-Assistenten im Hintergrund.
    # User oeffnet dessen URL im eigenen Browser, laeuft die 9 Schritte
    # durch (Webspace, Agent, Portal, Kopplung). Danach stoppt der User
    # den Assistenten wieder – der konfigurierte Agent laeuft als
    # systemd-user-service weiter und wird von Ilijas ahpt-settings-API
    # automatisch erkannt.
    _AHPT_ASSISTENT_DIR = "/opt/ilija-os/ahpt-agent"
    _AHPT_ASSISTENT_PY  = os.path.join(_AHPT_ASSISTENT_DIR, "einrichten.py")
    _AHPT_ASSISTENT_STATE = os.path.join(_AHPT_DIR, "assistent_state.json")
    _AHPT_ASSISTENT_PORT  = 8771

    def _assistent_state_load():
        try:
            with open(_AHPT_ASSISTENT_STATE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _assistent_state_save(d):
        os.makedirs(_AHPT_DIR, exist_ok=True)
        with open(_AHPT_ASSISTENT_STATE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _assistent_lebt(pid):
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ValueError, TypeError):
            return False

    def _lan_ip_oder_localhost():
        """Beste erreichbare Adresse fuer den Nutzer: LAN-IP wenn moeglich,
        sonst localhost."""
        try:
            import socket as _s
            with _s.socket(_s.AF_INET, _s.SOCK_DGRAM) as sk:
                sk.connect(("8.8.8.8", 53))
                return sk.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    @bp.route("/api/ahpt/assistent-status", methods=["GET"])
    def assistent_status():
        st = _assistent_state_load()
        pid = st.get("pid")
        if pid and _assistent_lebt(pid):
            return jsonify({"laeuft": True,
                            "pid":   pid,
                            "url":   st.get("url", ""),
                            "token": st.get("token", "")})
        return jsonify({"laeuft": False,
                        "installiert": os.path.exists(_AHPT_ASSISTENT_PY)})

    @bp.route("/api/ahpt/assistent-starten", methods=["POST"])
    def assistent_starten():
        if not os.path.exists(_AHPT_ASSISTENT_PY):
            return jsonify({"ok": False,
                            "error": f"AHPT-Dateien fehlen unter {_AHPT_ASSISTENT_DIR}. "
                                     "Update einspielen oder Installer erneut laufen lassen."}), 404
        # Schon laufend?
        st = _assistent_state_load()
        if st.get("pid") and _assistent_lebt(st["pid"]):
            return jsonify({"ok": True, "laeuft": True,
                            "pid": st["pid"], "url": st.get("url", ""),
                            "token": st.get("token", "")})
        # Neu starten – im Hintergrund, Log in ~/.ahpt/einrichten.log
        os.makedirs(_AHPT_DIR, exist_ok=True)
        log_pfad = os.path.join(_AHPT_DIR, "einrichten.log")
        try:
            with open(log_pfad, "a") as logf:
                logf.write(f"\n=== Assistent gestartet via Ilija-UI, "
                           f"{__import__('datetime').datetime.now().isoformat()} ===\n")
            proc = subprocess.Popen(
                ["python3", _AHPT_ASSISTENT_PY, "--port", str(_AHPT_ASSISTENT_PORT)],
                cwd=_AHPT_ASSISTENT_DIR,
                stdout=open(log_pfad, "a"), stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # ueberlebt SSH-/Flask-Abbrueche
            )
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
        # Token aus Log extrahieren (steht spaetestens nach ~2 Sek).
        # WICHTIG: Das Log wird im "a"-Modus geoeffnet und waechst bei jedem
        # Neustart. re.search() wuerde das ERSTE (alte) Token finden. Nur
        # das LETZTE Token im Log gehoert zum jetzt gestarteten Prozess.
        # Zusaetzlich: Nur Tokens suchen die NACH dem letzten "Assistent
        # gestartet"-Marker stehen, damit auch Edge-Cases sauber bleiben.
        import time as _t, re as _re
        token = ""
        for _ in range(20):
            _t.sleep(0.2)
            try:
                with open(log_pfad) as logf:
                    inhalt = logf.read()
                # Ab der letzten Start-Markierung lesen
                markers = list(_re.finditer(r"=== Assistent gestartet", inhalt))
                ab = markers[-1].start() if markers else 0
                treffer = _re.findall(r"\?t=([a-f0-9]+)", inhalt[ab:])
                if treffer:
                    token = treffer[-1]
                    break
            except Exception:
                pass
        if not token:
            return jsonify({"ok": False,
                            "error": "Assistent startet, aber Token nicht lesbar. "
                                     f"Pruefe {log_pfad}"}), 500
        ip = _lan_ip_oder_localhost()
        url = f"http://{ip}:{_AHPT_ASSISTENT_PORT}/?t={token}"
        _assistent_state_save({"pid": proc.pid, "token": token, "url": url,
                               "gestartet": __import__("datetime").datetime.now().isoformat()})
        return jsonify({"ok": True, "laeuft": True, "pid": proc.pid,
                        "url": url, "token": token})

    @bp.route("/api/ahpt/assistent-stoppen", methods=["POST"])
    def assistent_stoppen():
        st = _assistent_state_load()
        pid = st.get("pid")
        if pid and _assistent_lebt(pid):
            try:
                os.kill(int(pid), 15)  # SIGTERM
            except Exception:
                pass
        _assistent_state_save({})
        return jsonify({"ok": True})

    # ── Webspace-Paket: ZIP mit allem was auf den Hoster muss ─────
    # Kein User soll mehr relay.php, zwei .htaccess und einen Ordner einzeln
    # ueber FTP hochladen muessen. Ein ZIP, das man im Dateimanager des
    # Hosters hochlaedt und entpackt, erzeugt die exakt richtige Struktur.
    @bp.route("/api/ahpt/webspace-paket")
    def webspace_paket():
        quelle = "/opt/ilija-os/ahpt-agent"
        relay    = os.path.join(quelle, "relay.php")
        htbasis  = os.path.join(quelle, "htaccess-beispiel")
        htabl    = os.path.join(quelle, "htaccess-ablage-beispiel")
        webspace = os.path.join(quelle, "WEBSPACE.md")  # optional, mit rein wenn da
        fehlend = [p for p in (relay, htbasis, htabl) if not os.path.isfile(p)]
        if fehlend:
            return jsonify({
                "ok": False,
                "error": "AHPT-Dateien fehlen auf dem Server: "
                         + ", ".join(os.path.basename(p) for p in fehlend)
                         + ". Bitte das naechste Ilija-Update einspielen.",
            }), 404

        liesmich = (
            "AHPT Webspace-Paket\n"
            "===================\n"
            "\n"
            "Dieses ZIP enthaelt alles, was auf deinen Webspace muss, damit\n"
            "AHPT dort als Vermittler funktioniert.\n"
            "\n"
            "SO GEHT'S:\n"
            "----------\n"
            "1. Logge dich bei deinem Hoster ein (FTP-Programm oder Datei-\n"
            "   manager im Hoster-Backend, z.B. bei bplaced oder lima-city).\n"
            "2. Wechsle ins oeffentliche Verzeichnis deines Webspace --\n"
            "   dort, wo auch deine index.html stehen wuerde (meist 'htdocs',\n"
            "   'www' oder 'public_html').\n"
            "3. Lade dieses ZIP komplett dort hoch und entpacke es --\n"
            "   oder entpacke es lokal und uebertrage die drei Teile:\n"
            "       relay.php         ins Hauptverzeichnis\n"
            "       .htaccess         ins Hauptverzeichnis\n"
            "       ahpt/.htaccess    in einen NEUEN Unterordner 'ahpt/'\n"
            "4. Zurueck in Ilija: 'AHPT einrichten'-Assistent starten.\n"
            "   Dort traegst du die Basis-URL ein, z.B.\n"
            "       https://deinname.bplaced.net\n"
            "   Der Assistent prueft sofort ob der Webspace richtig antwortet.\n"
            "\n"
            "WAS DIE DATEIEN TUN:\n"
            "--------------------\n"
            "   relay.php         Der Vermittler, der Fragen und Antworten\n"
            "                     zwischenlagert. Nur PHP erforderlich,\n"
            "                     keine Datenbank, kein Cronjob.\n"
            "   .htaccess         Schuetzt relay_token.php / relay_state.php\n"
            "                     und schaltet mod_speling aus. Entscheidend\n"
            "                     fuer die Sicherheit -- unbedingt mit\n"
            "                     hochladen.\n"
            "   ahpt/.htaccess    Setzt CORS-Kopfzeilen damit das Portal\n"
            "                     auch von anderen Hosts darauf zugreifen\n"
            "                     kann (z.B. von deiner lokalen Festplatte).\n"
            "\n"
            "WICHTIG: Die .htaccess-Dateien beginnen mit einem Punkt und sind\n"
            "unter Windows standardmaessig unsichtbar. Im Explorer unter\n"
            "'Ansicht' -> 'Ausgeblendete Elemente' aktivieren falls sie fehlen.\n"
        )

        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(relay,   "relay.php")
            zf.write(htbasis, ".htaccess")
            zf.write(htabl,   "ahpt/.htaccess")
            zf.writestr("LIESMICH.txt", liesmich)
            if os.path.isfile(webspace):
                zf.write(webspace, "WEBSPACE.md")
        puffer.seek(0)
        return send_file(puffer,
                         mimetype="application/zip",
                         as_attachment=True,
                         download_name="ahpt-webspace.zip")

    @bp.route("/api/ahpt/webspace-doku")
    def webspace_doku():
        """Zeigt die WEBSPACE.md als lesbares Plain-Text an -- fuer die
        Direkt-Verlinkung aus der UI, ohne GitHub-Umweg."""
        pfad = "/opt/ilija-os/ahpt-agent/WEBSPACE.md"
        if not os.path.isfile(pfad):
            return "WEBSPACE.md noch nicht auf diesem System installiert. " \
                   "Nach dem naechsten Ilija-Update verfuegbar.", 404, {
                       "Content-Type": "text/plain; charset=utf-8"}
        with open(pfad, encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}

    app.register_blueprint(bp)
