"""
cloud_routes.py – Ilija Cloud: lokaler Datei-Manager (ohne AHPT-Tunnel)
======================================================================
Die lokale Variante des AHPT-Cloud-Portals: greift DIREKT auf die gemeinsame
Ablage der Maschine zu (kein Relay, keine Noise-Krypto). Im LAN erreichbar,
damit Handy/Tablet/Zweit-PC über eine Portalseite an die Dateien kommen.

SICHERHEIT: Alle Operationen sind hart auf die Wurzel `~/Ilija-Ablage`
eingegrenzt (kein Ausbruch per ../, kein System-/Home-Zugriff, KEIN Terminal).
Der Zugang liegt hinter der Ilija-OS-Web-Anmeldung (ilija_os_auth).

Integration in web_server.py:
    from cloud_routes import register_cloud_routes
    register_cloud_routes(app)
"""
import os
import json
import shutil
from datetime import datetime
from flask import request, jsonify, send_file, abort

# Standard: Ilija Cloud folgt dem im DMS hinterlegten Archiv-Pfad (dynamisch),
# damit DMS + Cloud (+ AHPT) auf DASSELBE Verzeichnis zeigen. Der Nutzer kann
# aber einen EIGENEN Cloud-Pfad hinterlegen (dann getrennt vom DMS).
_HIER = os.path.dirname(os.path.abspath(__file__))
_DMS_CONFIG = os.path.join(_HIER, "data", "dms", "dms_config.json")
_CLOUD_CONFIG = os.path.join(_HIER, "data", "cloud", "cloud_config.json")
_FALLBACK = "/srv/ilija-ablage/DMS/archiv"


def _dms_archiv() -> str:
    try:
        with open(_DMS_CONFIG, encoding="utf-8") as f:
            p = (json.load(f) or {}).get("archiv_pfad", "")
        if p:
            return os.path.abspath(os.path.expanduser(p))
    except Exception:
        pass
    return _FALLBACK


def _eigener_pfad() -> str:
    try:
        with open(_CLOUD_CONFIG, encoding="utf-8") as f:
            return ((json.load(f) or {}).get("eigener_pfad", "") or "").strip()
    except Exception:
        return ""


def _root() -> str:
    eig = _eigener_pfad()
    root = os.path.abspath(os.path.expanduser(eig)) if eig else _dms_archiv()
    os.makedirs(root, exist_ok=True)
    return root


def _set_eigener_pfad(p: str) -> str:
    p = (p or "").strip()
    if p:
        os.makedirs(os.path.abspath(os.path.expanduser(p)), exist_ok=True)
    os.makedirs(os.path.dirname(_CLOUD_CONFIG), exist_ok=True)
    with open(_CLOUD_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"eigener_pfad": p}, f, ensure_ascii=False, indent=2)
    return _root()


def _safe(rel: str) -> str:
    """Löst rel gegen die Wurzel auf und verhindert Ausbruch."""
    base = os.path.realpath(_root())
    full = os.path.realpath(os.path.join(base, (rel or "").lstrip("/\\")))
    if full != base and not full.startswith(base + os.sep):
        abort(403)
    return full


def _rel(full: str) -> str:
    return os.path.relpath(full, _root()).replace(os.sep, "/").lstrip(".").lstrip("/")


def _typ_gruppe(name: str) -> str:
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for gruppe, exts in {
        "bild": {"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"},
        "pdf": {"pdf"},
        "text": {"txt", "md", "csv", "log", "json", "py", "js", "html", "css", "xml", "ini", "toml", "yml", "yaml"},
        "tabelle": {"xlsx", "xls", "ods"},
        "dokument": {"docx", "doc", "odt", "rtf"},
        "praesentation": {"pptx", "ppt", "odp"},
        "audio": {"mp3", "wav", "ogg", "flac"},
        "video": {"mp4", "webm", "mkv", "mov"},
    }.items():
        if ext in exts:
            return gruppe
    return "datei"


def register_cloud_routes(app):

    @app.route("/api/cloud/list")
    def cloud_list():
        rel = request.args.get("path", "")
        full = _safe(rel)
        if not os.path.isdir(full):
            return jsonify({"error": "Kein Verzeichnis"}), 404
        ordner, dateien = [], []
        for name in sorted(os.listdir(full), key=str.lower):
            if name.startswith("."):
                continue
            p = os.path.join(full, name)
            try:
                st = os.stat(p)
                eintrag = {"name": name, "pfad": _rel(p),
                           "geaendert": datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M")}
                if os.path.isdir(p):
                    eintrag["typ"] = "ordner"
                    ordner.append(eintrag)
                else:
                    eintrag["typ"] = "datei"
                    eintrag["gruppe"] = _typ_gruppe(name)
                    eintrag["groesse"] = st.st_size
                    dateien.append(eintrag)
            except OSError:
                continue
        return jsonify({"pfad": _rel(full), "eintraege": ordner + dateien})

    @app.route("/api/cloud/download")
    def cloud_download():
        full = _safe(request.args.get("path", ""))
        if not os.path.isfile(full):
            return jsonify({"error": "Datei nicht gefunden"}), 404
        return send_file(full, as_attachment=True, download_name=os.path.basename(full))

    @app.route("/api/cloud/preview")
    def cloud_preview():
        full = _safe(request.args.get("path", ""))
        if not os.path.isfile(full):
            return jsonify({"error": "Datei nicht gefunden"}), 404
        return send_file(full)  # inline (Browser entscheidet: anzeigen)

    @app.route("/api/cloud/mkdir", methods=["POST"])
    def cloud_mkdir():
        data = request.get_json() or {}
        name = (data.get("name") or "").strip().strip("/\\")
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            return jsonify({"error": "Ungültiger Ordnername"}), 400
        ziel = _safe(os.path.join(data.get("path", ""), name))
        try:
            os.makedirs(ziel, exist_ok=False)
        except FileExistsError:
            return jsonify({"error": "Existiert bereits"}), 400
        return jsonify({"ok": True, "pfad": _rel(ziel)})

    @app.route("/api/cloud/upload", methods=["POST"])
    def cloud_upload():
        rel = request.form.get("path", "")
        ziel_dir = _safe(rel)
        os.makedirs(ziel_dir, exist_ok=True)
        gespeichert = []
        for f in request.files.getlist("files"):
            if not f or not f.filename:
                continue
            name = os.path.basename(f.filename)
            f.save(_safe(os.path.join(rel, name)))
            gespeichert.append(name)
        return jsonify({"ok": True, "anzahl": len(gespeichert), "dateien": gespeichert})

    @app.route("/api/cloud/delete", methods=["POST"])
    def cloud_delete():
        full = _safe((request.get_json() or {}).get("path", ""))
        if full == os.path.realpath(_root()):
            return jsonify({"error": "Wurzel kann nicht gelöscht werden"}), 400
        if os.path.isdir(full):
            shutil.rmtree(full)
        elif os.path.isfile(full):
            os.remove(full)
        else:
            return jsonify({"error": "Nicht gefunden"}), 404
        return jsonify({"ok": True})

    @app.route("/api/cloud/rename", methods=["POST"])
    def cloud_rename():
        data = request.get_json() or {}
        full = _safe(data.get("path", ""))
        neu  = (data.get("name") or "").strip()
        if full == os.path.realpath(_root()):
            return jsonify({"error": "Wurzel kann nicht umbenannt werden"}), 400
        if not os.path.exists(full):
            return jsonify({"error": "Nicht gefunden"}), 404
        if not neu or "/" in neu or "\\" in neu or neu in (".", ".."):
            return jsonify({"error": "Ungueltiger Name"}), 400
        ziel = os.path.join(os.path.dirname(full), neu)
        if os.path.exists(ziel):
            return jsonify({"error": "Name bereits vergeben"}), 400
        # ziel darf nicht ausserhalb der Wurzel landen (zusaetzliche Sicherung)
        ziel_real = os.path.realpath(ziel)
        if not ziel_real.startswith(os.path.realpath(_root())):
            return jsonify({"error": "Pfad ausserhalb der Wurzel"}), 400
        os.rename(full, ziel)
        return jsonify({"ok": True})

    @app.route("/api/cloud/root")
    def cloud_root():
        return jsonify({"root": _root()})

    @app.route("/api/cloud/settings", methods=["GET", "POST"])
    def cloud_settings():
        if request.method == "POST":
            data = request.get_json() or {}
            try:
                root = _set_eigener_pfad(data.get("eigener_pfad", ""))
                return jsonify({"ok": True, "root": root,
                                "eigener_pfad": _eigener_pfad(),
                                "folgt_dms": not _eigener_pfad()})
            except Exception as e:
                return jsonify({"error": str(e)}), 400
        return jsonify({"root": _root(), "eigener_pfad": _eigener_pfad(),
                        "dms_archiv": _dms_archiv(), "folgt_dms": not _eigener_pfad()})
