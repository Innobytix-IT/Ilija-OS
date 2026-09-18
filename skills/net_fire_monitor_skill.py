"""
net_fire_monitor_skill.py – Net-Fire-Monitor Skill für Ilija

Gibt Ilija vollen Zugriff und volle Entscheidungsmacht über den
Net-Fire-Monitor. Ilija kann den Monitor steuern, IPs analysieren,
blockieren/freigeben, den Modus wechseln, die Whitelist pflegen
und den Status abfragen.

Installation:
    Diese Datei in den skills/-Ordner von Ilija kopieren.
    Beim ersten Aufruf wird der Pfad zum Net-Fire-Monitor abgefragt
    und dauerhaft gespeichert.
"""

import json
import socket
import subprocess
import platform
from pathlib import Path

# ── Skill-eigene Konfigurationsdatei (liegt neben diesem Skill) ───────────────
_SKILL_DIR        = Path(__file__).parent
_SKILL_CONFIG     = _SKILL_DIR / "net_fire_monitor_skill_config.json"


def _load_skill_config() -> dict:
    """Lädt die Skill-Konfiguration (Pfad zum Monitor etc.)."""
    if _SKILL_CONFIG.exists():
        return json.loads(_SKILL_CONFIG.read_text(encoding="utf-8"))
    return {}


def _save_skill_config(data: dict) -> None:
    """Speichert die Skill-Konfiguration."""
    _SKILL_CONFIG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_nfm_dir() -> Path | None:
    """Gibt den konfigurierten NFM-Pfad zurück, oder None wenn nicht gesetzt."""
    cfg = _load_skill_config()
    p = cfg.get("nfm_path", "")
    if p and Path(p).exists():
        return Path(p)
    return None


def _nfm_paths() -> dict | None:
    """
    Gibt alle relevanten Pfade zurück wenn NFM konfiguriert ist,
    sonst None.
    """
    nfm_dir = _get_nfm_dir()
    if not nfm_dir:
        return None
    return {
        "dir":      nfm_dir,
        "config":   nfm_dir / "net_fire_monitor_config.json",
        "log":      nfm_dir / "net_fire_monitor.log",
        "fw_log":   nfm_dir / "firewall.log",
        "ti_cache": nfm_dir / "threat_intel_cache.txt",
        "geoip":    nfm_dir / "GeoLite2-City.mmdb",
    }


_SETUP_HINWEIS = (
    "⚙️  Net-Fire-Monitor Skill ist noch nicht eingerichtet!\n"
    "Bitte zuerst den Pfad konfigurieren:\n"
    "  nfm_pfad_einrichten(pfad=\"C:\\\\Users\\\\...\\\\Net_fire_monitor_v1.0\")\n"
    "oder auf Linux/macOS:\n"
    "  nfm_pfad_einrichten(pfad=\"/home/.../Net_fire_monitor_v1.0\")"
)


def _load_config() -> dict:
    """Lädt die Net-Fire-Monitor Config."""
    paths = _nfm_paths()
    if not paths:
        raise RuntimeError(_SETUP_HINWEIS)
    if not paths["config"].exists():
        raise FileNotFoundError(f"Config nicht gefunden: {paths['config']}")
    return json.loads(paths["config"].read_text(encoding="utf-8"))


def _save_config(cfg: dict) -> None:
    """Speichert die Net-Fire-Monitor Config."""
    paths = _nfm_paths()
    if not paths:
        raise RuntimeError(_SETUP_HINWEIS)
    paths["config"].write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# EINRICHTUNG
# ══════════════════════════════════════════════════════════════════════════════

def nfm_pfad_einrichten(pfad: str) -> str:
    """
    Richtet den Pfad zum Net-Fire-Monitor ein. Nur einmalig nötig!
    Der Pfad wird dauerhaft gespeichert.
    Beispiel Windows : nfm_pfad_einrichten(pfad="C:\\Users\\Manuel\\Downloads\\net_monitor\\V2.1")
    Beispiel Linux   : nfm_pfad_einrichten(pfad="/home/manuel/net_fire_monitor")
    """
    p = Path(pfad.strip())

    if not p.exists():
        return (
            f"❌ Pfad existiert nicht: {p}\n"
            f"   Bitte den genauen Ordnerpfad angeben wo 'net_fire_monitor_v1.0.py' liegt."
        )

    # Prüfen ob NFM-Dateien vorhanden
    config_file = p / "net_fire_monitor_config.json"
    script_file = list(p.glob("net_fire_monitor*.py"))

    if not config_file.exists() and not script_file:
        return (
            f"⚠️  Warnung: In '{p}' wurde weder 'net_fire_monitor_config.json'\n"
            f"   noch 'net_fire_monitor_v*.py' gefunden.\n"
            f"   Ist das der richtige Ordner? Pfad trotzdem gespeichert.\n"
            f"   → Starte den Net-Fire-Monitor einmal damit die Config erstellt wird."
        )

    # Pfad speichern
    cfg = _load_skill_config()
    cfg["nfm_path"] = str(p)
    _save_skill_config(cfg)

    gefunden = []
    if config_file.exists():
        gefunden.append("✅ net_fire_monitor_config.json")
    if script_file:
        gefunden.append(f"✅ {script_file[0].name}")

    return (
        f"✅ Net-Fire-Monitor Skill erfolgreich eingerichtet!\n"
        f"📁 Pfad: {p}\n"
        f"{'chr(10)'.join(gefunden)}\n"
        f"\nDu kannst jetzt alle nfm_*-Funktionen verwenden.\n"
        f"Teste mit: nfm_status()"
    )


def nfm_pfad_anzeigen() -> str:
    """
    Zeigt den aktuell konfigurierten Pfad zum Net-Fire-Monitor.
    Beispiel: nfm_pfad_anzeigen()
    """
    cfg = _load_skill_config()
    p   = cfg.get("nfm_path", "")
    if not p:
        return _SETUP_HINWEIS
    exists = "✅ Pfad existiert" if Path(p).exists() else "❌ Pfad existiert NICHT mehr!"
    return f"📁 Konfigurierter NFM-Pfad:\n   {p}\n   {exists}"


# ══════════════════════════════════════════════════════════════════════════════
# STATUS & ÜBERSICHT
# ══════════════════════════════════════════════════════════════════════════════

def nfm_status() -> str:
    """
    Gibt den aktuellen Status des Net-Fire-Monitors zurück.
    Zeigt Modus, Schwellenwert, Whitelist-Größe, Threat-Intel-Cache usw.
    Beispiel: nfm_status()
    """
    paths = _nfm_paths()
    if not paths:
        return _SETUP_HINWEIS
    try:
        cfg = _load_config()

        ti_count = 0
        if paths["ti_cache"].exists():
            ti_count = sum(1 for _ in paths["ti_cache"].read_text().splitlines() if _.strip())

        last_alerts = []
        if paths["log"].exists():
            lines = paths["log"].read_text(encoding="utf-8", errors="ignore").splitlines()
            last_alerts = [l for l in lines if "WARNING" in l or "ERROR" in l][-3:]

        modus    = cfg.get("firewall_mode", "monitor").upper()
        wl_count = len(cfg.get("whitelist", []))
        bl_count = len(cfg.get("blacklist", []))

        result = (
            f"🔥 Net-Fire-Monitor Status\n"
            f"{'─' * 40}\n"
            f"Pfad             : {paths['dir']}\n"
            f"Firewall-Modus   : {modus}\n"
            f"Schwellenwert    : +{cfg.get('threshold', 20)}%\n"
            f"Messintervall    : {cfg.get('monitor_interval', 30)}s\n"
            f"Baseline-Dauer   : {cfg.get('average_period', 120)}s\n"
            f"Whitelist        : {wl_count} IP(s)\n"
            f"Blacklist        : {bl_count} IP(s)\n"
            f"Threat-Intel     : {'aktiv' if cfg.get('threat_intel_enabled') else 'inaktiv'} "
            f"({ti_count:,} bekannte Bedrohungen)\n"
            f"Auto-Block       : {'ja' if cfg.get('threat_intel_auto_block') else 'nein'}\n"
            f"E-Mail           : {'aktiv → ' + cfg.get('email_recipient', '') if cfg.get('email_enabled') else 'inaktiv'}\n"
            f"DNS-Auflösung    : {'ja' if cfg.get('resolve_dns') else 'nein'}\n"
            f"Port-Scan-Detect : {'ja' if cfg.get('detect_portscan') else 'nein'}\n"
        )

        if last_alerts:
            result += f"\n⚠️  Letzte Alarme:\n"
            for a in last_alerts:
                result += f"  {a}\n"
        else:
            result += f"\n✅ Keine aktuellen Alarme im Log.\n"

        return result

    except Exception as e:
        return f"❌ Fehler beim Lesen des Status: {e}"


def nfm_alarme_lesen(anzahl: int = 10) -> str:
    """
    Liest die letzten Alarme aus dem Net-Fire-Monitor Log.
    Beispiel: nfm_alarme_lesen(anzahl=20)
    """
    paths = _nfm_paths()
    if not paths:
        return _SETUP_HINWEIS
    try:
        if not paths["log"].exists():
            return "📋 Kein Log gefunden – läuft der Monitor?"
        lines  = paths["log"].read_text(encoding="utf-8", errors="ignore").splitlines()
        alarme = [l for l in lines if "WARNING" in l or "ERROR" in l]
        if not alarme:
            return "✅ Keine Alarme im Log."
        letzte = alarme[-anzahl:]
        return f"🚨 Letzte {len(letzte)} Alarme:\n" + "\n".join(letzte)
    except Exception as e:
        return f"❌ Fehler: {e}"


def nfm_firewall_log_lesen(anzahl: int = 10) -> str:
    """
    Liest die letzten Einträge aus dem Firewall-Log.
    Zeigt blockierte und freigegebene IPs.
    Beispiel: nfm_firewall_log_lesen(anzahl=20)
    """
    paths = _nfm_paths()
    if not paths:
        return _SETUP_HINWEIS
    try:
        if not paths["fw_log"].exists():
            return "📋 Kein Firewall-Log gefunden."
        lines = paths["fw_log"].read_text(encoding="utf-8", errors="ignore").splitlines()
        if not lines:
            return "✅ Firewall-Log ist leer – keine Aktionen bisher."
        letzte = lines[-anzahl:]
        return f"🛡️  Letzte {len(letzte)} Firewall-Aktionen:\n" + "\n".join(letzte)
    except Exception as e:
        return f"❌ Fehler: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# FIREWALL-MODUS STEUERN
# ══════════════════════════════════════════════════════════════════════════════

def nfm_modus_setzen(modus: str) -> str:
    """
    Setzt den Firewall-Modus des Net-Fire-Monitors.
    Mögliche Werte: monitor, confirm, auto
    - monitor : Nur beobachten, keine automatischen Eingriffe
    - confirm : E-Mail bei Alarm, manuell bestätigen
    - auto    : Verdächtige IPs sofort automatisch blockieren
    Beispiel: nfm_modus_setzen(modus="auto")
    """
    modus = modus.lower().strip()
    if modus not in ("monitor", "confirm", "auto"):
        return f"❌ Ungültiger Modus '{modus}'. Erlaubt: monitor, confirm, auto"
    try:
        cfg = _load_config()
        alter_modus = cfg.get("firewall_mode", "monitor")
        cfg["firewall_mode"] = modus
        _save_config(cfg)
        return (
            f"✅ Firewall-Modus geändert: {alter_modus.upper()} → {modus.upper()}\n"
            f"⚠️  Änderung wird beim nächsten Neustart des Monitors aktiv."
        )
    except Exception as e:
        return f"❌ Fehler: {e}"


def nfm_schwellenwert_setzen(prozent: int) -> str:
    """
    Setzt den Alarm-Schwellenwert in Prozent über der Baseline.
    Empfohlen: 15–50. Niedriger = sensibler, Höher = weniger Alarme.
    Beispiel: nfm_schwellenwert_setzen(prozent=30)
    """
    if not 5 <= prozent <= 500:
        return f"❌ Schwellenwert muss zwischen 5 und 500 liegen."
    try:
        cfg = _load_config()
        alt = cfg.get("threshold", 20)
        cfg["threshold"] = prozent
        _save_config(cfg)
        return f"✅ Schwellenwert geändert: {alt}% → {prozent}%"
    except Exception as e:
        return f"❌ Fehler: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# WHITELIST & BLACKLIST VERWALTEN
# ══════════════════════════════════════════════════════════════════════════════

def nfm_whitelist_anzeigen() -> str:
    """
    Zeigt alle IPs auf der Whitelist.
    Beispiel: nfm_whitelist_anzeigen()
    """
    try:
        cfg = _load_config()
        wl = cfg.get("whitelist", [])
        if not wl:
            return "📋 Whitelist ist leer."
        return f"✅ Whitelist ({len(wl)} IPs):\n" + "\n".join(f"  • {ip}" for ip in sorted(wl))
    except Exception as e:
        return f"❌ Fehler: {e}"


def nfm_whitelist_hinzufuegen(ip: str) -> str:
    """
    Fügt eine IP zur Whitelist hinzu (kein Alarm mehr für diese IP).
    Beispiel: nfm_whitelist_hinzufuegen(ip="160.79.104.10")
    """
    ip = ip.strip()
    try:
        cfg = _load_config()
        wl = cfg.get("whitelist", [])
        if ip in wl:
            return f"ℹ️  {ip} ist bereits auf der Whitelist."
        wl.append(ip)
        cfg["whitelist"] = wl
        _save_config(cfg)
        return f"✅ {ip} zur Whitelist hinzugefügt. (Whitelist: {len(wl)} IPs)"
    except Exception as e:
        return f"❌ Fehler: {e}"


def nfm_whitelist_entfernen(ip: str) -> str:
    """
    Entfernt eine IP von der Whitelist.
    Beispiel: nfm_whitelist_entfernen(ip="160.79.104.10")
    """
    ip = ip.strip()
    try:
        cfg = _load_config()
        wl = cfg.get("whitelist", [])
        if ip not in wl:
            return f"ℹ️  {ip} ist nicht auf der Whitelist."
        wl.remove(ip)
        cfg["whitelist"] = wl
        _save_config(cfg)
        return f"✅ {ip} von der Whitelist entfernt."
    except Exception as e:
        return f"❌ Fehler: {e}"


def nfm_blacklist_hinzufuegen(ip: str) -> str:
    """
    Fügt eine IP zur Blacklist hinzu (sofortiger Alarm bei dieser IP).
    Beispiel: nfm_blacklist_hinzufuegen(ip="1.2.3.4")
    """
    ip = ip.strip()
    try:
        cfg = _load_config()
        bl = cfg.get("blacklist", [])
        if ip in bl:
            return f"ℹ️  {ip} ist bereits auf der Blacklist."
        bl.append(ip)
        cfg["blacklist"] = bl
        _save_config(cfg)
        return f"✅ {ip} zur Blacklist hinzugefügt."
    except Exception as e:
        return f"❌ Fehler: {e}"


def nfm_blacklist_entfernen(ip: str) -> str:
    """
    Entfernt eine IP von der Blacklist.
    Beispiel: nfm_blacklist_entfernen(ip="1.2.3.4")
    """
    ip = ip.strip()
    try:
        cfg = _load_config()
        bl = cfg.get("blacklist", [])
        if ip not in bl:
            return f"ℹ️  {ip} ist nicht auf der Blacklist."
        bl.remove(ip)
        cfg["blacklist"] = bl
        _save_config(cfg)
        return f"✅ {ip} von der Blacklist entfernt."
    except Exception as e:
        return f"❌ Fehler: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# IP ANALYSIEREN
# ══════════════════════════════════════════════════════════════════════════════

def nfm_ip_analysieren(ip: str) -> str:
    """
    Analysiert eine IP-Adresse vollständig:
    Hostname (nslookup), Geo-IP, Threat-Intel-Status, Whitelist/Blacklist-Status.
    Ilija kann damit eigenständig entscheiden ob eine IP geblockt werden soll.
    Beispiel: nfm_ip_analysieren(ip="157.240.0.60")
    """
    paths = _nfm_paths()
    if not paths:
        return _SETUP_HINWEIS

    ip = ip.strip()
    result = [f"🔍 IP-Analyse: {ip}", "─" * 40]

    # Hostname via nslookup
    try:
        r = subprocess.run(["nslookup", ip], capture_output=True, text=True, timeout=5)
        hostname = "Nicht auflösbar"
        for line in r.stdout.splitlines():
            if "name =" in line.lower() or "name=" in line.lower():
                hostname = line.split("=")[-1].strip().rstrip(".")
                break
        result.append(f"Hostname  : {hostname}")
    except Exception:
        result.append("Hostname  : nslookup nicht verfügbar")

    # Geo-IP via GeoLite2 wenn vorhanden
    if paths["geoip"].exists():
        try:
            import geoip2.database
            with geoip2.database.Reader(str(paths["geoip"])) as reader:
                r = reader.city(ip)
                city    = r.city.name or ""
                country = r.country.name or ""
                iso     = r.country.iso_code or ""
                result.append(f"Geo-IP    : {city + ', ' if city else ''}{country} ({iso})")
        except Exception:
            result.append("Geo-IP    : –")
    else:
        result.append("Geo-IP    : GeoLite2-DB nicht vorhanden")

    # Threat-Intel prüfen
    if paths["ti_cache"].exists():
        bad_ips = set(paths["ti_cache"].read_text().splitlines())
        if ip in bad_ips:
            result.append("Bedrohung : ☠️  JA – in Threat-Intel-Liste!")
        else:
            result.append("Bedrohung : ✅ Vermutlich Nein (keine bekannte Bedrohung)")
    else:
        result.append("Bedrohung : ⚠️  Threat-Intel-Cache nicht verfügbar")

    # Whitelist / Blacklist Status
    try:
        cfg = _load_config()
        wl = cfg.get("whitelist", [])
        bl = cfg.get("blacklist", [])
        if ip in wl:
            result.append("Status    : ✅ Auf Whitelist (kein Alarm)")
        elif ip in bl:
            result.append("Status    : 🚫 Auf Blacklist (sofortiger Alarm)")
        else:
            result.append("Status    : ⚠️  Weder Whitelist noch Blacklist")
    except Exception:
        pass

    # Privat-IP Check
    try:
        import ipaddress
        addr = ipaddress.ip_address(ip)
        if addr.is_private:
            result.append("Typ       : 🏠 Private/LAN-IP")
        elif addr.is_global:
            result.append("Typ       : 🌍 Öffentliche IP")
    except Exception:
        pass

    return "\n".join(result)


# ══════════════════════════════════════════════════════════════════════════════
# DIREKTE FIREWALL-STEUERUNG
# ══════════════════════════════════════════════════════════════════════════════

def nfm_ip_blockieren(ip: str, grund: str = "Ilija-Entscheidung") -> str:
    """
    Blockiert eine IP direkt über die System-Firewall.
    Ilija kann diese Funktion autonom einsetzen wenn sie eine IP als gefährlich einstuft.
    Funktioniert auf Windows (netsh) und Linux (iptables).
    Beispiel: nfm_ip_blockieren(ip="1.2.3.4", grund="Verdächtiger Traffic")
    """
    ip = ip.strip()
    system = platform.system()

    # Sicherheitscheck: Private IPs niemals blockieren
    try:
        import ipaddress
        if ipaddress.ip_address(ip).is_private:
            return f"🛡️  Sicherheits-Schutz: Private/LAN-IPs werden nicht blockiert ({ip})"
    except Exception:
        pass

    try:
        if system == "Windows":
            rule_name = f"Ilija_Block_{ip}"
            cmd = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={rule_name}", "dir=in", "action=block",
                f"remoteip={ip}", "enable=yes"
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                return f"✅ IP {ip} blockiert (Windows netsh)\nGrund: {grund}"
            else:
                return f"❌ Block fehlgeschlagen: {r.stderr}\n(Als Administrator ausführen?)"

        elif system == "Linux":
            for chain in ("INPUT", "OUTPUT", "FORWARD"):
                subprocess.run(["iptables", "-I", chain, "-s", ip, "-j", "DROP"],
                               capture_output=True)
            return f"✅ IP {ip} blockiert (Linux iptables)\nGrund: {grund}"

        elif system == "Darwin":
            subprocess.run(["pfctl", "-t", "ilija_blocked", "-T", "add", ip],
                          capture_output=True)
            return f"✅ IP {ip} blockiert (macOS pfctl)\nGrund: {grund}"

        else:
            return f"❌ Unbekanntes System: {system}"

    except Exception as e:
        return f"❌ Fehler beim Blockieren: {e}"


def nfm_ip_freigeben(ip: str) -> str:
    """
    Hebt eine IP-Blockierung auf.
    Beispiel: nfm_ip_freigeben(ip="1.2.3.4")
    """
    ip = ip.strip()
    system = platform.system()
    try:
        if system == "Windows":
            rule_name = f"Ilija_Block_{ip}"
            # Auch Net-Fire-Monitor Regel entfernen
            for name in (rule_name, f"NetFireMon_Block_{ip}"):
                subprocess.run(
                    ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name}"],
                    capture_output=True
                )
            return f"✅ Firewall-Regel für {ip} entfernt."

        elif system == "Linux":
            for chain in ("INPUT", "OUTPUT", "FORWARD"):
                subprocess.run(["iptables", "-D", chain, "-s", ip, "-j", "DROP"],
                               capture_output=True)
            return f"✅ iptables-Regel für {ip} entfernt."

        elif system == "Darwin":
            subprocess.run(["pfctl", "-t", "ilija_blocked", "-T", "delete", ip],
                          capture_output=True)
            return f"✅ pfctl-Regel für {ip} entfernt."

    except Exception as e:
        return f"❌ Fehler: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# AUTONOME ENTSCHEIDUNG
# ══════════════════════════════════════════════════════════════════════════════

def nfm_autonome_entscheidung(ip: str) -> str:
    """
    Ilija analysiert eine IP vollständig und entscheidet AUTONOM ob sie
    blockiert, zur Whitelist hinzugefügt oder ignoriert werden soll.
    Gibt eine klare Empfehlung mit Begründung zurück.
    Beispiel: nfm_autonome_entscheidung(ip="157.240.0.60")
    """
    ip = ip.strip()

    # Analyse durchführen
    analyse = nfm_ip_analysieren(ip)

    # Entscheidungslogik
    entscheidung = ""
    begruendung  = ""

    # Threat-Intel positiv → sofort blockieren
    if "Threat-Intel-Liste" in analyse:
        entscheidung = "🚫 BLOCKIEREN"
        begruendung  = "IP ist in bekannten Threat-Intel-Listen gelistet."
        nfm_ip_blockieren(ip, grund="Autonome Ilija-Entscheidung: Threat-Intel-Treffer")

    # Private IP → Whitelist
    elif "Private/LAN-IP" in analyse:
        entscheidung = "✅ WHITELIST"
        begruendung  = "Private/LAN-IP – kein Sicherheitsrisiko."
        nfm_whitelist_hinzufuegen(ip)

    # Bekannte CDN/Cloud-Anbieter → Whitelist
    elif any(cdn in analyse.lower() for cdn in (
        "akamai", "cloudflare", "amazon", "google", "microsoft",
        "facebook", "whatsapp", "fbcdn", "apple", "anthropic",
        "netflix", "fastly", "cdn", "azure", "amazonaws"
    )):
        entscheidung = "✅ WHITELIST"
        begruendung  = "Bekannter CDN/Cloud-Anbieter – legitimer Traffic."
        nfm_whitelist_hinzufuegen(ip)

    # Hostname nicht auflösbar + öffentliche IP → Verdächtig
    elif "Nicht auflösbar" in analyse and "Öffentliche IP" in analyse:
        entscheidung = "⚠️  BEOBACHTEN"
        begruendung  = "Kein Hostname auflösbar. Empfehle manuelle Prüfung vor dem Blockieren."

    # Alles andere → ignorieren
    else:
        entscheidung = "ℹ️  IGNORIEREN"
        begruendung  = "Kein eindeutiger Handlungsbedarf erkannt."

    return (
        f"{analyse}\n"
        f"{'─' * 40}\n"
        f"🤖 Ilija-Entscheidung : {entscheidung}\n"
        f"📝 Begründung         : {begruendung}\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
# SKILL-REGISTRIERUNG
# ══════════════════════════════════════════════════════════════════════════════

AVAILABLE_SKILLS = [
    nfm_pfad_einrichten,
    nfm_pfad_anzeigen,
    nfm_status,
    nfm_alarme_lesen,
    nfm_firewall_log_lesen,
    nfm_modus_setzen,
    nfm_schwellenwert_setzen,
    nfm_whitelist_anzeigen,
    nfm_whitelist_hinzufuegen,
    nfm_whitelist_entfernen,
    nfm_blacklist_hinzufuegen,
    nfm_blacklist_entfernen,
    nfm_ip_analysieren,
    nfm_ip_blockieren,
    nfm_ip_freigeben,
    nfm_autonome_entscheidung,
]
