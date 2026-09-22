#!/usr/bin/env python3
"""Ilija OS – Anwenden-Logik des Einrichtungsassistenten.

Nimmt das Ergebnis-Dict des Assistenten und schreibt die tatsächlichen
Konfigurationen: Ilija-.env (KI-Anbieter/Key oder lokales Modell oder keine),
OpenPhönix config.toml ([company] + [paths]), DMS-Pfade, AHPT-wurzel, legt die
gemeinsame Ablage an und schaltet die Dienste.

Alle Pfade zentral in PFADE – im ISO/für andere Nutzer anpassbar.
Mit dry=True wird nur protokolliert, nichts geschrieben.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess

HOME = os.path.expanduser("~")

PFADE = {
    "ilija_dir": f"{HOME}/Ilija-AI-Agent-Public-Edition/ilija_public_edition_v2.0",
    "erp_toml":  f"{HOME}/OpenPhoenix-ERP/OpenPhoenixERP_V3/config.toml",
    "ahpt_toml": f"{HOME}/.ahpt/agent.toml",
}
PFADE["ilija_env"] = f"{PFADE['ilija_dir']}/.env"
PFADE["dms_json"]  = f"{PFADE['ilija_dir']}/data/dms/dms_config.json"
PFADE["web_auth"]  = f"{HOME}/.config/ilija-os/web-auth"

KI_ENV_VARS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
               "GEMINI_API_KEY", "OLLAMA_MODEL"]


# --------------------------------------------------------------------------- #
# kleine, sichere Editoren
# --------------------------------------------------------------------------- #
def _env_setzen(pfad: str, aktiv: dict, dry: bool, log):
    """Setzt die Variablen aus `aktiv` (VAR->Wert) aktiv; alle anderen
    KI-Variablen werden auskommentiert. Rest der Datei bleibt unangetastet."""
    try:
        zeilen = open(pfad, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        zeilen = []
    aus = []
    gesehen = set()
    for ln in zeilen:
        m = re.match(r"\s*#?\s*([A-Z_]+)\s*=", ln)
        if m and m.group(1) in KI_ENV_VARS:
            var = m.group(1)
            if var in aktiv:
                if var not in gesehen:
                    aus.append(f"{var}={aktiv[var]}")
                    gesehen.add(var)
                # weitere Vorkommen fallen weg
            else:
                aus.append(ln if ln.lstrip().startswith("#") else "#" + ln)
        else:
            aus.append(ln)
    for var, wert in aktiv.items():
        if var not in gesehen:
            aus.append(f"{var}={wert}")
    log(f"  .env: aktiv={list(aktiv)} · andere KI-Keys auskommentiert")
    if not dry:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("\n".join(aus) + "\n")


def _env_zusatz(pfad: str, setzen: dict, deaktiv: list, dry: bool, log):
    """Setzt beliebige (Nicht-KI-)Variablen aktiv bzw. kommentiert `deaktiv` aus.
    Andere Zeilen bleiben unberührt."""
    try:
        zeilen = open(pfad, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        zeilen = []
    betroffen = set(setzen) | set(deaktiv)
    aus = []
    gesehen = set()
    for ln in zeilen:
        m = re.match(r"\s*#?\s*([A-Z_]+)\s*=", ln)
        if m and m.group(1) in betroffen:
            var = m.group(1)
            if var in setzen:
                if var not in gesehen:
                    aus.append(f"{var}={setzen[var]}")
                    gesehen.add(var)
            else:
                aus.append(ln if ln.lstrip().startswith("#") else "#" + ln)
        else:
            aus.append(ln)
    for var, wert in setzen.items():
        if var not in gesehen:
            aus.append(f"{var}={wert}")
    log(f"  Integrationen .env: setzen={list(setzen)} · aus={deaktiv}")
    if not dry:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("\n".join(aus) + "\n")


def _toml_setzen(pfad: str, werte: dict, dry: bool, log):
    """werte: {(section, key): value}. Strings werden zitiert, Zahlen roh."""
    try:
        zeilen = open(pfad, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        zeilen = []

    def fmt(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return '"%s"' % str(v).replace("\\", "\\\\").replace('"', '\\"')

    offen = set(werte.keys())
    aus = []
    sec = None
    for ln in zeilen:
        mh = re.match(r"\s*\[+(.+?)\]+\s*$", ln)  # [x] und [[x]] (Array-Tabellen)
        if mh:
            # beim Verlassen einer Section fehlende Keys ergänzen
            if sec is not None:
                for (s, k) in list(offen):
                    if s == sec:
                        aus.append(f"{k} = {fmt(werte[(s, k)])}")
                        offen.discard((s, k))
            sec = mh.group(1)
            aus.append(ln)
            continue
        mk = re.match(r"\s*([A-Za-z0-9_]+)\s*=", ln)
        if mk and sec is not None and (sec, mk.group(1)) in offen:
            k = mk.group(1)
            aus.append(f"{k} = {fmt(werte[(sec, k)])}")
            offen.discard((sec, k))
            continue
        aus.append(ln)
    # am Dateiende offene Keys der zuletzt offenen Section
    if sec is not None:
        for (s, k) in list(offen):
            if s == sec:
                aus.append(f"{k} = {fmt(werte[(s, k)])}")
                offen.discard((s, k))
    # ganz fehlende Sections anhängen
    rest_secs = {}
    for (s, k) in offen:
        rest_secs.setdefault(s, []).append(k)
    for s, ks in rest_secs.items():
        aus.append(f"[{s}]")
        for k in ks:
            aus.append(f"{k} = {fmt(werte[(s, k)])}")
    log(f"  {os.path.basename(pfad)}: {len(werte)} Schlüssel gesetzt")
    if not dry:
        with open(pfad, "w", encoding="utf-8") as f:
            f.write("\n".join(aus) + "\n")


def _json_setzen(pfad: str, updates: dict, dry: bool, log):
    try:
        daten = json.load(open(pfad, encoding="utf-8"))
    except Exception:
        daten = {}
    daten.update(updates)
    log(f"  {os.path.basename(pfad)}: {list(updates)}")
    if not dry:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(daten, f, indent=2, ensure_ascii=False)


def _dienst(aktion: str, name: str, dry: bool, log):
    log(f"  systemctl {aktion} {name}")
    if not dry:
        subprocess.run(["sudo", "systemctl", aktion, name],
                       capture_output=True, text=True)


# --------------------------------------------------------------------------- #
def anwenden(e: dict, dry: bool = False, log=print) -> None:
    baust = e.get("bausteine", {"ilija": True, "erp": True, "ahpt": False})
    wurzel = e.get("ablage_wurzel", f"{HOME}/Ilija-Ablage")
    erp_dok = f"{wurzel}/ERP/Dokumente"
    erp_bel = f"{wurzel}/ERP/Eingangsbelege"
    erp_xr  = f"{wurzel}/ERP/XRechnung"
    dms_arch = f"{wurzel}/DMS/archiv"
    dms_imp  = f"{wurzel}/DMS/import"

    # 1) gemeinsame Ablage anlegen
    log("• Gemeinsame Ablage")
    for d in (erp_dok, erp_bel, erp_xr, dms_arch, dms_imp):
        log(f"  mkdir -p {d}")
        if not dry:
            os.makedirs(d, exist_ok=True)

    # 2) Ilija-KI (.env)
    log("• Ilija-KI")
    modus = e.get("ki_modus", "keine")
    if modus == "cloud":
        _env_setzen(PFADE["ilija_env"], {e["env_var"]: e["api_key"]}, dry, log)
    elif modus == "lokal":
        _env_setzen(PFADE["ilija_env"], {"OLLAMA_MODEL": e.get("modell", "qwen2.5:7b")}, dry, log)
    else:
        _env_setzen(PFADE["ilija_env"], {}, dry, log)  # alle KI-Keys aus

    # 2b) Optionale Integrationen (FritzBox/Telegram/Web-Suche in .env;
    #     Kalender/WhatsApp brauchen einen interaktiven Login beim Erst-Start)
    integ = e.get("integrationen", {})
    if integ:
        log("• Integrationen")
        setzen, deaktiv = {}, []
        felder = {
            "fritzbox": ["SIP_SERVER", "SIP_USER", "SIP_PASSWORD"],
            "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"],
            "websuche": ["GOOGLE_SEARCH_API_KEY", "GOOGLE_SEARCH_CX"],
        }
        for name, vs in felder.items():
            cfg = integ.get(name, {})
            if cfg.get("an"):
                for v in vs:
                    if cfg.get(v):
                        setzen[v] = cfg[v]
            else:
                deaktiv += vs
        if setzen or deaktiv:
            _env_zusatz(PFADE["ilija_env"], setzen, deaktiv, dry, log)
        for name in ("kalender", "whatsapp"):
            if integ.get(name, {}).get("an"):
                log(f"  {name}: Anmeldung beim ersten Start (Browser-Login)")

    # 3) DMS-Pfade
    log("• DMS")
    _json_setzen(PFADE["dms_json"],
                 {"archiv_pfad": dms_arch, "import_pfad": dms_imp}, dry, log)

    # 4) OpenPhönix (Firmendaten + Pfade)
    if baust.get("erp", True):
        log("• OpenPhönix ERP")
        f = e.get("firma", {})
        werte = {
            ("paths", "documents"): erp_dok,
            ("paths", "belege"): erp_bel,
            ("paths", "xrechnung_output"): erp_xr,
        }
        abb = {"name": "name", "strasse": "address", "plz": "zip", "ort": "city",
               "telefon": "phone", "email": "email", "ustid": "tax_id",
               "leitweg": "leitweg_id"}
        for quelle, ziel in abb.items():
            if f.get(quelle):
                werte[("company", ziel)] = f[quelle]
        if f.get("plz") or f.get("ort"):
            werte[("company", "zip_city")] = f"{f.get('plz','')} {f.get('ort','')}".strip()
        if f.get("iban") or f.get("bic"):
            werte[("company", "bank_details")] = \
                f"IBAN: {f.get('iban','')} | BIC: {f.get('bic','')}".strip(" |")
        _toml_setzen(PFADE["erp_toml"], werte, dry, log)

    # 5) AHPT-wurzel: STANDARD = derselbe Ordner wie DMS-Archiv & Ilija Cloud,
    #    damit DMS-UI, Ilija Cloud (lokal) und AHPT Cloud (remote) auf DASSELBE
    #    Verzeichnis zeigen. Überschreibbar (agent.toml / Cloud-Einstellungen).
    #    ERP bleibt bewusst getrennt (sensibler) und wird NICHT über AHPT geteilt.
    if baust.get("ahpt", False):
        log("• AHPT")
        if os.path.exists(PFADE["ahpt_toml"]) or dry:
            _toml_setzen(PFADE["ahpt_toml"], {("dienst", "wurzel"): dms_arch}, dry, log)
            log("  (Relay + Handy-Kopplung folgen beim Erst-Start)")

    # 5b) Web-Login (getrennt vom DMS-Passwort, das Ilija in seinen Einstellungen
    #     verwaltet und das nur sensible DMS-Aktionen absichert)
    log("• Web-Login")
    auth_datei = PFADE["web_auth"]
    pw = e.get("web_passwort", "")
    if pw:
        h = hashlib.sha256(pw.encode("utf-8")).hexdigest()
        log("  Web-Login-Passwort gesetzt")
        if not dry:
            os.makedirs(os.path.dirname(auth_datei), exist_ok=True)
            with open(auth_datei, "w", encoding="utf-8") as f:
                f.write(h + "\n")
            os.chmod(auth_datei, 0o600)
    else:
        log("  ohne Web-Login (Oberfläche offen im Heimnetz)")
        if not dry and os.path.exists(auth_datei):
            os.remove(auth_datei)

    # 6) Dienste schalten
    log("• Dienste")
    if baust.get("ilija", True) and modus != "keine":
        _dienst("enable", "ilija.service", dry, log)
        _dienst("restart", "ilija.service", dry, log)
    else:
        _dienst("disable", "ilija.service", dry, log)
        _dienst("stop", "ilija.service", dry, log)
    # ERP ist eine Desktop-App (kein Dienst); AHPT-Dienst erst nach Kopplung.
    log("Fertig.")


if __name__ == "__main__":
    beispiel = {
        "ki_modus": "cloud", "provider": "gemini",
        "env_var": "GOOGLE_API_KEY", "api_key": "TESTKEY",
        "bausteine": {"ilija": True, "erp": True, "ahpt": True},
        "ablage_wurzel": f"{HOME}/Ilija-Ablage",
        "firma": {"name": "Innobytix-IT", "strasse": "Musterstr. 1",
                  "plz": "79098", "ort": "Freiburg", "ustid": "DE123456789",
                  "telefon": "+49 761 1", "email": "a@b.de",
                  "iban": "DE89...", "bic": "COBADEFF", "leitweg": ""},
    }
    import sys
    anwenden(beispiel, dry="--echt" not in sys.argv)

def _auto_update_einrichten(e: dict, ilija_dir: str, dry: bool, log) -> None:
    """Crontab, Update-Skript und sudoers fuer automatische Updates."""
    import subprocess
    cfg = e.get("auto_update", {"enabled": True, "time": "03:00"})
    enabled = cfg.get("enabled", True)
    time_str = cfg.get("time", "03:00")
    update_script = os.path.join(HOME, "ilija-update.sh")
    update_json = os.path.join(ilija_dir, "data", "update_settings.json")

    # update_settings.json fuer die Web-UI
    log("• Auto-Update Einstellungen")
    _json_setzen(update_json, {"auto_update_enabled": enabled, "update_time": time_str}, dry, log)

    if not enabled:
        log("  Auto-Update deaktiviert – kein Cron-Job.")
        return

    h, m = time_str.split(":")

    # Update-Skript erstellen
    skript = f"""#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
echo "=== Ilija OS Update gestartet ==="

echo "--- System-Update (apt) ---"
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get autoremove -y -qq
echo "--- System-Update abgeschlossen ---"

echo "--- Ilija OS Update (GitHub) ---"
git config --global --add safe.directory {ilija_dir} 2>/dev/null || true
cd {ilija_dir}
git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
    git pull origin main --quiet
    source {ilija_dir}/venv/bin/activate
    pip install -r {ilija_dir}/requirements.txt --quiet
    sudo systemctl restart ilija 2>/dev/null || true
    echo "--- Ilija OS aktualisiert ---"
else
    echo "--- Ilija OS ist aktuell (kein Update noetig) ---"
fi
echo "=== Fertig ==="
"""
    log(f"  Update-Skript: {update_script}")
    if not dry:
        with open(update_script, "w") as f:
            f.write(skript)
        os.chmod(update_script, 0o755)

    # Sudoers-Regeln
    current_user = os.environ.get("USER", os.environ.get("LOGNAME", ""))
    if current_user:
        for name, cmd in [("ilija-apt", "/usr/bin/apt-get"),
                          ("ilija-restart", "/bin/systemctl restart ilija")]:
            rule = f"{current_user} ALL=(ALL) NOPASSWD: {cmd}\n"
            log(f"  sudoers: {name}")
            if not dry:
                try:
                    subprocess.run(
                        ["sudo", "tee", f"/etc/sudoers.d/{name}"],
                        input=rule, text=True, capture_output=True, check=True
                    )
                    subprocess.run(
                        ["sudo", "chmod", "440", f"/etc/sudoers.d/{name}"],
                        capture_output=True, check=True
                    )
                except Exception as ex:
                    log(f"  ⚠ sudoers {name} konnte nicht gesetzt werden: {ex}")

        # Falls dedizierter Dienst-User 'ilija' existiert (ISO-Betrieb),
        # darf er das Update-Script als Installer-User ausführen (Web-UI-Button).
        import shutil
        if not dry and shutil.which("id") and current_user != "ilija":
            import subprocess as _sp2
            if _sp2.run(["id", "ilija"], capture_output=True).returncode == 0:
                rule2 = f"ilija ALL=({current_user}) NOPASSWD: /bin/bash {update_script}\n"
                try:
                    _sp2.run(["sudo", "tee", "/etc/sudoers.d/ilija-update"],
                             input=rule2, text=True, capture_output=True, check=True)
                    _sp2.run(["sudo", "chmod", "440", "/etc/sudoers.d/ilija-update"],
                             capture_output=True, check=True)
                    log(f"  sudoers: ilija-update (Dienst-User → {current_user})")
                except Exception as ex:
                    log(f"  ⚠ sudoers ilija-update konnte nicht gesetzt werden: {ex}")

    # Cron-Job
    log(f"  Cron-Job: taeglich um {h}:{m} Uhr")
    if not dry:
        try:
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            lines = [l for l in result.stdout.splitlines() if "ilija-update.sh" not in l]
            lines.append(f"{int(m)} {int(h)} * * * {update_script} >> {HOME}/ilija-update.log 2>&1")
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
        except Exception as ex:
            log(f"  ⚠ Cron-Job konnte nicht gesetzt werden: {ex}")
