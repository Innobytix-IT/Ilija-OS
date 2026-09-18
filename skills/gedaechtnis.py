"""
gedaechtnis.py – Langzeitgedächtnis für Ilija Public Edition
Nutzt ChromaDB + Sentence-Transformers für semantische Suche
"""

import os
import threading
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from datetime import datetime

MEMORY_DIR = os.path.abspath("memory")
COLLECTION = "ilija_memory"

_client     = None
_collection = None
_model      = None
_init_lock  = threading.Lock()   # Verhindert Mehrfach-Initialisierung in parallelen Threads


def _init():
    global _client, _collection, _model
    if _collection is not None:
        return
    with _init_lock:
        # Double-checked locking: anderer Thread könnte zwischen erstem Check und Lock fertig sein
        if _collection is not None:
            return
        os.makedirs(MEMORY_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=MEMORY_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")


def gedaechtnis_speichern(information: str, kategorie: str = "allgemein") -> str:
    """
    Speichert eine Information dauerhaft im Langzeitgedächtnis.
    Beispiel: gedaechtnis_speichern(information="Mein Name ist Manuel", kategorie="persoenlich")
    """
    _init()
    try:
        einbettung = _model.encode(information).tolist()
        doc_id     = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        _collection.add(
            documents  = [information],
            embeddings = [einbettung],
            ids        = [doc_id],
            metadatas  = [{"kategorie": kategorie, "datum": datetime.now().isoformat()}],
        )
        return f"✅ Gespeichert: '{information}'"
    except Exception as e:
        return f"❌ Speichern fehlgeschlagen: {e}"


def gedaechtnis_suchen(suchanfrage: str, max_ergebnisse: int = 5) -> str:
    """
    Sucht im Langzeitgedächtnis nach relevanten Informationen.
    Beispiel: gedaechtnis_suchen(suchanfrage="Was weißt du über mich?")
    """
    _init()
    try:
        einbettung = _model.encode(suchanfrage).tolist()
        ergebnisse = _collection.query(
            query_embeddings = [einbettung],
            n_results        = min(max_ergebnisse, _collection.count() or 1),
        )
        docs = ergebnisse.get("documents", [[]])[0]
        if not docs:
            return "🧠 Keine relevanten Erinnerungen gefunden."
        zeilen = [f"  • {doc}" for doc in docs]
        return "🧠 Erinnerungen:\n" + "\n".join(zeilen)
    except Exception as e:
        return f"❌ Suche fehlgeschlagen: {e}"


def gedaechtnis_loeschen_alles() -> str:
    """Löscht das gesamte Langzeitgedächtnis (nicht rückgängig machbar!)."""
    global _collection
    _init()
    try:
        anzahl = _collection.count()
        _client.delete_collection(COLLECTION)
        _collection = _client.get_or_create_collection(
            name     = COLLECTION,
            metadata = {"hnsw:space": "cosine"}
        )
        return f"🗑️ Gedächtnis geleert. {anzahl} Einträge gelöscht."
    except Exception as e:
        return f"❌ Löschen fehlgeschlagen: {e}"


def gedaechtnis_anzahl() -> str:
    """Gibt die Anzahl der gespeicherten Erinnerungen zurück."""
    _init()
    try:
        return f"🧠 Gedächtnis enthält {_collection.count()} Einträge."
    except Exception as e:
        return f"❌ Fehler: {e}"


AVAILABLE_SKILLS = [
    gedaechtnis_speichern,
    gedaechtnis_suchen,
    gedaechtnis_loeschen_alles,
    gedaechtnis_anzahl,
]
