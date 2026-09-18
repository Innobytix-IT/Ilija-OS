"""
fritzbox_skill.py – VoIP-Telefonie-Skill für Ilija
Basis: Fundament_FritzboxSkill.py (funktionierender TCP-SIP-Stack)

Ilija kann damit:
  - Anrufe tätigen (Rufnummer oder Name aus Fritzbox-Telefonbuch)
  - Eingehende Anrufe annehmen (Auto-Answer)
  - Laufende Gespräche beenden
  - Fritzbox-Kontakte abfragen
  - Telefonstatus prüfen

.env Einträge:
    SIP_SERVER=192.168.x.x      ← IP der Fritzbox
    SIP_PORT=5060
    SIP_USER=ilija2026           ← Benutzername des IP-Telefons in Fritzbox
    SIP_PASSWORD=deinpasswort
    SIP_MY_IP=192.168.x.x       ← lokale PC-IP (ipconfig)
    SIP_MIC_ID=2                 ← optionale Mikrofon-ID (siehe Konsolenausgabe)

Fritzbox-Einrichtung:
    fritz.box → Telefonie → Telefoniegeräte → Neues Gerät → IP-Telefon
    Benutzername + Passwort vergeben → in .env eintragen
"""

import os
import re
import uuid
import time
import socket
import hashlib
import logging
import pathlib
import threading
import audioop
import pyaudio

from dotenv import load_dotenv
from typing import Optional

logger = logging.getLogger(__name__)

# ── .env laden ────────────────────────────────────────────────
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

SIP_SERVER  = os.getenv("SIP_SERVER",  "fritz.box")
SIP_PORT    = int(os.getenv("SIP_PORT", "5060"))
SIP_USER    = os.getenv("SIP_USER",    "")
SIP_PASSWORD= os.getenv("SIP_PASSWORD","")
SIP_MY_IP   = os.getenv("SIP_MY_IP",   "")
MIC_ID      = int(os.getenv("SIP_MIC_ID", "0")) if os.getenv("SIP_MIC_ID") else None

# ── Globaler Zustand ──────────────────────────────────────────
_phone: Optional["FritzboxPhone"] = None
_phone_lock = threading.Lock()
_call_end_callback = None

# Pending Push: Buchungsdetails die nach dem Gespräch zum Provider gesendet werden
_pending_push: Optional[dict] = None


def set_call_end_callback(fn):
    """Registriert eine Funktion die beim Gesprächsende gerufen wird."""
    global _call_end_callback
    _call_end_callback = fn


def registriere_post_call_push(titel: str, datum: str, uhrzeit_von: str,
                                uhrzeit_bis: str, kontaktinfos: str = "",
                                beschreibung: str = ""):
    """Merkt sich eine Buchung für den Push nach dem Gesprächsende."""
    global _pending_push
    _pending_push = {
        "titel":       titel,
        "datum":       datum,
        "uhrzeit_von": uhrzeit_von,
        "uhrzeit_bis": uhrzeit_bis,
        "kontakt":     kontaktinfos,
        "beschreibung": beschreibung,
    }


def _flush_pending_push():
    """Schickt ausstehende Buchung an den konfigurierten Provider (Hintergrund-Thread)."""
    global _pending_push
    eintrag = _pending_push
    _pending_push = None
    if not eintrag:
        return
    try:
        from skills.kalender_sync_skill import push_termin_zu_provider
        ergebnis = push_termin_zu_provider(
            eintrag["titel"], eintrag["datum"],
            eintrag["uhrzeit_von"], eintrag["uhrzeit_bis"],
            eintrag["kontakt"], eintrag["beschreibung"],
        )
        logger.info(f"[KalenderSync] Post-Call Push: {ergebnis}")
    except Exception as e:
        logger.warning(f"[KalenderSync] Post-Call Push fehlgeschlagen: {e}")

# ── STT-Modell-Cache (verhindert wiederholtes Laden bei jedem Audio-Snippet) ──
_WHISPER_MODEL = None
_WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL", "base").strip().lower()
# Wahl: "tiny" (schnell, ungenau), "base" (default), "small" (besser), "medium" (sehr gut, langsam)

# Domain-Prompt für besseres Verständnis deutscher Namen + Telefon-Kontext
_STT_PROMPT_DE = (
    "Telefongespräch auf Deutsch mit Ilija, einem KI-Assistenten für "
    "Terminvereinbarungen. "
    "Typische Anliegen: Öffnungszeiten, Sprechzeiten, geöffnet, "
    "Termin vereinbaren, Termin buchen, Termin absagen, Termin stornieren, "
    "meine Termine abfragen, Nachricht hinterlassen, Notiz hinterlassen. "
    "Der Anrufer nennt deutsche Familiennamen wie "
    "Müller, Schmidt, Schneider, Fischer, Weber, Mayer, Wagner, Becker, "
    "Schulz, Hoffmann, Bauer, Wolf, Lehmann, Krüger, Hartmann, Lange, "
    "Werner, Schwarz, Krause, Meier. Wochentage: Montag, Dienstag, Mittwoch, "
    "Donnerstag, Freitag. Uhrzeiten: zehn Uhr, halb elf, vierzehn Uhr. "
    "Häufige Antworten: ja, nein, gerne, bitte, danke, nein danke. "
    "Telefonnummern werden Ziffer für Ziffer genannt."
)


def _load_whisper_model():
    """Lädt das Whisper-Modell EINMAL beim ersten Aufruf und cached es."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        try:
            import whisper, warnings
            warnings.filterwarnings("ignore")
            logger.info(f"[STT] Lade Whisper-Modell '{_WHISPER_MODEL_NAME}' ...")
            _WHISPER_MODEL = whisper.load_model(_WHISPER_MODEL_NAME, device="cpu")
            logger.info(f"[STT] Whisper-Modell '{_WHISPER_MODEL_NAME}' geladen")
        except Exception as e:
            logger.error(f"[STT] Modell-Load-Fehler: {e}")
            _WHISPER_MODEL = None
    return _WHISPER_MODEL


# ── Hilfsfunktionen ───────────────────────────────────────────
def _get_header_val(response: str, key: str) -> Optional[str]:
    """Liest einen Wert aus einem SIP-Header (key="value" Format)."""
    match = re.search(f'{key}="?([^" \\r\\n;]+)"?', response, re.IGNORECASE)
    return match.group(1) if match else None


def _get_full_header(data: str, key: str) -> str:
    """Liest den vollständigen Wert eines SIP-Headers (für Via/From/To)."""
    m = re.search(rf'^{re.escape(key)}:\s*(.+)$', data,
                  re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _eigene_ip() -> str:
    """Ermittelt die lokale IP automatisch wenn nicht in .env gesetzt."""
    if SIP_MY_IP:
        return SIP_MY_IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((SIP_SERVER, SIP_PORT))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


# ── Fritzbox-Telefonbuch ───────────────────────────────────────
def fritzbox_kontakte() -> dict:
    """Lädt Kontakte aus dem Fritzbox-Telefonbuch. Gibt {name: nummer} zurück."""
    try:
        from fritzconnection.lib.fritzphonebook import FritzPhonebook
        pb = FritzPhonebook(address=SIP_SERVER)
        kontakte = {}
        for pb_id in pb.list_phonebooks():
            for entry in pb.get_all_persons(pb_id):
                for number in entry.numbers:
                    kontakte[entry.name.lower()] = number.number
        return kontakte
    except Exception as e:
        logger.warning(f"[Fritzbox] Kontakte laden fehlgeschlagen: {e}")
        return {}


def nummer_aufloesen(name_oder_nr: str) -> str:
    """Gibt Rufnummer zurück – direkt oder per Kontaktsuche."""
    bereinigt = name_oder_nr.strip()
    if all(c in "0123456789+*#()- " for c in bereinigt):
        return bereinigt.replace(" ", "").replace("-", "")
    kontakte = fritzbox_kontakte()
    suche = bereinigt.lower()
    for name, nummer in kontakte.items():
        if suche in name or name in suche:
            logger.info(f"[Fritzbox] Kontakt gefunden: {name} → {nummer}")
            return nummer
    return bereinigt


# ── Kern: SIP-Telefon (basierend auf Fundament_FritzboxSkill) ─
class FritzboxPhone:
    """
    Schlanker SIP-Client über TCP für die Fritzbox.
    Kein pyVoIP — direkter Socket-Code wie in Fundament_FritzboxSkill.py.
    """

    def __init__(self):
        self.my_ip = _eigene_ip()
        self.my_sip_port = 5060  # Wird beim Verbinden überschrieben

        # Mutex: verhindert gleichzeitige RTP-Sends aus mehreren Threads.
        # Ohne Lock kämpfen TTS-Thread und Bestätigungston-Thread um denselben
        # RTP-Stream → Fritzbox verwirft die kollidierten Pakete → Stille.
        self._rtp_send_lock = threading.Lock()

        # TCP-Socket für SIP-Signalisierung
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.settimeout(1.0)

        # UDP-Socket für RTP-Audio
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind((self.my_ip, 0))
        self.my_rtp_port = self.udp_sock.getsockname()[1]

        # SIP-Zustand
        self.call_id            = uuid.uuid4().hex
        self.from_tag           = uuid.uuid4().hex
        self.to_tag             = ""
        self.cseq               = 1
        self.is_incoming        = False   # True bei eingehendem Anruf
        self.remote_from_hdr    = ""      # From-Header des eingehenden INVITE (mit Tag)
        self.reg_cseq           = 1
        self.is_registered      = False
        self.is_audio_running   = False
        self.dest_rtp_port      = 0
        self.dest_rtp_ip        = SIP_SERVER   # FIX: separate RTP-Ziel-IP
        self.active_num         = ""
        self.last_invite_branch = ""
        self.last_invite_cseq   = 0
        self.keep_alive         = True
        self.mic_boost          = 1.0
        self.ki_modus           = False
        self.ki_kernel          = None
        self.ki_begruessung     = ""

        # Logik für striktes Abwechseln (Turn-Taking)
        self._cancel_tts        = False
        self._is_ki_busy        = False
        self._is_thinking       = False

        # FIX: Merkt sich ob ein eingehender Anruf wartet (für ACK-Handler)
        self._incoming_call_pending = False

        # DTMF-Tracking (Deduplizierung mehrerer RTP-Events pro Tastendruck)
        self._last_dtmf_ts    = 0.0
        self._last_dtmf_digit = ""
        # DTMF-Queue (nur noch für Legacy — DTMF ist im Sprach-Modus deaktiviert)
        self._dtmf_queue: list = []

        # Callbacks
        self._status_log: list = []
        self._end_callback = None

    @property
    def status(self) -> str:
        if not self.is_registered:
            return "nicht_registriert"
        if self.is_audio_running:
            return "gespräch_aktiv"
        return "registriert (wartet auf Anrufe)"

    def _log(self, msg: str):
        logger.info(f"[Fritzbox] {msg}")
        self._status_log.append(msg)

    def _fire_end_callback(self, reason: str = ""):
        cb = self._end_callback
        if cb:
            try:
                threading.Thread(target=cb, args=(reason,), daemon=True).start()
            except Exception as e:
                logger.warning(f"[Fritzbox] End-Callback Fehler: {e}")
        # Push ausstehende Buchung an externen Kalender (nach Gesprächsende)
        threading.Thread(target=_flush_pending_push, daemon=True).start()

    def _create_msg(self, method: str, uri: str, auth: str = "",
                    body: str = "", custom_cseq=None, custom_branch=None) -> str:
        branch   = custom_branch or f"z9hG4bK{uuid.uuid4().hex}"
        cseq_num = custom_cseq   or self.cseq
        ct = "Content-Type: application/sdp\r\n" if body else ""

        to_hdr = f"<{uri}>"
        if method == "BYE" and self.to_tag:
            to_hdr += f";tag={self.to_tag}"

        return (
            f"{method} {uri} SIP/2.0\r\n"
            f"Via: SIP/2.0/TCP {self.my_ip}:{self.my_sip_port};branch={branch}\r\n"
            f"From: <sip:{SIP_USER}@{SIP_SERVER}>;tag={self.from_tag}\r\n"
            f"To: {to_hdr}\r\n"
            f"Call-ID: {self.call_id}\r\n"
            f"CSeq: {cseq_num} {method}\r\n"
            f"Contact: <sip:{SIP_USER}@{self.my_ip}:{self.my_sip_port};transport=tcp>\r\n"
            f"Expires: 120\r\n"
            f"{auth}{ct}Content-Length: {len(body)}\r\n"
            f"Max-Forwards: 70\r\n"
            f"User-Agent: IlijaPhone/1.0\r\n\r\n{body}"
        )

    def _get_sdp(self) -> str:
        # FIX: telephone-event (RFC 4733) als zweiten Codec anbieten,
        # damit DTMF-Tasten (1=Ja, 2=Nein) als RTP-Events ankommen.
        return (
            f"v=0\r\no={SIP_USER} 1 1 IN IP4 {self.my_ip}\r\ns=Ilija\r\n"
            f"c=IN IP4 {self.my_ip}\r\nt=0 0\r\n"
            f"m=audio {self.my_rtp_port} RTP/AVP 8 101\r\n"
            f"a=rtpmap:8 PCMA/8000\r\n"
            f"a=rtpmap:101 telephone-event/8000\r\n"
            f"a=fmtp:101 0-15\r\n"
        )

    def _calc_auth(self, method: str, uri: str, nonce: str, realm: str) -> str:
        ha1  = hashlib.md5(f"{SIP_USER}:{realm}:{SIP_PASSWORD}".encode()).hexdigest()
        ha2  = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        resp = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        return (
            f'Authorization: Digest username="{SIP_USER}", '
            f'realm="{realm}", nonce="{nonce}", uri="{uri}", '
            f'response="{resp}"\r\n'
        )

    def _background_listener(self):
        buf = ""
        while self.keep_alive:
            try:
                chunk = self.tcp_sock.recv(8192).decode(errors="ignore")
                if not chunk:
                    continue
                buf += chunk

                while "\r\n\r\n" in buf:
                    header_part, rest = buf.split("\r\n\r\n", 1)

                    # FIX: Content-Length auslesen und Body korrekt einschließen.
                    # Früher wurde am ersten \r\n\r\n gesplittet und der SDP-Body
                    # (mit m=audio PORT) landete im Puffer statt in `data`.
                    # Dadurch blieb dest_rtp_port=0 und _start_audio() wurde
                    # im ACK-Handler nie aufgerufen → Anrufer hörte Stille.
                    cl_match = re.search(r"Content-Length:\s*(\d+)", header_part,
                                         re.IGNORECASE)
                    content_length = int(cl_match.group(1)) if cl_match else 0

                    if len(rest) < content_length:
                        break  # Body noch nicht vollständig empfangen

                    body = rest[:content_length]
                    buf  = rest[content_length:]
                    data = header_part + "\r\n\r\n" + body

                    first_line = data.splitlines()[0]
                    if "INVITE" in first_line or "OPTIONS" in first_line:
                        self._log(f"← {first_line}")
                    self._handle_sip(data)

            except socket.timeout:
                continue
            except Exception as e:
                if self.keep_alive:
                    self._log(f"Listener-Fehler: {e}")

    def _handle_sip(self, data: str):
        """Verarbeitet ein vollständiges SIP-Paket."""

        def get_routing_headers(sip_data: str) -> str:
            headers = ""
            for line in sip_data.splitlines():
                lower_line = line.lower()
                if lower_line.startswith("via:") or lower_line.startswith("record-route:"):
                    headers += line + "\r\n"
            return headers

        routing_hdrs = get_routing_headers(data)
        from_hdr     = _get_full_header(data, "From")
        to_hdr       = _get_full_header(data, "To")
        call_id      = _get_full_header(data, "Call-ID")
        cseq         = _get_full_header(data, "CSeq")

        # 1. OPTIONS-Ping / NOTIFY der Fritzbox beantworten
        if data.startswith("OPTIONS ") or data.startswith("NOTIFY "):
            ok = (
                f"SIP/2.0 200 OK\r\n"
                f"{routing_hdrs}"
                f"From: {from_hdr}\r\n"
                f"To: {to_hdr}\r\n"
                f"Call-ID: {call_id}\r\n"
                f"CSeq: {cseq}\r\n"
                f"Content-Length: 0\r\n\r\n"
            )
            self.tcp_sock.sendall(ok.encode())
            return

        # 2. EINGEHENDER ANRUF (INVITE)
        if data.startswith("INVITE "):
            if self.is_audio_running:
                self._log("🔔 Eingehender Anruf abgelehnt (Besetzt)")
                resp = (
                    f"SIP/2.0 486 Busy Here\r\n"
                    f"{routing_hdrs}"
                    f"From: {from_hdr}\r\n"
                    f"To: {to_hdr};tag={uuid.uuid4().hex}\r\n"
                    f"Call-ID: {call_id}\r\n"
                    f"CSeq: {cseq}\r\n"
                    f"Content-Length: 0\r\n\r\n"
                )
                self.tcp_sock.sendall(resp.encode())
                return

            self.call_id         = call_id
            self.to_tag          = uuid.uuid4().hex
            self.is_incoming     = True
            self.remote_from_hdr = from_hdr

            caller_match = re.search(r"sip:([^@>]+)", from_hdr)
            self.active_num = caller_match.group(1) if caller_match else "Unbekannt"
            self._log(f"🔔 EINGEHENDER ANRUF VON: {self.active_num} - Nehme ab!")

            # FIX: RTP-Port UND RTP-IP aus dem SDP des eingehenden INVITE lesen.
            # Bei internen Fritzbox-Anrufen kann die RTP-Gegenstelle eine andere
            # IP als die Fritzbox selbst haben (direktes RTP zwischen Endgeräten).
            port = re.search(r"m=audio ([0-9]+)", data)
            if port:
                self.dest_rtp_port = int(port.group(1))
            ip_match = re.search(r"c=IN IP4 ([0-9.]+)", data)
            if ip_match:
                self.dest_rtp_ip = ip_match.group(1)
                self._log(f"[SDP] RTP-Ziel: {self.dest_rtp_ip}:{self.dest_rtp_port}")
            else:
                self.dest_rtp_ip = SIP_SERVER

            sdp = self._get_sdp()

            # FIX: Merken dass wir auf ACK warten (eingehender Anruf)
            self._incoming_call_pending = True

            # FIX: ki_modus sicherstellen — falls listen() vorher gesetzt hat,
            # NICHT überschreiben. Nur Default-Begrüßung setzen wenn leer.
            if not self.ki_begruessung:
                self.ki_begruessung = "Hallo, hier ist Ilija. Wie kann ich dir helfen?"

            # 180 Ringing
            ringing = (
                f"SIP/2.0 180 Ringing\r\n"
                f"{routing_hdrs}"
                f"From: {from_hdr}\r\n"
                f"To: {to_hdr};tag={self.to_tag}\r\n"
                f"Call-ID: {self.call_id}\r\n"
                f"CSeq: {cseq}\r\n"
                f"Contact: <sip:{SIP_USER}@{self.my_ip}:{self.my_sip_port};transport=tcp>\r\n"
                f"Content-Length: 0\r\n\r\n"
            )
            self.tcp_sock.sendall(ringing.encode())

            import time as _t
            # FIX: Längere Klingelzeit (war 0.2s — zu kurz, Anrufer hörte kaum Klingeln)
            _t.sleep(1.5)

            # 200 OK (Abheben)
            ok_resp = (
                f"SIP/2.0 200 OK\r\n"
                f"{routing_hdrs}"
                f"From: {from_hdr}\r\n"
                f"To: {to_hdr};tag={self.to_tag}\r\n"
                f"Call-ID: {self.call_id}\r\n"
                f"CSeq: {cseq}\r\n"
                f"Contact: <sip:{SIP_USER}@{self.my_ip}:{self.my_sip_port};transport=tcp>\r\n"
                f"Content-Type: application/sdp\r\n"
                f"Content-Length: {len(sdp)}\r\n\r\n"
                f"{sdp}"
            )
            self.tcp_sock.sendall(ok_resp.encode())

            self._cancel_tts = False
            self._is_ki_busy = False
            self._is_thinking = False
            return

        # 3. ACK (Fritzbox bestätigt unser Abheben → Audio starten)
        if data.startswith("ACK "):
            # FIX: Nur starten wenn wirklich ein eingehender Anruf vorlag
            # UND dest_rtp_port bekannt ist UND Audio noch nicht läuft
            if (self._incoming_call_pending
                    and not self.is_audio_running
                    and self.dest_rtp_port > 0):
                self._incoming_call_pending = False
                self._log("📞 Leitung steht (eingehend). Starte Audio-Modus.")
                # ki_modus wurde bereits von skill_ausfuehren("listen") auf True
                # gesetzt und darf hier NICHT überschrieben werden.
                # Früher wurde ki_modus=False erzwungen wenn ki_kernel=None —
                # das führte zum Mic-Loop statt KI-Loop (PC-Durchleitung).
                if self.ki_modus and self.ki_kernel is None:
                    self._log("⚠️  KI-Modus aktiv, aber kein Kernel übergeben — "
                              "nutze Echo-Modus als Fallback")
                self._log(f"   → Modus: {'KI-Loop' if self.ki_modus else 'Mic-Loop'}")
                threading.Thread(target=self._start_audio, daemon=True).start()
            return

        # 4. CANCEL (Anrufer legt auf, bevor wir abheben konnten)
        if data.startswith("CANCEL "):
            # SIP-Standard: 200 OK für CANCEL immer senden
            ok = (
                f"SIP/2.0 200 OK\r\n"
                f"{routing_hdrs}"
                f"From: {from_hdr}\r\n"
                f"To: {to_hdr}\r\n"
                f"Call-ID: {call_id}\r\n"
                f"CSeq: {cseq}\r\n"
                f"Content-Length: 0\r\n\r\n"
            )
            self.tcp_sock.sendall(ok.encode())

            if self.is_audio_running:
                # FritzBox schickt manchmal ein verspätetes CANCEL nach dem ACK.
                # Wenn Audio bereits läuft, ist das Gespräch schon verbunden —
                # CANCEL ignorieren und Gespräch weiterlaufen lassen.
                self._log("⚠️  Verspätetes CANCEL nach Gesprächsstart — wird ignoriert "
                          "(Gespräch läuft weiter)")
                return

            # CANCEL vor ACK: Anrufer hat wirklich aufgelegt
            self.is_audio_running = False
            self._incoming_call_pending = False
            self._log("📵 Anrufer hat vor dem Abheben aufgelegt.")
            self._fire_end_callback("aufgelegt (verpasst)")
            return

        # 5. BYE (Gegenseite legt auf)
        if "BYE " in data:
            self.is_audio_running = False
            self._incoming_call_pending = False
            self._log("📵 Gegenseite hat aufgelegt")

            ok = (
                f"SIP/2.0 200 OK\r\n"
                f"{routing_hdrs}"
                f"From: {from_hdr}\r\n"
                f"To: {to_hdr}\r\n"
                f"Call-ID: {call_id}\r\n"
                f"CSeq: {cseq}\r\n"
                f"Content-Length: 0\r\n\r\n"
            )
            self.tcp_sock.sendall(ok.encode())
            # FIX: _fire_end_callback war hier vergessen worden
            self._fire_end_callback("aufgelegt")
            return

        # 6. 486 Besetzt
        if "486 Busy" in data:
            self.is_audio_running = False
            self._incoming_call_pending = False
            self._log("📵 Besetzt")
            # FIX: _fire_end_callback war hier vergessen worden
            self._fire_end_callback("besetzt")
            return

        # 7. 603 / 480 / 487 Abgelehnt / Abgebrochen
        if re.search(r"SIP/2\.0 (603|480|487)", data):
            self.is_audio_running = False
            self._incoming_call_pending = False
            self._log("📵 Anruf abgelehnt/abgebrochen")
            # FIX: _fire_end_callback war hier vergessen worden
            self._fire_end_callback("abgelehnt")
            return

        # 8. 180 Ringing
        if "180 Ringing" in data:
            self._log("📞 Es klingelt beim Ziel...")
            return

        # 9. 401 Unauthorized → Auth-Challenge für ausgehende INVITEs oder REGISTER
        if "401 Unauthorized" in data:
            nonce = _get_header_val(data, "nonce")
            realm = _get_header_val(data, "realm")
            cseq_match = re.search(r"CSeq:\s*([0-9]+)\s+([A-Z]+)", data)
            if cseq_match and nonce and realm:
                method = cseq_match.group(2)
                uri    = (f"sip:{SIP_USER}@{SIP_SERVER}" if method == "REGISTER"
                          else f"sip:{self.active_num}@{SIP_SERVER}")
                auth   = self._calc_auth(method, uri, nonce, realm)

                if method == "REGISTER":
                    self.reg_cseq += 1
                    msg = self._create_msg("REGISTER", f"sip:{SIP_USER}@{SIP_SERVER}",
                                           auth=auth, custom_cseq=self.reg_cseq)
                else:
                    self.cseq += 1
                    self.last_invite_cseq   = self.cseq
                    self.last_invite_branch = f"z9hG4bK{uuid.uuid4().hex}"
                    msg = self._create_msg("INVITE",
                                           f"sip:{self.active_num}@{SIP_SERVER}",
                                           auth=auth, body=self._get_sdp(),
                                           custom_cseq=self.last_invite_cseq,
                                           custom_branch=self.last_invite_branch)
                self.tcp_sock.sendall(msg.encode())
            return

        # 10. 183 Session Progress / 200 OK auf eigenes INVITE → Gespräch aktiv
        if "183 Session Progress" in data or ("200 OK" in data and re.search(r"CSeq:\s*\d+\s+INVITE", data)):
            self._log("🎤 Ausgehendes Gespräch aktiv")
            if "200 OK" in data:
                tag_match = re.search(r"tag=([^;\r\n]+)", to_hdr)
                if tag_match:
                    self.to_tag = tag_match.group(1)

                ack = self._create_msg("ACK",
                                       f"sip:{self.active_num}@{SIP_SERVER}",
                                       custom_cseq=self.last_invite_cseq,
                                       custom_branch=self.last_invite_branch)
                self.tcp_sock.sendall(ack.encode())

            port = re.search(r"m=audio ([0-9]+)", data)
            if port and not self.is_audio_running:
                rtp_port = int(port.group(1))
                if rtp_port > 0:
                    self.dest_rtp_port = rtp_port
                    ip_match = re.search(r"c=IN IP4 ([0-9.]+)", data)
                    self.dest_rtp_ip = ip_match.group(1) if ip_match else SIP_SERVER
                    threading.Thread(target=self._start_audio, daemon=True).start()
            return

        # 11. 200 OK auf REGISTER → erfolgreich registriert
        if "200 OK" in data and re.search(r"CSeq:\s*\d+\s+REGISTER", data):
            self.is_registered = True
            self._log("✅ Bei Fritzbox registriert")
            return

    # ── Registrierung ──────────────────────────────────────────
    def registrieren(self) -> bool:
        if not SIP_USER or not SIP_PASSWORD:
            self._log("SIP_USER oder SIP_PASSWORD fehlt in .env!")
            return False
        try:
            self._log(f"Verbinde zu {SIP_SERVER}:{SIP_PORT}...")
            self.tcp_sock.connect((SIP_SERVER, SIP_PORT))

            # WICHTIG: Den echten lokalen TCP-Port auslesen für die Contact-Header!
            self.my_sip_port = self.tcp_sock.getsockname()[1]

            threading.Thread(target=self._background_listener,
                             daemon=True, name="SIP-Listener").start()

            self.reg_cseq = 1
            msg = self._create_msg("REGISTER", f"sip:{SIP_USER}@{SIP_SERVER}",
                                   custom_cseq=self.reg_cseq)
            self.tcp_sock.sendall(msg.encode())

            def _refresh():
                while self.keep_alive:
                    time.sleep(60)
                    if not self.is_registered:
                        continue
                    try:
                        self.reg_cseq += 1
                        self.tcp_sock.sendall(
                            self._create_msg("REGISTER", f"sip:{SIP_USER}@{SIP_SERVER}",
                                             custom_cseq=self.reg_cseq).encode()
                        )
                    except (OSError, ConnectionAbortedError, BrokenPipeError) as e:
                        logger.warning(f"[SIP-Refresh] Verbindung unterbrochen: {e} — "
                                       "versuche Reconnect in 5s")
                        self.is_registered = False
                        # Reconnect-Schleife: versucht es unbegrenzt alle 30s
                        while self.keep_alive and not self.is_registered:
                            time.sleep(5)
                            try:
                                self.tcp_sock.close()
                            except Exception:
                                pass
                            try:
                                import socket as _sock
                                new_sock = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                                new_sock.settimeout(10)
                                new_sock.connect((SIP_SERVER, SIP_PORT))
                                self.tcp_sock = new_sock
                                self.tcp_sock.settimeout(1.0)
                                # Lokalen Port aktualisieren (neuer Socket = neuer Port)
                                self.my_sip_port = self.tcp_sock.getsockname()[1]
                                # Neuen Listener-Thread starten (alter ist auf altem Socket gestorben)
                                threading.Thread(target=self._background_listener,
                                                 daemon=True, name="SIP-Listener").start()
                                self.reg_cseq += 1
                                self.tcp_sock.sendall(
                                    self._create_msg("REGISTER", f"sip:{SIP_USER}@{SIP_SERVER}",
                                                     custom_cseq=self.reg_cseq).encode()
                                )
                                logger.info("[SIP-Refresh] Reconnect gesendet — warte auf 200 OK...")
                                # Warte bis Registrierung bestätigt (max 15s)
                                for _ in range(30):
                                    if self.is_registered or not self.keep_alive:
                                        break
                                    time.sleep(0.5)
                                if self.is_registered:
                                    logger.info("[SIP-Refresh] ✅ Wieder registriert")
                                else:
                                    logger.warning("[SIP-Refresh] Keine Bestätigung — erneuter Versuch in 30s")
                                    time.sleep(25)  # + die 5s am Anfang = 30s
                            except Exception as err:
                                logger.error(f"[SIP-Refresh] Reconnect fehlgeschlagen: {err} — "
                                             "nächster Versuch in 30s")
                                time.sleep(25)
            threading.Thread(target=_refresh, daemon=True,
                             name="SIP-Refresh").start()
            return True

        except Exception as e:
            self._log(f"Verbindungsfehler: {e}")
            return False

    # ── Anruf tätigen ──────────────────────────────────────────
    def anrufen(self, nummer: str, ki_modus: bool = False,
               ki_kernel=None, ki_begruessung: str = "") -> str:
        self.ki_modus       = ki_modus
        self.ki_kernel      = ki_kernel
        self.ki_begruessung = ki_begruessung
        self._cancel_tts    = False
        self._is_ki_busy    = False
        self._is_thinking   = False
        self._incoming_call_pending = False  # FIX: kein eingehender Anruf

        if not self.is_registered:
            return "❌ Nicht registriert. Zuerst telefon_starten() aufrufen."
        if not nummer.strip():
            return "❌ Keine Nummer angegeben."

        self.active_num         = nummer.strip()
        self.call_id            = uuid.uuid4().hex
        self.to_tag             = ""
        self.cseq              += 1
        self.last_invite_cseq   = self.cseq
        self.last_invite_branch = f"z9hG4bK{uuid.uuid4().hex}"

        msg = self._create_msg(
            "INVITE", f"sip:{self.active_num}@{SIP_SERVER}",
            body=self._get_sdp(),
            custom_cseq=self.last_invite_cseq,
            custom_branch=self.last_invite_branch,
        )
        self.tcp_sock.sendall(msg.encode())
        self._log(f"📞 Rufe {self.active_num} an...")
        return f"📞 Wähle {self.active_num}..."

    # ── Auflegen ───────────────────────────────────────────────
    def auflegen(self) -> str:
        self.is_audio_running = False
        self._incoming_call_pending = False
        self._cancel_tts = True
        self._is_thinking = False
        target = f"sip:{self.active_num}@{SIP_SERVER}" if self.active_num else f"sip:{SIP_USER}@{SIP_SERVER}"

        try:
            self.tcp_sock.sendall(
                self._create_msg("CANCEL", target,
                                 custom_cseq=self.last_invite_cseq,
                                 custom_branch=self.last_invite_branch).encode()
            )
        except Exception:
            pass

        self.cseq += 1
        try:
            if self.is_incoming and self.remote_from_hdr:
                # Eingehender Anruf: From/To müssen gespiegelt werden.
                # From = Ilija mit dem To-Tag aus dem 200 OK
                # To   = Caller mit dem Tag aus dem ursprünglichen INVITE
                branch = f"z9hG4bK{uuid.uuid4().hex}"
                bye = (
                    f"BYE {target} SIP/2.0\r\n"
                    f"Via: SIP/2.0/TCP {self.my_ip}:{self.my_sip_port};branch={branch}\r\n"
                    f"From: <sip:{SIP_USER}@{SIP_SERVER}>;tag={self.to_tag}\r\n"
                    f"To: {self.remote_from_hdr}\r\n"
                    f"Call-ID: {self.call_id}\r\n"
                    f"CSeq: {self.cseq} BYE\r\n"
                    f"Contact: <sip:{SIP_USER}@{self.my_ip}:{self.my_sip_port};transport=tcp>\r\n"
                    f"Max-Forwards: 70\r\n"
                    f"User-Agent: IlijaPhone/1.0\r\n"
                    f"Content-Length: 0\r\n\r\n"
                )
                self.tcp_sock.sendall(bye.encode())
            else:
                self.tcp_sock.sendall(
                    self._create_msg("BYE", target).encode()
                )
        except Exception:
            pass
        self.is_incoming = False
        self._log("📵 Aufgelegt")
        return "📵 Aufgelegt."

    # ── Beenden ────────────────────────────────────────────────
    def beenden(self):
        self.keep_alive       = False
        self.is_audio_running = False
        self._cancel_tts      = True
        self._is_thinking     = False
        self._incoming_call_pending = False
        try:
            self.tcp_sock.close()
        except Exception:
            pass
        try:
            self.udp_sock.close()
        except Exception:
            pass
        self._log("Telefon beendet.")

    # ── Audio (RTP über UDP) ───────────────────────────────────

    def _rtp_send_pcm(self, pcm_bytes: bytes):
        """Sendet PCM-Audio als RTP-Pakete (PCMA/G.711a, 8kHz, Mono).
        Thread-sicher: _rtp_send_lock verhindert gleichzeitige Sends."""
        import time as _t
        lock = getattr(self, "_rtp_send_lock", None)
        with (lock if lock else threading.Lock()):
            chunk_bytes = 320
            samples_per_chunk = 160
            seq = getattr(self, "_tts_seq", 0)
            ts  = getattr(self, "_tts_ts",  0)
            next_send = _t.monotonic()

            for i in range(0, len(pcm_bytes), chunk_bytes):
                if self._cancel_tts or not self.is_audio_running:
                    break

                frame = pcm_bytes[i:i+chunk_bytes]
                if len(frame) < chunk_bytes:
                    frame = frame + b'\x00' * (chunk_bytes - len(frame))

                pkt = (bytearray([0x80, 0x08])
                       + seq.to_bytes(2, "big")
                       + ts.to_bytes(4, "big")
                       + b'\x00\x00\x00\x00'
                       + audioop.lin2alaw(frame, 2))

                try:
                    self.udp_sock.sendto(bytes(pkt), (self.dest_rtp_ip, self.dest_rtp_port))
                except Exception:
                    pass

                seq = (seq + 1) % 65536
                ts  = (ts  + samples_per_chunk) % 4294967296

                next_send += 0.020
                wait = next_send - _t.monotonic()

                if wait > 0:
                    if wait > 0.002:
                        _t.sleep(wait - 0.002)
                    while _t.monotonic() < next_send:
                        pass

            self._tts_seq = seq
            self._tts_ts  = ts

    def _play_waiting_tone(self):
        # Im Buchstabier-Modus Warteton komplett unterdrücken!
        is_spelling = getattr(self.ki_kernel, "is_spelling_active", False)
        if is_spelling:
            return

        # Erst 1.5 Sekunden warten — wenn die KI-Antwort schnell kommt,
        # wird "Einen Augenblick" gar nicht erst gespielt.
        import time as _t
        for _ in range(15):  # 15 × 0.1s = 1.5s
            if not self._is_thinking or not self.is_audio_running:
                return
            _t.sleep(0.1)

        if self._is_thinking and self.is_audio_running:
            self._tts_speak("Einen Augenblick bitte.")

        import math, struct
        sr = 8000

        def make_tone(duration_ms, freq, volume=0.04):
            samples = int(sr * duration_ms / 1000)
            return struct.pack(f"<{samples}h", *[int(32767 * volume * math.sin(2 * math.pi * freq * t / sr)) for t in range(samples)])

        def make_silence(duration_ms):
            samples = int(sr * duration_ms / 1000)
            return struct.pack(f"<{samples}h", *[0]*samples)

        beep1 = make_tone(70, 500)
        silence_short = make_silence(50)
        beep2 = make_tone(70, 650)
        chunk_silence = make_silence(200)

        for _ in range(3):
            if not self._is_thinking: break
            self._rtp_send_pcm(chunk_silence)

        while self._is_thinking and self.is_audio_running:
            if not self._is_thinking: break
            self._rtp_send_pcm(beep1 + silence_short + beep2)

            for _ in range(7):
                if not self._is_thinking: break
                self._rtp_send_pcm(chunk_silence)

    def _tts_speak(self, text: str):
        import tempfile, os, wave, subprocess, shutil, asyncio, re

        if self._cancel_tts or not self.is_audio_running:
            return

        # FIX: Leere oder Whitespace-only Antworten nicht sprechen
        # (z.B. wenn der Kernel im Spelling-Mode "" zurückgibt)
        if not text or not text.strip():
            return

        text = re.sub(r'[*_#~`]', '', text)
        self._log(f"[TTS] '{text[:60]}'")

        saetze = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if not saetze:
            saetze = [text]

        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

        def _speak_satz(satz: str) -> bool:
            if self._cancel_tts:
                return False

            try:
                import edge_tts
                mp3 = tempfile.mktemp(suffix=".mp3")
                wav = tempfile.mktemp(suffix=".wav")

                async def _synthesize():
                    communicate = edge_tts.Communicate(satz, voice="de-DE-ConradNeural")
                    await communicate.save(mp3)

                asyncio.run(_synthesize())

                if self._cancel_tts:
                    try: os.unlink(mp3)
                    except: pass
                    return False

                subprocess.run([ffmpeg, "-y", "-i", mp3,
                                "-ar", "8000", "-ac", "1", "-f", "wav", wav],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                with wave.open(wav, "rb") as wf:
                    pcm = wf.readframes(wf.getnframes())
                for p in [mp3, wav]:
                    try: os.unlink(p)
                    except: pass

                # Warteton stoppen, sobald das Audio bereit ist (verhindert Stille-Lücke)
                self._is_thinking = False
                self._rtp_send_pcm(pcm)
                return True
            except Exception as e:
                self._log(f"[TTS] edge-tts Satz-Fehler: {e}")
                return False

        edge_ok = False
        for satz in saetze:
            if self._cancel_tts or not self.is_audio_running:
                break
            if _speak_satz(satz):
                edge_ok = True

        if not edge_ok and not self._cancel_tts:
            self._log("[TTS] Fallback auf pyttsx3")
            try:
                import pyttsx3
                wav = tempfile.mktemp(suffix=".wav")
                eng = pyttsx3.init()
                eng.setProperty("rate", 160)
                for v in eng.getProperty("voices"):
                    if "german" in v.name.lower() or "de_" in v.id.lower():
                        eng.setProperty("voice", v.id)
                        break
                eng.save_to_file(text, wav)
                eng.runAndWait()
                wav8 = wav + "_8k.wav"
                subprocess.run([ffmpeg, "-y", "-i", wav, "-ar", "8000", "-ac", "1", wav8],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                src = wav8 if os.path.exists(wav8) else wav
                with wave.open(src, "rb") as wf:
                    pcm = wf.readframes(wf.getnframes())
                for p in [wav, wav8]:
                    try: os.unlink(p)
                    except: pass
                self._rtp_send_pcm(pcm)
                self._log("[TTS] pyttsx3 OK")
            except Exception as e:
                self._log(f"[TTS] pyttsx3: {e} – kein TTS-Backend verfügbar!")

    # ── DTMF (RFC 4733) ────────────────────────────────────────────────

    def _play_quick_confirm(self):
        """Sofortiges akustisches Feedback nach '#' — 2 kurze aufsteigende Töne.
        Signalisiert dem Anrufer: Eingabe empfangen, System arbeitet.
        Kein TTS nötig — Rohdaten direkt über RTP (~200ms, blockiert nicht spürbar)."""
        import math, struct
        sr = 8000
        def _tone(ms, freq, vol=0.07):
            n = int(sr * ms / 1000)
            return struct.pack(f"<{n}h",
                *[int(32767 * vol * math.sin(2 * math.pi * freq * t / sr))
                  for t in range(n)])
        def _sil(ms):
            return struct.pack(f"<{int(sr * ms / 1000)}h",
                               *([0] * int(sr * ms / 1000)))
        # tief → hoch (klassisches IVR-Bestätigungs-Signal)
        audio = _tone(80, 800) + _sil(40) + _tone(100, 1200)
        self._rtp_send_pcm(audio)

    @staticmethod
    def _rtp_payload_type(data: bytes) -> int:
        """Liest den Payload-Type aus dem RTP-Header (Bits 1-7 von Byte 1)."""
        if len(data) < 12:
            return -1
        return data[1] & 0x7F

    @staticmethod
    def _parse_dtmf_event(payload: bytes):
        """RFC 4733: liefert (digit_char, end_bit) oder (None, False)."""
        if len(payload) < 4:
            return None, False
        event = payload[0]
        end   = bool(payload[1] & 0x80)
        chars = "0123456789*#ABCD"
        if event < len(chars):
            return chars[event], end
        return None, False

    def _handle_dtmf(self, digit: str):
        """DTMF deaktiviert — alles läuft über Spracheingabe (Whisper STT).
        Tasteneingaben werden still ignoriert, damit sie den Sprach-Loop nicht stören."""
        self._log(f"[DTMF] Taste {digit!r} ignoriert (Sprach-Modus)")
        return

    def _handle_dtmf_legacy(self, digit: str):
        """[LEGACY — nicht mehr aktiv] Ehemaliger DTMF-Handler mit Modus A/B."""
        if not digit:
            return

        # ── Modus B: Normal (Slot-Auswahl, Ja/Nein) — LEGACY ────────────────
        if not digit.isdigit():
            self._log(f"[DTMF] Taste {digit!r} ignoriert (keine Ziffer)")
            return
        if self._is_ki_busy:
            self._dtmf_queue = [digit]   # nur letzte Taste merken
            self._log(f"[DTMF] '{digit}' in Queue gestellt (KI beschaeftigt)")
            return
        self._dtmf_queue = []
        self._log(f"[DTMF] Taste {digit} → an Kernel")
        self._is_ki_busy = True

        def _process():
            try:
                antwort = self.ki_kernel.chat(digit) if self.ki_kernel else ""
                if antwort and antwort.strip():
                    self._tts_speak(antwort)
            except Exception as e:
                self._log(f"[DTMF] Fehler: {e}")
            finally:
                self._is_ki_busy = False
                if self._dtmf_queue:
                    queued = self._dtmf_queue.pop(0)
                    self._log(f"[DTMF] Queue-Taste {queued} nachverarbeiten")
                    import time as _t; _t.sleep(0.15)
                    self._handle_dtmf(queued)

        threading.Thread(target=_process, daemon=True).start()

    def _stt_from_pcm(self, pcm_bytes: bytes) -> str:
        import tempfile, os, wave, subprocess, shutil
        dur = len(pcm_bytes) / 16000
        self._log(f"[STT] {dur:.1f}s Audio transkribieren...")

        wav8 = tempfile.mktemp(suffix="_8k.wav")
        with wave.open(wav8, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm_bytes)

        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        wav16  = wav8 + "_16k.wav"
        subprocess.run([ffmpeg, "-y", "-i", wav8, "-ar", "16000", wav16],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        src = wav16 if os.path.exists(wav16) else wav8
        text = ""

        # 1. OpenAI API zuerst (wenn API-Key vorhanden) — deutlich besser als
        #    lokales Whisper "base" für deutsche Namen und kurze Antworten.
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            try:
                import openai as _openai
                client = _openai.OpenAI(api_key=openai_key)
                stt_model = os.getenv("OPENAI_STT_MODEL", "whisper-1")
                with open(src, "rb") as f:
                    r = client.audio.transcriptions.create(
                        model=stt_model,
                        file=f,
                        language="de",
                        prompt=_STT_PROMPT_DE,    # Domain-Hinweis verbessert Namen-Erkennung deutlich
                        temperature=0.0,           # deterministisch, keine Halluzinationen
                    )
                text = r.text.strip()
                self._log(f"[STT] OpenAI {stt_model}: '{text[:60]}'")
            except Exception as e:
                self._log(f"[STT] OpenAI: {e}")

        # 2. Lokales Whisper als Fallback (mit Modell-Cache + initial_prompt)
        if not text:
            model = _load_whisper_model()
            if model:
                try:
                    result = model.transcribe(
                        src,
                        language="de",
                        initial_prompt=_STT_PROMPT_DE,
                        temperature=0.0,
                        condition_on_previous_text=False,
                    )
                    text = result["text"].strip()
                    self._log(f"[STT] Whisper-{_WHISPER_MODEL_NAME}: '{text[:60]}'")
                except Exception as e:
                    self._log(f"[STT] Whisper: {e}")

        for p in [wav8, wav16]:
            try: os.unlink(p)
            except: pass
        return text

    def _ki_antworten(self, pcm_bytes: bytes):
        self._is_thinking = True
        wait_thread = threading.Thread(target=self._play_waiting_tone, daemon=True)
        wait_thread.start()

        try:
            text = self._stt_from_pcm(pcm_bytes)
            if not text:
                self._log("[KI] STT: kein Text erkannt")
                return

            self._log(f"[KI] Verstanden: '{text}'")
            if self.ki_kernel:
                antwort = self.ki_kernel.chat(text)
            else:
                antwort = f"Du hast gesagt: {text}"

            self._log(f"[KI] Antwort: '{antwort[:80]}'")

            self._is_thinking = False
            wait_thread.join()

            self._tts_speak(antwort)

            # Dialog beendet → Ilija legt selbst auf (kurze Pause damit TTS ausklingt)
            try:
                dialog = getattr(self.ki_kernel, "_dialog", None)
                if dialog and getattr(dialog, "state", None) is not None:
                    if getattr(dialog.state, "value", None) == "end":
                        threading.Timer(1.5, self.auflegen).start()
            except Exception:
                pass

        except Exception as e:
            self._log(f"[KI] Fehler: {e}")
            self._is_thinking = False
        finally:
            self._is_thinking = False
            self._is_ki_busy = False

    def _start_audio(self):
        self.is_audio_running = True
        self._tts_seq = 0
        self._tts_ts  = 0
        self._log(f"[Audio] Start — KI-Modus: {self.ki_modus}")
        if self.ki_modus:
            self._audio_ki_loop()
        else:
            self._audio_mic_loop()

    def _audio_mic_loop(self):
        try:
            p     = pyaudio.PyAudio()
            in_s  = p.open(format=pyaudio.paInt16, channels=1, rate=8000,
                           input=True, frames_per_buffer=160,
                           input_device_index=MIC_ID)
            out_s = p.open(format=pyaudio.paInt16, channels=1, rate=8000, output=True)
            ts, seq = 0, 0
            while self.is_audio_running:
                try:
                    raw = in_s.read(160, exception_on_overflow=False)
                    if self.mic_boost != 1.0:
                        raw = audioop.mul(raw, 2, self.mic_boost)
                    self.udp_sock.sendto(
                        bytearray([0x80, 0x08])
                        + seq.to_bytes(2, "big")
                        + ts.to_bytes(4, "big")
                        + b'\x00\x00\x00\x00'
                        + audioop.lin2alaw(raw, 2),
                        (self.dest_rtp_ip, self.dest_rtp_port))
                    seq = (seq + 1) % 65536
                    ts  = (ts  + 160) % 4294967296
                    self.udp_sock.setblocking(False)
                    try:
                        d, _ = self.udp_sock.recvfrom(2048)
                        if len(d) > 12:
                            out_s.write(audioop.alaw2lin(d[12:], 2))
                    except Exception:
                        pass
                    finally:
                        self.udp_sock.setblocking(True)
                except Exception:
                    pass
            in_s.close()
            out_s.close()
            p.terminate()
        except Exception as e:
            self._log(f"[Audio] Mic-Fehler: {e}")

    def _audio_ki_loop(self):
        import time as _t

        # ── Neuen Anruf sauber initialisieren ────────────────────────────────
        # Gesprächsverlauf des vorherigen Anrufs löschen — sonst "erinnert"
        # sich Ilija an fremde Termine aus dem vorherigen Gespräch.
        if self.ki_kernel and hasattr(self.ki_kernel, "reset_history"):
            self.ki_kernel.reset_history()
            self._log("[KI] Gesprächsverlauf zurückgesetzt (neuer Anruf)")

        # Anrufer-Nummer an den KI-Kernel weitergeben (für Datenisolation).
        if (self.ki_kernel and self.active_num
                and self.active_num not in ("", "Unbekannt")
                and hasattr(self.ki_kernel, "set_caller_id")):
            self.ki_kernel.set_caller_id(self.active_num)
            self._log(f"[KI] caller_id gesetzt: {self.active_num}")
        elif self.ki_kernel and hasattr(self.ki_kernel, "set_caller_id"):
            # Unterdrückte Nummer → caller_id explizit leeren
            self.ki_kernel.set_caller_id("")
            self._log("[KI] Unterdrückte Nummer — caller_id geleert")

        # FIX: Konstanten für Voice-Activity-Detection (VAD)
        # Vorher waren MIN_SPEECH_SEC = 0.4 zu hoch — kurze "Ja"/"Nein"-Antworten
        # (typisch 200-350ms) wurden komplett verworfen. Anrufer mussten 3-4x
        # wiederholen, bis die Summe das Minimum überschritt.
        SILENCE_RMS    = 250    # war 300 — etwas sensibler für leise Stimmen
        SILENCE_SEC    = 0.8    # war 1.2 — schnellere Reaktion auf kurze Antworten
        MIN_SPEECH_SEC = 0.2    # war 0.4 — akzeptiert auch kurze "Ja"/"Nein"
        SAMPLE_RATE    = 8000

        buf           = b""
        silence_start = None
        speaking      = False
        last_pkt      = _t.time()

        self._log("[KI] Hoere zu...")

        if self.ki_begruessung:
            # FIX: Warte länger damit die RTP-Verbindung stabil ist (war 1.0s — zu kurz)
            # Besonders bei eingehenden Anrufen braucht die Fritzbox etwas mehr Zeit
            # um den RTP-Stream anzunehmen nach dem ACK.
            _t.sleep(2.0)

            def _greet():
                self._is_ki_busy = True
                try:
                    self._tts_speak(self.ki_begruessung)
                finally:
                    self._is_ki_busy = False

            if self.is_audio_running:
                threading.Thread(target=_greet, daemon=True).start()
                _t.sleep(0.5)

        while self.is_audio_running:
            self.udp_sock.settimeout(0.05)
            try:
                data, _ = self.udp_sock.recvfrom(2048)
                last_pkt = _t.time()

                # ── DTMF-Events (PT 101) — still ignorieren (Sprach-Modus) ──────
                pt = self._rtp_payload_type(data)
                if pt == 101 and len(data) >= 16:
                    digit, end = self._parse_dtmf_event(data[12:])
                    if digit and end:
                        self._handle_dtmf(digit)  # no-op im Sprach-Modus
                    continue

                # Während KI beschäftigt: Buffer verwerfen.
                if self._is_ki_busy:
                    buf           = b""
                    speaking      = False
                    silence_start = None
                    continue

                if len(data) <= 12:
                    continue

                pcm = audioop.alaw2lin(data[12:], 2)
                rms = audioop.rms(pcm, 2)

                if rms > SILENCE_RMS:
                    if not speaking:
                        self._log("[KI] Sprache erkannt")
                        speaking = True
                    buf          += pcm
                    silence_start = None
                else:
                    if speaking:
                        if silence_start is None:
                            silence_start = _t.time()
                        elif _t.time() - silence_start >= SILENCE_SEC:
                            dur = len(buf) / (SAMPLE_RATE * 2)
                            self._log(f"[KI] Pause nach {dur:.1f}s Sprache")
                            if dur >= MIN_SPEECH_SEC:
                                cap           = buf
                                buf           = b""
                                speaking      = False
                                silence_start = None

                                self._is_ki_busy = True
                                threading.Thread(target=self._ki_antworten,
                                                 args=(cap,), daemon=True).start()
                            else:
                                buf           = b""
                                speaking      = False
                                silence_start = None

            except socket.timeout:
                if _t.time() - last_pkt > 10.0:
                    self._log("[KI] Keine RTP-Pakete seit 10s — beende")
                    break
            except Exception as e:
                if self.is_audio_running:
                    self._log(f"[KI] Empfangsfehler: {e}")

        self._log("[KI] Audio-Loop beendet")


# ── Skill-Interface für den Ilija-Kernel ──────────────────────

SKILL_NAME        = "fritzbox_telefonie"
SKILL_DESCRIPTION = """
Telefonie über die Fritzbox. Ilija kann:
- Anrufe tätigen an Rufnummern oder Kontaktnamen (aktion="anrufen")
- Laufende Gespräche beenden (aktion="auflegen")
- Den Telefonstatus abfragen (aktion="status")
- Fritzbox-Kontakte suchen (aktion="kontakte")
- In den 'Zuhören'-Modus gehen, um Anrufe anzunehmen (aktion="listen")

WICHTIG: Wenn der Nutzer möchte, dass du auf Anrufe wartest oder ans Telefon gehst, nutze IMMER die aktion "listen" (nicht "annehmen" oder "warten").
"""

SKILL_TRIGGERS = [
    "ruf", "anruf", "telefonier", "klingel", "wähl", "dial",
    "phone", "nummer", "telefon", "call", "auflegen", "leg auf",
    "verbinden", "kontakt", "fritzbox", "listen", "zuhören", "annehmen", "warten", "empfangen"
]


def telefon_starten() -> bool:
    global _phone
    with _phone_lock:
        if _phone is not None and _phone.is_registered:
            return True
        try:
            _phone = FritzboxPhone()
        except Exception as e:
            logger.error(f"[Fritzbox] Telefon-Init fehlgeschlagen: {e}")
            return False

    ok = _phone.registrieren()
    if ok:
        for _ in range(10):
            time.sleep(0.5)
            if _phone.is_registered:
                return True
    return _phone.is_registered if _phone else False


def telefon_stoppen():
    global _phone
    with _phone_lock:
        if _phone:
            _phone.beenden()
            _phone = None


def telefon_status() -> str:
    if _phone is None:
        return "nicht_gestartet"
    return _phone.status


def skill_ausfuehren(aktion: str, nummer: str = "", name: str = "",
                     suche: str = "", ki_modus: str = "", kernel=None) -> str:
    global _phone

    aktion = aktion.strip().lower()

    if aktion == "anrufen":
        ziel = nummer or name
        nummer = ziel
        if not nummer:
            return "❌ Keine Nummer oder Name angegeben."

        use_ki      = ki_modus.lower() in ("ja", "yes", "true", "1") if ki_modus else False
        begruessung = "Hallo, hier ist Ilija. Wie kann ich dir helfen?" if use_ki else ""

        rufnummer = nummer_aufloesen(nummer)

        if _phone is None or not _phone.is_registered:
            logger.info("[Fritzbox] Starte Telefon für Anruf...")
            if not telefon_starten():
                return "❌ Telefon konnte nicht gestartet werden. SIP_USER/SIP_PASSWORD in .env prüfen."

        if _call_end_callback:
            _phone._end_callback = _call_end_callback

        return _phone.anrufen(rufnummer, ki_modus=use_ki, ki_kernel=kernel, ki_begruessung=begruessung)

    elif aktion == "auflegen":
        if _phone is None:
            return "ℹ️ Kein aktives Gespräch."
        return _phone.auflegen()

    elif aktion == "status":
        status = telefon_status()
        status_texte = {
            "nicht_gestartet":   "📵 Telefon nicht gestartet.",
            "nicht_registriert": "⏳ Verbindet mit Fritzbox...",
            "registriert":       "✅ Telefon registriert und bereit.",
            "gespräch_aktiv":    "🎤 Gespräch ist gerade aktiv.",
        }
        return status_texte.get(status, status)

    elif aktion in ["listen", "zuhören", "annehmen", "warten", "empfangen"]:
        if _phone is None or not _phone.is_registered:
            logger.info("[Fritzbox] Starte Telefon für eingehende Anrufe...")
            if not telefon_starten():
                return "❌ Telefon konnte nicht gestartet werden."

        # FIX: KI-Kernel und Begrüßung JETZT setzen, damit sie beim
        # eingehenden INVITE bereits vorhanden sind und der ACK-Handler
        # sie vorfindet. Früher wurden sie erst beim ACK geprüft —
        # zu spät, weil INVITE die Begrüßung evtl. schon überschrieben hat.
        _phone.ki_kernel      = kernel
        _phone.ki_modus       = True
        # Begrüßung aus phone_config.json laden (Fallback: generische Begrüßung)
        try:
            from phone_kernel import lade_begruessung
            _phone.ki_begruessung = lade_begruessung()
        except Exception:
            _phone.ki_begruessung = "Hallo, hier ist die KI-Assistentin Ilija. Wie kann ich helfen?"

        if _call_end_callback:
            _phone._end_callback = _call_end_callback

        return "✅ Ilija ist jetzt online und nimmt eingehende Anrufe automatisch an!"

    elif aktion == "kontakte":
        kontakte = fritzbox_kontakte()
        if not kontakte:
            return "📒 Keine Kontakte gefunden."
        s = suche.lower()
        if s:
            treffer = {n: nr for n, nr in kontakte.items() if s in n}
        else:
            treffer = dict(list(kontakte.items())[:15])
        if not treffer:
            return f"📒 Kein Kontakt für '{s}' gefunden."
        zeilen = [f"• {n.title()}: {nr}" for n, nr in sorted(treffer.items())]
        return "📒 Kontakte:\n" + "\n".join(zeilen)

    return f"❌ Unbekannte Aktion: '{aktion}'"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")

    print("=" * 50)
    print("Fritzbox Skill – Direkttest")
    print(f"Server: {SIP_SERVER}, User: {SIP_USER}")
    print("=" * 50)

    print("\n[1] Starte Telefon und registriere bei Fritzbox...")
    ok = telefon_starten()
    print(f"    Registriert: {ok}")

    if ok:
        print("\n[2] Testanruf auf **9 (Fritzbox-Ansage)...")
        ergebnis = skill_ausfuehren("anrufen", nummer="**9")
        print(f"    Ergebnis: {ergebnis}")

        print("\n[3] Warte 8 Sekunden...")
        time.sleep(8)

        print("\n[4] Auflegen...")
        print(f"    {skill_ausfuehren('auflegen')}")

        print("\n[5] Status:")
        print(f"    {skill_ausfuehren('status')}")

    print("\n[6] Beende.")
    telefon_stoppen()


AVAILABLE_SKILLS = [
    telefon_starten,
    telefon_stoppen,
    telefon_status,
    skill_ausfuehren,
    fritzbox_kontakte,
    nummer_aufloesen,
    set_call_end_callback,
]