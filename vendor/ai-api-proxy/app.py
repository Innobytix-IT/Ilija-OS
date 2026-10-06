"""
Gemini Proxy — Tkinter-Launcher mit Prozessverwaltung, .env-Editor
und automatischer lokaler Netzwerk-IP (LAN-Freigabe).
"""
from __future__ import annotations

import os
import sys
import socket
import secrets
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _read_env() -> dict:
    result: dict[str, str] = {}
    if not os.path.exists(ENV_FILE):
        return result
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            key, _, val = line.strip().partition("=")
            key = key.strip()
            if key and not key.startswith("#") and val is not None:
                result[key] = val.strip()
    return result


def _write_env(data: dict) -> None:
    lines: list[str] = []
    updated: set[str] = set()
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                key = line.partition("=")[0].strip()
                if key in data:
                    lines.append(f"{key}={data[key]}\n")
                    updated.add(key)
                else:
                    lines.append(line)
    for k, v in data.items():
        if k not in updated:
            lines.append(f"{k}={v}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _local_ip() -> str:
    """Ermittelt die tatsächliche LAN-IP-Adresse des Rechners."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


BG, BG2, BG3 = "#1e1e2e", "#313244", "#45475a"
TX1, TX2, TX3 = "#cdd6f4", "#a6adc8", "#6c7086"
BLUE, GREEN, RED, YELLOW = "#89b4fa", "#a6e3a1", "#f38ba8", "#f9e2af"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gemini Proxy (Agent Ready)")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.server_proc: subprocess.Popen | None = None
        self._build_ui()
        self._load_env()

    def _build_ui(self):
        outer = tk.Frame(self, bg=BG, padx=20, pady=16)
        outer.pack(fill="both")

        tk.Label(outer, text="Gemini Proxy v2.1", font=("Segoe UI", 14, "bold"), bg=BG, fg=TX1).pack(anchor="w")
        tk.Label(outer, text="OpenAI-kompatibel · LAN-Freigabe · Token-Pruning für Agenten",
                 font=("Segoe UI", 9), bg=BG, fg=TX3).pack(anchor="w", pady=(0, 14))

        # ── Gemini API-Key ──
        self._section(outer, "Gemini API-Key")
        self.var_api_key = tk.StringVar()
        row = tk.Frame(outer, bg=BG)
        row.pack(fill="x", pady=(2, 6))
        self._entry(row, self.var_api_key, show="•").pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(row, "Prüfen", self._check_api_thread).pack(side="left", padx=(4, 0))
        self.lbl_api = tk.Label(outer, text="— aus https://aistudio.google.com/apikey",
                                bg=BG, fg=TX3, font=("Segoe UI", 9), anchor="w")
        self.lbl_api.pack(fill="x", pady=(0, 10))

        ttk.Separator(outer).pack(fill="x", pady=8)

        # ── Netzwerk-Einstellungen ──
        row2 = tk.Frame(outer, bg=BG)
        row2.pack(fill="x", pady=(4, 2))
        tk.Label(row2, text="Port", bg=BG, fg=TX2, font=("Segoe UI", 9)).pack(side="left")
        self.var_port = tk.StringVar(value="8642")
        self._entry(row2, self.var_port, width=8).pack(side="left", ipady=4, padx=(8, 20))
        tk.Label(row2, text="LAN-IP:", bg=BG, fg=TX2, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(row2, text=_local_ip(), bg=BG, fg=BLUE, font=("Consolas", 9)).pack(side="left", padx=(6, 0))

        tk.Label(outer, text="API-Secret (Token für Clients / Agenten im Netzwerk)",
                 bg=BG, fg=TX2, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 2))
        row3 = tk.Frame(outer, bg=BG)
        row3.pack(fill="x", pady=(0, 8))
        self.var_secret = tk.StringVar()
        self._entry(row3, self.var_secret).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(row3, "↺ Neu", self._gen_secret).pack(side="left", padx=(4, 0))

        ttk.Separator(outer).pack(fill="x", pady=8)

        # ── Start/Stop ──
        self.btn_start = tk.Button(outer, text="▶   Server starten",
                                   command=self._toggle_server,
                                   bg=BLUE, fg=BG, relief="flat",
                                   font=("Segoe UI", 10, "bold"),
                                   pady=9, cursor="hand2", bd=0)
        self.btn_start.pack(fill="x", pady=(4, 8))

        row_st = tk.Frame(outer, bg=BG)
        row_st.pack(fill="x", pady=(0, 6))
        self.lbl_dot = tk.Label(row_st, text="●", bg=BG, fg=RED, font=("Segoe UI", 13))
        self.lbl_dot.pack(side="left")
        self.lbl_status = tk.Label(row_st, text="Gestoppt", bg=BG, fg=TX3, font=("Segoe UI", 10))
        self.lbl_status.pack(side="left", padx=6)

        # ── Endpunkt-URLs ──
        tk.Label(outer, text="Netzwerk-Endpunkt-URLs (beide Formate funktionieren)",
                 bg=BG, fg=TX2, font=("Segoe UI", 9)).pack(anchor="w")

        self.var_url_base = tk.StringVar(value=f"http://{_local_ip()}:8642")
        self.var_url_v1   = tk.StringVar(value=f"http://{_local_ip()}:8642/v1")

        self._url_row(outer, "Base",   self.var_url_base)
        self._url_row(outer, "+ /v1",  self.var_url_v1)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.minsize(470, 0)

    def _section(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=TX2, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 2))

    def _entry(self, parent, var, show="", width=None):
        kw = dict(textvariable=var, bg=BG2, fg=TX1, relief="flat",
                  font=("Segoe UI", 10), insertbackground=TX1, bd=0)
        if show:
            kw["show"] = show
        if width:
            kw["width"] = width
        return tk.Entry(parent, **kw)

    def _btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         bg=BG2, fg=TX1, relief="flat",
                         font=("Segoe UI", 9), padx=10, pady=4,
                         cursor="hand2", bd=0, activebackground=BG3, activeforeground=TX1)

    def _url_row(self, parent, label: str, var: tk.StringVar):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(2, 2))
        tk.Label(row, text=label, bg=BG, fg=TX3,
                 font=("Segoe UI", 8), width=5, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, state="readonly",
                 bg=BG2, fg=GREEN, readonlybackground=BG2,
                 relief="flat", font=("Consolas", 10), bd=0
                 ).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 4))
        self._btn(row, "Kopieren", lambda v=var: self._copy_url(v)).pack(side="left")

    def _load_env(self):
        env = _read_env()
        self.var_api_key.set(env.get("GEMINI_API_KEY", ""))
        port = env.get("PORT", "8642")
        self.var_port.set(port)
        self._update_urls(port)

        secret = env.get("API_SECRET", "")
        if secret and secret not in ("change-me", "change-me-to-a-random-string"):
            self.var_secret.set(secret)
        else:
            self._gen_secret()

    def _update_urls(self, port: str):
        base = f"http://{_local_ip()}:{port}"
        self.var_url_base.set(base)
        self.var_url_v1.set(f"{base}/v1")

    def _gen_secret(self):
        self.var_secret.set(secrets.token_hex(16))

    def _check_api_thread(self):
        key = self.var_api_key.get().strip()
        if not key:
            self.lbl_api.config(text="— kein Key eingetragen", fg=TX3)
            return
        self.lbl_api.config(text="prüfe …", fg=TX2)
        threading.Thread(target=self._check_api_worker, args=(key,), daemon=True).start()

    def _check_api_worker(self, key: str):
        try:
            from google import genai
            client = genai.Client(api_key=key)
            models = list(client.models.list())
            gemini_names = [m.name for m in models if "gemini-" in (m.name or "").lower()]
            msg = f"✓ API-Key OK · {len(gemini_names)} Gemini-Modelle erkannt"
            self.after(0, lambda: self.lbl_api.config(text=msg, fg=GREEN))
        except Exception as e:
            self.after(0, lambda err=e: self.lbl_api.config(text=f"✗ {err}", fg=RED))

    def _toggle_server(self):
        if self.server_proc and self.server_proc.poll() is None:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        port = self.var_port.get().strip() or "8642"
        secret = self.var_secret.get().strip() or secrets.token_hex(16)
        lan_ip = _local_ip()

        _write_env({
            "API_SECRET": secret,
            "HOST": "0.0.0.0",
            "PORT": port,
            "GEMINI_API_KEY": self.var_api_key.get().strip(),
            "ENABLE_AGENT_PRUNING": "true",
        })

        self._update_urls(port)

        try:
            self.server_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", port],
                cwd=SCRIPT_DIR,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception as e:
            messagebox.showerror("Startfehler", str(e))
            return

        self.btn_start.config(text="■   Server stoppen", bg=RED, fg=BG)
        self.lbl_dot.config(fg=GREEN)
        self.lbl_status.config(text=f"Online im Netzwerk ({lan_ip}:{port})", fg=GREEN)
        self.after(2000, self._watch_server)

    def _stop_server(self):
        if self.server_proc:
            pid = self.server_proc.pid
            try:
                if sys.platform == "win32":
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.server_proc.terminate()
            except Exception:
                pass
            self.server_proc = None

        self.btn_start.config(text="▶   Server starten", bg=BLUE, fg=BG)
        self.lbl_dot.config(fg=RED)
        self.lbl_status.config(text="Gestoppt", fg=TX3)

    def _watch_server(self):
        if self.server_proc is None:
            return
        if self.server_proc.poll() is not None:
            self.server_proc = None
            self.btn_start.config(text="▶   Server starten", bg=BLUE, fg=BG)
            self.lbl_dot.config(fg=YELLOW)
            self.lbl_status.config(text="Unerwartet beendet", fg=YELLOW)
            return
        self.after(2000, self._watch_server)

    def _copy_url(self, var: tk.StringVar):
        self.clipboard_clear()
        self.clipboard_append(var.get())
        prev = self.lbl_status.cget("text")
        self.lbl_status.config(text=f"URL kopiert ✓  →  {var.get()}", fg=BLUE)
        self.after(2200, lambda: self.lbl_status.config(text=prev))

    def _on_close(self):
        self._stop_server()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()