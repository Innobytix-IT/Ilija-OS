import socket, uuid, hashlib, re, pathlib, os
from dotenv import load_dotenv

# .env laden – aber NUR wenn Werte nicht bereits gesetzt sind
env_path = pathlib.Path(__file__).parent / ".env"
load_dotenv(env_path)

FB_IP = os.getenv("SIP_SERVER", "fritz.box")
USER  = os.getenv("SIP_USER",   "")
PASS  = os.getenv("SIP_PASSWORD","")
MY_IP = os.getenv("SIP_MY_IP",  "")

# MY_IP automatisch ermitteln falls leer
if not MY_IP:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((FB_IP, 5060)); MY_IP = s.getsockname()[0]; s.close()

print(f"FB_IP={FB_IP}  USER={USER}  MY_IP={MY_IP}")
print(f"PASS={'*' * len(PASS) if PASS else '❌ LEER!'}")
print()

# ── SIP-Nachrichten ────────────────────────────────────────────
from_tag = uuid.uuid4().hex
call_id  = uuid.uuid4().hex

def create_msg(method, uri, auth="", cseq=1, branch=None):
    br = branch or f"z9hG4bK{uuid.uuid4().hex}"
    return (
        f"{method} {uri} SIP/2.0\r\n"
        f"Via: SIP/2.0/TCP {MY_IP}:5060;branch={br}\r\n"
        f"From: <sip:{USER}@{FB_IP}>;tag={from_tag}\r\n"
        f"To: <{uri}>\r\n"
        f"Call-ID: {call_id}\r\n"
        f"CSeq: {cseq} {method}\r\n"
        f"Contact: <sip:{USER}@{MY_IP}:5060;transport=tcp>\r\n"
        f"{auth}"
        f"Content-Length: 0\r\n"
        f"Max-Forwards: 70\r\n"
        f"User-Agent: PythonSoftphoneV4.3\r\n"
        f"\r\n"
    )

def calc_auth(nonce, realm, method, uri):
    ha1  = hashlib.md5(f"{USER}:{realm}:{PASS}".encode()).hexdigest()
    ha2  = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    resp = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return (
        f'Authorization: Digest username="{USER}", realm="{realm}", '
        f'nonce="{nonce}", uri="{uri}", response="{resp}"\r\n'
    )

def recv_full(sock, timeout=10.0):
    """
    Liest TCP-Pakete bis ein vollständiger SIP-Header angekommen ist.
    Fritzbox schickt manchmal mehrere TCP-Segmente — daher Loop.
    """
    sock.settimeout(timeout)
    buf = ""
    while True:
        try:
            chunk = sock.recv(8192).decode(errors="ignore")
            if chunk:
                buf += chunk
                print(f"   [TCP chunk {len(chunk)} Bytes]")
            if "\r\n\r\n" in buf:
                break
            if not chunk:
                break
        except socket.timeout:
            print("   [recv timeout]")
            break
    return buf

# ── Verbinden & Registrieren ───────────────────────────────────
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10.0)

try:
    print(f"Verbinde zu {FB_IP}:5060 (TCP)...")
    sock.connect((FB_IP, 5060))
    print("Verbunden!\n")

    # REGISTER-URI: sip:USER@FB_IP  (wie in Original-App)
    reg_uri = f"sip:{USER}@{FB_IP}"

    print(f"→ REGISTER senden (uri={reg_uri})...")
    sock.sendall(create_msg("REGISTER", reg_uri, cseq=1).encode())

    resp1 = recv_full(sock)
    first_line = resp1.split("\r\n")[0] if resp1 else "(keine Antwort)"
    print(f"← {first_line}\n")

    if "200 OK" in resp1:
        print("✅ ERFOLG! Sofort registriert.")

    elif "401" in resp1:
        nonce = re.search(r'nonce="([^"]+)"', resp1)
        realm = re.search(r'realm="([^"]+)"', resp1)

        if not nonce or not realm:
            print("❌ 401 ohne nonce/realm — volle Antwort:")
            print(resp1[:600])
        else:
            print(f"   nonce={nonce.group(1)[:20]}...  realm={realm.group(1)}")
            auth = calc_auth(nonce.group(1), realm.group(1), "REGISTER", reg_uri)
            print("→ REGISTER mit Auth senden...")
            sock.sendall(create_msg("REGISTER", reg_uri, auth=auth, cseq=2).encode())

            resp2 = recv_full(sock)
            second_line = resp2.split("\r\n")[0] if resp2 else "(keine Antwort)"
            print(f"← {second_line}\n")

            if "200 OK" in resp2:
                print("✅ ERFOLG! Registrierung erfolgreich.")
            else:
                print("❌ Fehlgeschlagen. Volle Antwort:")
                print(resp2[:600])

    else:
        print(f"⚠️  Unerwartete Antwort (leer = Fritzbox hat nichts geschickt):")
        print(repr(resp1[:300]))

except socket.timeout:
    print("❌ TIMEOUT — keine Antwort von Fritzbox auf TCP:5060")
except Exception as e:
    print(f"❌ {type(e).__name__}: {e}")
finally:
    sock.close()
