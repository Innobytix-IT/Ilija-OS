# Ilija OS – ToDo-Liste

## Offen

### Distribution & Release
- [ ] **GitHub Releases einrichten**: Fertige Ilija-OS-ISO über GitHub Releases bereitstellen (bis 2 GB pro Datei, direkt verlinkbar)
- [ ] **Release-Workflow**: Tagging-Prozess definieren (z.B. `v2.1.0`) → ISO bauen → als Release hochladen
- [ ] **Update-Skript für End-User**: `ilija-update` auf `curl`-basiertes Tarball-Download umstellen sobald Repo-Zugang nicht garantiert ist

### Claude Desktop API – Verbesserungen
- [ ] **Autostart**: `app.py` beim Windows-Start automatisch ausführen (Aufgabenplanung oder Startordner)
- [ ] **Modell-Liste dynamisch**: Verfügbare Claude-Modelle per `claude models` statt Hardcode
- [ ] **Streaming**: Echtes Token-Streaming statt SSE-Einmal-Wrap (für bessere UX in Ilija)
- [ ] **Multi-Turn**: Gesprächsverlauf an claude CLI übergeben (z. B. via `--resume` oder Prompt-Format)
- [ ] **Fehlerdiagnose im UI**: Fehlermeldungen aus dem Subprocess im Tkinter-Launcher anzeigen

---

## Erledigt
