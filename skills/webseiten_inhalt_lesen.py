"""
webseiten_inhalt_lesen.py – Webseiten lesen & Internetrecherche für Ilija Public Edition

Suche-Priorität:
  1. DuckDuckGo (kostenlos, kein Key, Region de-de)
  2. Google Custom Search API (100 Anfragen/Tag gratis)
     → API-Key in .env: GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_CX
     → Einrichten: console.cloud.google.com → Custom Search API aktivieren
                   programmablesearchengine.google.com → Engine erstellen → CX kopieren
"""

import os
import re
import requests
from urllib.parse import quote_plus, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
TIMEOUT = 15


# ── Google Custom Search (optional, wenn API-Key gesetzt) ─────────────────────

def _google_suche(suchanfrage: str, max_ergebnisse: int = 5) -> list | None:
    """
    Sucht über Google Custom Search API.
    Gibt Liste von Dicts {title, body, href} zurück oder None wenn kein Key.
    """
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
    cx      = os.getenv("GOOGLE_SEARCH_CX", "").strip()
    if not api_key or not cx:
        return None  # Kein Key → Fallback auf DuckDuckGo

    try:
        params = {
            "key":  api_key,
            "cx":   cx,
            "q":    suchanfrage,
            "num":  min(max_ergebnisse, 10),
            "lr":   "lang_de",
            "hl":   "de",
        }
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params, timeout=TIMEOUT
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        return [
            {
                "title": item.get("title", ""),
                "body":  item.get("snippet", ""),
                "href":  item.get("link", ""),
            }
            for item in items
        ]
    except Exception as e:
        print(f"[Google Search] Fehler: {e}")
        return None


# ── DuckDuckGo ────────────────────────────────────────────────────────────────

def _ddg_suche(suchanfrage: str, max_ergebnisse: int = 5) -> list | None:
    """Sucht über DuckDuckGo (deutsche Region)."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(
                suchanfrage,
                region="de-de",
                max_results=max_ergebnisse,
            ))
        return results if results else None
    except Exception as e:
        print(f"[DuckDuckGo] Fehler: {e}")
        return None


# ── Öffentliche Skills ────────────────────────────────────────────────────────

def internet_suche(suchanfrage: str, max_ergebnisse: int = 5) -> str:
    """
    Sucht im Internet (Google wenn API-Key vorhanden, sonst DuckDuckGo).
    Kein API-Key nötig — Google optional für bessere deutsche Ergebnisse.
    Beispiel: internet_suche(suchanfrage="KI-Trends 2025")
    """
    max_ergebnisse = int(max_ergebnisse)

    # Priorität 1: Google (falls Key gesetzt)
    results = _google_suche(suchanfrage, max_ergebnisse)
    quelle  = "Google"

    # Priorität 2: DuckDuckGo
    if not results:
        results = _ddg_suche(suchanfrage, max_ergebnisse)
        quelle  = "DuckDuckGo"

    if not results:
        return f"🔍 Keine Ergebnisse gefunden für: '{suchanfrage}'"

    output = [f"🔍 {quelle}-Suchergebnisse für: '{suchanfrage}'\n"]
    for i, r in enumerate(results, 1):
        output.append(
            f"{i}. {r.get('title', '')}\n"
            f"   {r.get('body', '')[:200]}\n"
            f"   🔗 {r.get('href', '')}"
        )
    return "\n\n".join(output)


def webseite_lesen(url: str) -> str:
    """
    Liest den Textinhalt einer Webseite.
    Beispiel: webseite_lesen(url="https://example.com")
    """
    url = url.strip()
    if not url.startswith("http"):
        match = re.search(r'https?://[^\s"\'<>]+', url)
        if match:
            url = match.group(0).rstrip(".,)")
        else:
            return f"❌ Keine gültige URL gefunden in: {url[:200]}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        domain = urlparse(url).netloc
        return f"🌐 {domain}\n{'─'*50}\n{text[:8000]}"
    except Exception as e:
        return f"❌ Fehler beim Laden von {url}: {e}"


def suche_und_lese_erste_seite(suchanfrage: str) -> str:
    """
    Sucht im Internet und liest automatisch die erste Ergebnis-Seite.
    Nutzt Google (falls Key gesetzt) oder DuckDuckGo.
    Beispiel: suche_und_lese_erste_seite(suchanfrage="KI-Trends 2025")
    """
    results = _google_suche(suchanfrage, 5) or _ddg_suche(suchanfrage, 5)

    if not results:
        return f"🔍 Keine Ergebnisse gefunden für: '{suchanfrage}'"

    erste_url = results[0].get("href", "")
    if not erste_url:
        return f"❌ Keine URL in Suchergebnissen für: '{suchanfrage}'"

    seiten_inhalt = webseite_lesen(erste_url)
    return (
        f"SUCHE: '{suchanfrage}'\n"
        f"QUELLE: {erste_url}\n"
        f"{'═'*60}\n"
        f"{seiten_inhalt}"
    )


def news_abrufen(thema: str = "Deutschland") -> str:
    """
    Ruft aktuelle Nachrichten zu einem Thema ab.
    Beispiel: news_abrufen(thema="Technologie")
    """
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news(thema, region="de-de", max_results=6))
        if results:
            output = [f"📰 Aktuelle News: '{thema}'\n"]
            for r in results:
                datum = r.get("date", "")[:10]
                output.append(
                    f"• {r.get('title', '')}\n"
                    f"  {datum} — {r.get('source', '')}\n"
                    f"  {r.get('body', '')[:150]}\n"
                    f"  🔗 {r.get('url', '')}"
                )
            return "\n\n".join(output)
    except Exception:
        pass
    return internet_suche(f"{thema} news aktuell", max_ergebnisse=6)


def google_suche_einrichten(api_key: str, cx: str) -> str:
    """
    Speichert den Google Custom Search API-Key und die Search Engine ID.
    Einmalig ausführen — danach nutzt internet_suche automatisch Google.
    Beispiel: google_suche_einrichten(api_key="AIza...", cx="017...")
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    def _set(lines, key, val):
        for i, l in enumerate(lines):
            if l.strip().startswith(f"{key}="):
                lines[i] = f"{key}={val}\n"
                return lines
        lines.append(f"{key}={val}\n")
        return lines

    lines = _set(lines, "GOOGLE_SEARCH_API_KEY", api_key.strip())
    lines = _set(lines, "GOOGLE_SEARCH_CX", cx.strip())

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Sofort laden
    os.environ["GOOGLE_SEARCH_API_KEY"] = api_key.strip()
    os.environ["GOOGLE_SEARCH_CX"]      = cx.strip()

    # Testsuche
    test = _google_suche("Test", 1)
    if test:
        return (
            f"✅ Google Custom Search eingerichtet!\n"
            f"API-Key: {api_key[:8]}****\n"
            f"Search Engine ID: {cx}\n"
            f"Testsuche: {test[0].get('title', 'OK')}\n\n"
            f"Ab sofort nutzt internet_suche automatisch Google."
        )
    return (
        f"⚠️ Keys gespeichert, aber Testsuche schlug fehl.\n"
        f"Prüfe: console.cloud.google.com → Custom Search API aktiviert?\n"
        f"Prüfe: programmablesearchengine.google.com → CX korrekt?"
    )


def wikipedia_suche(suchbegriff: str, sprache: str = "de") -> str:
    """
    Sucht einen Begriff auf Wikipedia und gibt eine Zusammenfassung zurück.
    Beispiel: wikipedia_suche(suchbegriff="Künstliche Intelligenz")
    """
    try:
        titel_key = suchbegriff.replace(" ", "_")
        api_url = (
            f"https://{sprache}.wikipedia.org/api/rest_v1/page/summary/"
            f"{titel_key}"
        )
        r = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data    = r.json()
        titel   = data.get("title", suchbegriff)
        extract = data.get("extract", "Keine Zusammenfassung verfügbar.")
        url     = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return (
            f"📖 {titel} (Wikipedia)\n\n"
            f"{extract[:3000]}"
            + (f"\n\n🔗 {url}" if url else "")
        )
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"❌ '{suchbegriff}' nicht auf Wikipedia gefunden."
        return f"❌ Wikipedia-Fehler: {e}"
    except Exception as e:
        return f"❌ Fehler: {e}"


AVAILABLE_SKILLS = [
    webseite_lesen,
    internet_suche,
    suche_und_lese_erste_seite,
    news_abrufen,
    wikipedia_suche,
]
