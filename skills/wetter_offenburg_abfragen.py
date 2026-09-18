"""
Fragt das aktuelle Wetter für Offenburg über wttr.in ab.
"""
import requests

def wetter_offenburg_abfragen() -> str:
    """
    Ruft das aktuelle Wetter für Offenburg ab (Temperatur, Bedingung, Symbol).
    Nutzt den kostenlosen Dienst wttr.in – kein API-Key erforderlich.
    Beispiel: wetter_offenburg_abfragen()
    """
    try:
        url = "https://wttr.in/Offenburg?format=3&lang=de"
        response = requests.get(url, timeout=10)
        
        # FIX: Wir zwingen Python, den Text als UTF-8 zu lesen (für Emojis & °C)
        response.encoding = 'utf-8' 
        
        if response.status_code == 200:
            wetter_text = response.text.strip()
            return f"Das aktuelle Wetter: {wetter_text}"
        else:
            return "Der Wetterdienst ist momentan nicht erreichbar."

    except Exception as e:
        return f"Fehler beim Abrufen des Wetters: {e}"

AVAILABLE_SKILLS = [wetter_offenburg_abfragen]