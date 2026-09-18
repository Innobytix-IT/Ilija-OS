"""
muenze_werfen.py – Münzwurf-Skill für Ilija Public Edition
"""
import random


def muenze_werfen() -> str:
    """
    Wirft eine virtuelle Münze und gibt Kopf oder Zahl zurück.
    Nützlich für schnelle Zufallsentscheidungen zwischen zwei Optionen.
    Beispiel: muenze_werfen()
    """
    ergebnis = random.randint(0, 1)
    return "🪙 Kopf!" if ergebnis == 0 else "🪙 Zahl!"


AVAILABLE_SKILLS = [muenze_werfen]
