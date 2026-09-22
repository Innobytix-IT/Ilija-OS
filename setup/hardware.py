#!/usr/bin/env python3
"""Ilija OS – Hardware-Erkennung für die Lokale-KI-Tauglichkeit.

Prüft RAM, CPU (AVX2/Kerne), GPU (NVIDIA/VRAM) und freien Speicher und leitet
daraus ab, ob ein lokales LLM (Qwen2.5-7B) sinnvoll läuft oder nur die Cloud-KI
(Gemini) bzw. „ohne KI" in Frage kommt.

Schwellen (siehe OFFEN.md):
  lokal möglich, wenn genug Disk (>=6 GB) UND (NVIDIA-GPU >=6 GB VRAM
  ODER (AVX2 UND RAM >=16 GB)).
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess

# Empfohlenes mitgeliefertes Modell
EMPFOHLENES_MODELL = "qwen2.5:7b"
MIN_RAM_GB = 16
MIN_VRAM_GB = 6
MIN_DISK_GB = 6


def _ram_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for zeile in f:
                if zeile.startswith("MemTotal:"):
                    return round(int(zeile.split()[1]) / 1024 / 1024, 1)
    except Exception:
        pass
    return 0.0


def _cpu() -> tuple[int, bool, str]:
    kerne = os.cpu_count() or 1
    avx2 = False
    modell = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            txt = f.read()
        avx2 = bool(re.search(r"\bavx2\b", txt))
        m = re.search(r"model name\s*:\s*(.+)", txt)
        if m:
            modell = m.group(1).strip()
    except Exception:
        pass
    return kerne, avx2, modell


def _gpu() -> tuple[str | None, float]:
    """NVIDIA-GPU via nvidia-smi. Rückgabe (Name, VRAM_GB) oder (None, 0)."""
    try:
        aus = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if aus.returncode == 0 and aus.stdout.strip():
            name, mem = [x.strip() for x in aus.stdout.strip().splitlines()[0].split(",")]
            return name, round(int(float(mem)) / 1024, 1)
    except Exception:
        pass
    return None, 0.0


def _disk_frei_gb(pfad: str = "~/.ollama") -> float:
    p = os.path.expanduser(pfad)
    while not os.path.exists(p) and p != "/":
        p = os.path.dirname(p)
    try:
        return round(shutil.disk_usage(p).free / 1024 ** 3, 1)
    except Exception:
        return 0.0


def erkenne() -> dict:
    ram = _ram_gb()
    kerne, avx2, cpu_modell = _cpu()
    gpu_name, vram = _gpu()
    disk = _disk_frei_gb()

    genug_disk = disk >= MIN_DISK_GB
    gpu_ok = gpu_name is not None and vram >= MIN_VRAM_GB
    cpu_ok = avx2 and ram >= MIN_RAM_GB
    lokal_moeglich = genug_disk and (gpu_ok or cpu_ok)

    if gpu_ok and vram >= 8:
        qualitaet = "gpu"          # schnell
    elif cpu_ok:
        qualitaet = "cpu"          # läuft, langsamer
    else:
        qualitaet = None

    gruende: list[str] = []
    if not gpu_ok:
        if not avx2:
            gruende.append("Prozessor ohne AVX2")
        if ram < MIN_RAM_GB:
            gruende.append(f"nur {ram:g} GB RAM ({MIN_RAM_GB} GB nötig)")
    if not genug_disk:
        gruende.append(f"nur {disk:g} GB Speicher frei ({MIN_DISK_GB} GB nötig)")

    return {
        "ram_gb": ram,
        "cores": kerne,
        "avx2": avx2,
        "cpu_model": cpu_modell,
        "gpu_name": gpu_name,
        "vram_gb": vram,
        "disk_free_gb": disk,
        "lokal_moeglich": lokal_moeglich,
        "qualitaet": qualitaet,           # 'gpu' | 'cpu' | None
        "gruende": gruende,
        "modell": EMPFOHLENES_MODELL,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(erkenne(), indent=2, ensure_ascii=False))
