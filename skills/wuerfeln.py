"""
wuerfeln.py – Würfel-Skill für Ilija Public Edition
"""
import random


def wuerfeln(max: int = 6) -> str:
    """
    Würfelt eine zufällige Zahl zwischen 1 und dem angegebenen Maximum.
    Standard: 6-seitiger Würfel. Für D20 einfach max=20 angeben.
    Beispiel: wuerfeln(max=20)
    """
    ergebnis = random.randint(1, max)
    return f"🎲 Gewürfelt (1–{max}): **{ergebnis}**"


AVAILABLE_SKILLS = [wuerfeln]
