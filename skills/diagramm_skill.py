"""
diagramm_skill.py – Diagramme/Charts für Ilija (Ilija OS)
=========================================================
Erstellt Balken-, Linien- und Kreisdiagramme als PNG in den Ilija-Markenfarben
(Gold/Blau). Ausgabe nach ~/Ilija-Ablage/Dokumente.
"""
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # headless (keine Anzeige nötig)
import matplotlib.pyplot as plt

AUSGABE = "/srv/ilija-ablage/Dokumente"
# Ilija-Markenpalette (Gold + Blau)
_FARBEN = ["#E0A82E", "#2E86DE", "#C8871B", "#5AA9E6", "#8A6D1D", "#1B4F8C",
           "#F0C75E", "#3AA0C8"]


def _ziel(dateiname: str) -> str:
    os.makedirs(AUSGABE, exist_ok=True)
    if not dateiname:
        dateiname = "diagramm_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    pfad = dateiname if os.path.isabs(dateiname) else os.path.join(AUSGABE, dateiname)
    if not pfad.lower().endswith(".png"):
        pfad += ".png"
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    return pfad


def _daten(text: str):
    labels, werte = [], []
    for teil in (text or "").replace("\r\n", "\n").replace("\n", ";").split(";"):
        teil = teil.strip()
        if not teil or ":" not in teil:
            continue
        label, _, wert = teil.rpartition(":")
        try:
            werte.append(float(wert.strip().replace(",", ".")))
            labels.append(label.strip())
        except ValueError:
            continue
    return labels, werte


def diagramm_erstellen(typ: str = "balken", titel: str = "", daten: str = "",
                       dateiname: str = "") -> str:
    """
    Erstellt ein Diagramm als PNG (Ilija-Gold/Blau). typ: 'balken', 'linie' oder 'kreis'.
    daten: 'Label:Wert'-Paare, durch ';' oder Zeilenumbruch getrennt. Beispiel:
    diagramm_erstellen(typ="balken", titel="Umsatz 2026", daten="Jan:1000;Feb:1500;Mär:1200")
    """
    labels, werte = _daten(daten)
    if not werte:
        return "❌ Keine gültigen Daten. Format: 'Label:Wert;Label:Wert' (z. B. 'Jan:1000;Feb:1500')."
    t = (typ or "balken").lower()
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=130)
    fig.patch.set_facecolor("#0E1A24")
    ax.set_facecolor("#0E1A24")
    if t in ("kreis", "pie", "torte"):
        ax.pie(werte, labels=labels, autopct="%1.0f%%",
               colors=_FARBEN, textprops={"color": "#EAF2F8"})
        ax.axis("equal")
    elif t in ("linie", "line"):
        ax.plot(labels, werte, marker="o", color="#E0A82E", linewidth=2.4,
                markerfacecolor="#2E86DE", markersize=7)
        _achsen(ax)
    else:  # Balken
        ax.bar(labels, werte, color=[_FARBEN[i % len(_FARBEN)] for i in range(len(werte))])
        _achsen(ax)
    if titel:
        ax.set_title(titel, color="#F0C75E", fontsize=14, fontweight="bold", pad=14)
    fig.tight_layout()
    pfad = _ziel(dateiname)
    fig.savefig(pfad, facecolor=fig.get_facecolor())
    plt.close(fig)
    return f"✓ Diagramm ({t}) erstellt: {pfad}"


def _achsen(ax):
    ax.tick_params(colors="#AEC4D6")
    for s in ax.spines.values():
        s.set_color("#2A3B49")
    ax.grid(axis="y", color="#1C2A36", linewidth=0.8)


AVAILABLE_SKILLS = [diagramm_erstellen]
