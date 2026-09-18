"""
DMS-Routen v3 für web_server.py
================================
- Passwortgeschütztes Löschen
- Robuste Import-Behandlung
- Model-API
"""

import os
import json
import hashlib
from pathlib import Path
from flask import jsonify, request, send_file, render_template, abort
from werkzeug.utils import secure_filename

DMS_BASE    = os.path.abspath("data/dms")
CONFIG_FILE = os.path.join(DMS_BASE, "dms_config.json")

ALLOWED_EXTENSIONS = {
    "pdf","docx","doc","xlsx","xls","xlsm","txt","csv","md","rtf",
    "jpg","jpeg","png","webp","tiff","tif","bmp","heic","heif",
    "odt","ods","odp","pptx","ppt",
}
IMAGE_EXTS = {"jpg","jpeg","png","webp","tiff","tif","bmp","heic","gif"}


def _get_cfg() -> dict:
    defaults = {
        "archiv_pfad":    os.path.join(DMS_BASE, "archiv"),
        "import_pfad":    os.path.join(DMS_BASE, "import"),
        "passwort_hash":  "",
        "passwort_aktiv": False,
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                defaults.update(json.load(f))
    except Exception:
        pass
    return defaults

def _save_cfg(cfg):
    os.makedirs(DMS_BASE, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def _check_pw(passwort: str) -> bool:
    cfg = _get_cfg()
    if not cfg.get("passwort_aktiv") or not cfg.get("passwort_hash"):
        return True
    return hashlib.sha256(passwort.encode()).hexdigest() == cfg["passwort_hash"]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def register_dms_routes(app):

    @app.route("/dms")
    def dms_index():
        return render_template("dms.html")

    # ── Stats ─────────────────────────────────────────────────
    @app.route("/api/dms/stats")
    def dms_stats_api():
        try:
            from skills.dms import dms_stats
            return jsonify(dms_stats())
        except Exception as e:
            return jsonify({"error": str(e), "gesamt": 0, "groesse_mb": 0,
                            "kategorien": {}, "import_count": 0, "passwort_aktiv": False}), 200

    # ── Tree ──────────────────────────────────────────────────
    @app.route("/api/dms/tree")
    def dms_tree_api():
        try:
            from skills.dms import dms_archiv_baum
            return jsonify(dms_archiv_baum())
        except Exception as e:
            return jsonify([]), 200

    # ── Import list ───────────────────────────────────────────
    @app.route("/api/dms/import-list")
    def dms_import_list():
        cfg        = _get_cfg()
        import_dir = cfg["import_pfad"]
        os.makedirs(import_dir, exist_ok=True)
        try:
            dateien = [
                {
                    "name":    f,
                    "groesse": os.path.getsize(os.path.join(import_dir, f)),
                    "ext":     Path(f).suffix.lower().lstrip("."),
                }
                for f in os.listdir(import_dir)
                if os.path.isfile(os.path.join(import_dir, f)) and allowed_file(f)
            ]
            return jsonify(sorted(dateien, key=lambda x: x["name"]))
        except Exception as e:
            return jsonify([]), 200

    # ── Upload ────────────────────────────────────────────────
    @app.route("/api/dms/upload", methods=["POST"])
    def dms_upload():
        cfg        = _get_cfg()
        import_dir = cfg["import_pfad"]
        os.makedirs(import_dir, exist_ok=True)

        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "Keine Dateien"}), 400

        hochgeladen, fehler = [], []
        for file in files:
            if not file.filename or not allowed_file(file.filename):
                if file.filename:
                    fehler.append(f"{file.filename}: Format nicht unterstützt")
                continue
            try:
                filename = secure_filename(file.filename)
                ziel     = os.path.join(import_dir, filename)
                if os.path.exists(ziel):
                    stem, ext = Path(filename).stem, Path(filename).suffix
                    i = 1
                    while os.path.exists(ziel):
                        ziel = os.path.join(import_dir, f"{stem}_{i}{ext}")
                        i   += 1
                file.save(ziel)
                hochgeladen.append(os.path.basename(ziel))
            except Exception as e:
                fehler.append(f"{file.filename}: {e}")

        return jsonify({"hochgeladen": hochgeladen, "fehler": fehler, "anzahl": len(hochgeladen)})

    # ── Sort ──────────────────────────────────────────────────
    @app.route("/api/dms/sort", methods=["POST"])
    def dms_sort():
        try:
            from skills.dms import dms_einsortieren
            from providers import select_provider
            _, provider = select_provider("auto")
            ergebnis    = dms_einsortieren(provider=provider)
            return jsonify({"ergebnis": ergebnis})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Search ────────────────────────────────────────────────
    @app.route("/api/dms/search")
    def dms_search():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify([])
        cfg        = _get_cfg()
        archiv_dir = cfg["archiv_pfad"]
        try:
            treffer = []
            for root, _, files in os.walk(archiv_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), archiv_dir).replace("\\", "/")
                    if q.lower() in rel.lower():
                        voll = os.path.join(root, f)
                        treffer.append({
                            "pfad":    rel,
                            "name":    f,
                            "groesse": os.path.getsize(voll),
                            "ext":     Path(f).suffix.lower().lstrip("."),
                        })
            return jsonify(sorted(treffer, key=lambda x: x["pfad"])[:100])
        except Exception as e:
            return jsonify([]), 200

    # ── Download ──────────────────────────────────────────────
    @app.route("/api/dms/download")
    def dms_download():
        pfad       = request.args.get("pfad", "")
        cfg        = _get_cfg()
        archiv_dir = cfg["archiv_pfad"]
        voll       = os.path.abspath(os.path.join(archiv_dir, pfad))
        if not voll.startswith(os.path.abspath(archiv_dir)):
            abort(403)
        if not os.path.isfile(voll):
            abort(404)
        return send_file(voll, as_attachment=True)

    # ── Preview (Archiv) ──────────────────────────────────────
    @app.route("/api/dms/preview")
    def dms_preview():
        pfad       = request.args.get("pfad", "")
        cfg        = _get_cfg()
        archiv_dir = cfg["archiv_pfad"]
        voll       = os.path.abspath(os.path.join(archiv_dir, pfad))
        if not voll.startswith(os.path.abspath(archiv_dir)):
            abort(403)
        if not os.path.isfile(voll):
            abort(404)
        ext = Path(voll).suffix.lower().lstrip(".")
        mime_img = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
                    "webp":"image/webp","gif":"image/gif","tiff":"image/tiff",
                    "tif":"image/tiff","bmp":"image/bmp"}
        if ext in mime_img:
            return send_file(voll, mimetype=mime_img[ext])
        if ext == "pdf":
            return send_file(voll, mimetype="application/pdf", as_attachment=False)
        abort(415)

    # ── Preview (Import) ──────────────────────────────────────
    @app.route("/api/dms/import-preview")
    def dms_import_preview():
        name       = request.args.get("name", "")
        cfg        = _get_cfg()
        import_dir = cfg["import_pfad"]
        voll       = os.path.abspath(os.path.join(import_dir, secure_filename(name)))
        if not voll.startswith(os.path.abspath(import_dir)):
            abort(403)
        if not os.path.isfile(voll):
            abort(404)
        ext = Path(voll).suffix.lower().lstrip(".")
        mime_img = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
                    "webp":"image/webp","bmp":"image/bmp","tiff":"image/tiff","tif":"image/tiff"}
        if ext in mime_img:
            return send_file(voll, mimetype=mime_img[ext])
        if ext == "pdf":
            return send_file(voll, mimetype="application/pdf", as_attachment=False)
        abort(415)

    # ── Delete Archiv (mit Passwort) ──────────────────────────
    @app.route("/api/dms/delete-archive", methods=["DELETE"])
    def dms_delete_archive():
        data     = request.get_json() or {}
        pfad     = data.get("pfad", "")
        passwort = data.get("passwort", "")

        if not pfad:
            return jsonify({"error": "Kein Pfad angegeben"}), 400

        # Passwortprüfung
        if not _check_pw(passwort):
            return jsonify({"error": "Falsches Passwort", "pw_required": True}), 403

        try:
            from skills.dms import dms_loeschen
            ergebnis = dms_loeschen(pfad, passwort)
            if ergebnis.startswith("❌"):
                return jsonify({"error": ergebnis}), 400
            return jsonify({"ok": True, "message": ergebnis})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Delete Import ─────────────────────────────────────────
    @app.route("/api/dms/delete", methods=["DELETE"])
    def dms_delete_import():
        data       = request.get_json() or {}
        name       = secure_filename(data.get("name", ""))
        cfg        = _get_cfg()
        import_dir = cfg["import_pfad"]
        if not name:
            return jsonify({"error": "Kein Dateiname"}), 400
        pfad = os.path.join(import_dir, name)
        if not os.path.isfile(pfad):
            return jsonify({"error": "Datei nicht gefunden"}), 404
        os.remove(pfad)
        return jsonify({"ok": True})

    # ── Verschieben ───────────────────────────────────────────
    @app.route("/api/dms/move", methods=["POST"])
    def dms_move():
        data                = request.get_json() or {}
        pfad                = data.get("pfad", "").strip()
        neue_kategorie      = data.get("kategorie", "").strip()
        neue_unterkategorie = data.get("unterkategorie", "").strip()
        passwort            = data.get("passwort", "")
        if not pfad or not neue_kategorie:
            return jsonify({"ok": False, "error": "Pfad und Kategorie erforderlich"}), 400
        try:
            from skills.dms import dms_verschieben
            return jsonify(dms_verschieben(pfad, neue_kategorie, neue_unterkategorie, passwort))
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500



    # ── Settings GET ──────────────────────────────────────────
    @app.route("/api/dms/settings", methods=["GET"])
    def dms_settings_get():
        cfg = _get_cfg()
        return jsonify({
            "archiv_pfad":    cfg["archiv_pfad"],
            "import_pfad":    cfg["import_pfad"],
            "passwort_aktiv": cfg.get("passwort_aktiv", False),
        })

    # ── Settings POST ─────────────────────────────────────────
    @app.route("/api/dms/settings", methods=["POST"])
    def dms_settings_set():
        data = request.get_json() or {}
        try:
            from skills.dms import dms_pfad_setzen
            ergebnis = dms_pfad_setzen(
                archiv_pfad  = data.get("archiv_pfad", ""),
                import_pfad  = data.get("import_pfad", ""),
                passwort     = data.get("passwort", ""),
                passwort_neu = data.get("passwort_neu", ""),
            )
            if ergebnis.startswith("❌"):
                return jsonify({"error": ergebnis}), 403
            return jsonify({"ok": True, "message": ergebnis})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/dms/settings/remove-password", methods=["POST"])
    def dms_remove_password():
        data = request.get_json() or {}
        try:
            from skills.dms import dms_passwort_entfernen
            ergebnis = dms_passwort_entfernen(data.get("passwort", ""))
            if ergebnis.startswith("❌"):
                return jsonify({"error": ergebnis}), 403
            return jsonify({"ok": True, "message": ergebnis})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Model API ─────────────────────────────────────────────
    @app.route("/api/model", methods=["GET"])
    def get_model():
        try:
            from providers import get_available_providers
            available = get_available_providers()
            cfg = {}
            try:
                with open("models_config.json") as f:
                    cfg = json.load(f)
            except Exception:
                pass
            return jsonify({
                "current_provider": cfg.get("default_provider", "auto"),
                "available":        available,
                "models":           cfg.get("models", {}),
            })
        except Exception as e:
            return jsonify({"error": str(e), "available": [], "current_provider": "auto"}), 200

    @app.route("/api/model", methods=["POST"])
    def set_model():
        data = request.get_json() or {}
        try:
            cfg = {}
            try:
                with open("models_config.json") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {"default_provider": "auto", "models": {}}

            if "provider" in data:
                cfg["default_provider"] = data["provider"]
            if "model_name" in data and "provider" in data:
                cfg.setdefault("models", {})[data["provider"]] = data["model_name"]

            with open("models_config.json", "w") as f:
                json.dump(cfg, f, indent=2)

            # Kernel-Provider neu setzen falls möglich
            try:
                from web_server import kernel, kernel_lock
                if kernel and "provider" in data:
                    with kernel_lock:
                        kernel.switch_provider(data["provider"])
            except Exception:
                pass

            return jsonify({"ok": True, "config": cfg})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
