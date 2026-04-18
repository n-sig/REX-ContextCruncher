# ContextCruncher — Agent Handoff Prompt

> **Kopiere diesen gesamten Text als erste Nachricht in eine neue Claude-Cowork-Session.**
> Wähle dabei den ContextCruncher-Ordner als Workspace-Folder aus.

---

## Dein Auftrag

Du übernimmst die Weiterentwicklung von **ContextCruncher** — einem AI-optimierten Clipboard-Manager für Windows mit Screen-OCR, Multi-Level Token-Komprimierung und einem MCP-Server. Alles läuft lokal, kein Cloud, kein Admin, kein Network.

Dein Ziel: **Das Programm in eine polished, stabile, funktional vollständige v1.0-Release bringen.** Es soll sich wie ein professionelles Tool anfühlen — schnell, zuverlässig, durchdacht.

Die Sprache im Code, Kommentaren und Commits ist **Englisch**. Die Kommunikation mit mir ist **Deutsch**.

---

## Schritt 0 — Einrichten

1. **Lies zuerst die CLAUDE.md** im Root des Projekts — sie enthält die Architektur, Design-Entscheidungen, Hotkeys, und alle strikten Regeln.
2. **Lies die DEV-TRACKER.md** — sie enthält alle bisherigen Bugs (BUG-01 bis BUG-14), Features (FR-01 bis FR-05.4), und Code-Review-Fixes. Alles was bisher passiert ist, steht dort.
3. **Lauf die Test-Suite** um den aktuellen Stand zu verifizieren:
   ```bash
   python -m pytest tests/ -v
   ```
   Erwartetes Ergebnis: **333 passed, 3 skipped** (die 3 Skips sind Windows-only WinRT-Tests, die auf Linux nicht laufen).
4. **Verstehe die Architektur** bevor du irgendetwas änderst:
   - `main.py` → Entry Point, GUI-Flow, Hotkey-Callbacks
   - `text_processor.py` → Deterministische 6-Phasen Token-Komprimierung
   - `prompt_optimizer.py` → LLM-basierte AI-Komprimierung mit 4-Schichten Hybrid-Extraktion
   - `content_router.py` → Intelligente Content-Type-Erkennung + Strategie-Routing
   - `security_scanner.py` → 2-Pass Secret Redaction (Pattern + Shannon-Entropy)
   - `mcp_server.py` → 22 MCP-Tools für AI-Agenten
   - `settings.py` → Scrollbares Tkinter Settings-Fenster
   - `config.py` → JSON Settings Persistence

---

## Strikte Regeln (NIEMALS brechen)

Diese Regeln sind architektonische Invarianten. Jede Verletzung führt zu schwer debugbaren Problemen:

1. **Single Tk Root:** Alle Tkinter-UI läuft auf `TkUIThread`. Erstelle NIEMALS zusätzliche `tk.Tk()`-Instanzen. Immer `Toplevel` verwenden.
2. **In-Memory Only:** `TextStack` nutzt `deque(maxlen=50)`. Keine Disk-Persistenz by Design.
3. **Deterministic Compression:** `minify_for_ai()` ist eine pure Function. Gleicher Input → immer gleicher Output. Keine LLM-Calls für deterministische Komprimierung.
4. **Security First:** `redact_secrets()` läuft IMMER VOR jedem LLM-Call. Secrets werden NIEMALS probabilistisch behandelt.
5. **Hybrid-Extraktion:** Code-Blöcke, Tabellen, Inline-Refs (`backticks`), und Constraint-Sätze (NEVER/ALWAYS/MUST) werden physisch extrahiert bevor ein LLM den Text sieht. Nach LLM-Komprimierung werden sie verbatim wieder eingesetzt.
6. **Zero Network im Core:** Nur `prompt_optimizer.py` (opt-in) und `mcp_server.py` (stdio) dürfen Netzwerk nutzen. Alle anderen Module sind offline.
7. **Windows Only:** Platform ist Windows 10 (1903+) / Windows 11. OCR nutzt native Windows WinRT APIs.
8. **Tests vor jedem Commit:** `python -m pytest tests/ -v` muss grün sein.

---

## Aktueller Stand (v0.2.0-beta)

### Was funktioniert
- ✅ Screen OCR (Region + Fullscreen) mit Multi-Language Support
- ✅ 6-Phasen deterministische Komprimierung (~31% Savings auf CLAUDE.md)
- ✅ LLM-basierte AI-Komprimierung (Ollama/OpenAI/Anthropic) mit Hybrid-Architektur
- ✅ 4-Schichten-Extraktion (Code, Tabellen, Inline-Refs, Constraints) vor LLM
- ✅ Content-Router mit automatischer Content-Type-Erkennung (code, data, log, prose, agent_config)
- ✅ Security Scanner mit 2-Pass Architektur (Patterns + Entropy)
- ✅ MCP-Server mit 22 Tools
- ✅ Token Heatmap mit Cost-Estimates und Context-Window-Warnung
- ✅ Settings UI (scrollbar, AI-Compression-Konfiguration, Singleton-Guard)
- ✅ Variant-System (Original → Compressed → AI)
- ✅ Mouse-Hotkeys (X1/X2 Seitentasten)
- ✅ 333 Tests, 0 Failures

### Bekannte offene Punkte / Verbesserungspotenzial

1. **Kein End-to-End Test der AI-Komprimierung** — Die `compress()`-Funktion in `prompt_optimizer.py` hat keine automatisierten Tests (nur die `optimize()`-Funktion und Profiles sind getestet). Braucht Mock-basierte Tests für den gesamten Flow: Secret-Redaction → Code-Extraktion → LLM-Call → Reinsertion → Post-Validation.

2. **Post-Validation nur als Warnings** — `_validate_compression()` vergleicht Zahlen/Daten/TODOs zwischen Original und Ergebnis, aber gibt nur Warnings aus. Es gibt keine UI-Anzeige für die Warnings und keinen automatischen Fallback.

3. **Content-Router Tests unvollständig** — `test_content_router.py` existiert, aber testet nicht den neuen `agent_config` Content-Type.

4. **BUG-13 offen (By Design)** — Deterministische Kompression zerstört Python-Indentation bei nicht-gefenctem Code. Könnte durch Indentation-Detection im `_phase_normalize` gelöst werden.

5. **Build nicht getestet** — Der PyInstaller Build (`pyinstaller build.spec`) wurde seit den letzten großen Änderungen nicht mehr getestet. `content_router.py` und `prompt_optimizer.py` fehlen vermutlich in den `hiddenimports` der `build.spec`.

6. **Settings UI polishing** — Das AI-Compression-Panel funktioniert, aber könnte eine "Test Connection"-Funktion für Ollama brauchen, und die API-Key-Eingabe ist ein einfaches Entry-Feld ohne Validation.

7. **Variant-Picker (Win+V Popup)** — Zeigt derzeit nur Text-Labels. Könnte Komprimierungsstufe (🪶💀☢️🤖) und Token-Count anzeigen.

8. **Toast-Benachrichtigungen** — Die AI-Komprimierung zeigt "🤖 AI compressing..." und dann das Ergebnis per Toast. Aber bei Fehlern (Ollama nicht erreichbar, Timeout) gibt es keine klare User-Feedback-Loop.

9. **MCP-Server kennt `compress()` nicht** — Der MCP-Server hat `optimize_prompt` aber kein dediziertes `ai_compress` Tool. Das wäre nützlich damit AI-Agenten direkt die Hybrid-Komprimierung nutzen können.

10. **Kein Auto-Update / Version-Check** — Für v1.0 wäre eine einfache Version-Anzeige im Tray-Menü und Settings sinnvoll.

---

## Technische Details die du kennen musst

### Varianten-System
Jeder Stack-Eintrag speichert mehrere vorberechnete Varianten:
- **Original** — Unverändert
- **Compressed** — Deterministisch komprimiert via `smart_route(text, intent="understand")` in `content_router.py`
- **AI** — LLM-komprimiert (async, wird im Hintergrund angehängt wenn `ai_compress_enabled=True`)

### Config-Keys für AI-Komprimierung (in `config.json`)
```json
{
  "ai_compress_enabled": false,
  "ai_compress_provider": "ollama",
  "ai_compress_model": "llama3.2",
  "ai_compress_aggressive": false
}
```
API-Keys separat in `%APPDATA%/ContextCruncher/llm_keys.json`.

### 4-Schichten Hybrid-Extraktion (prompt_optimizer.py)
Extraktionsreihenfolge vor LLM-Call:
1. `_extract_code_blocks()` → `⟨CODE_BLOCK_N⟩` (Fenced + eingerückt)
2. `_extract_tables()` → `⟨TABLE_N⟩` (Markdown-Tabellen)
3. `_extract_inline_refs()` → `⟨REF_N⟩` (Backtick-Referenzen)
4. `_extract_constraints()` → `⟨RULE_N⟩` (NEVER/ALWAYS/MUST/DO NOT Sätze)

Reinsertion in umgekehrter Reihenfolge nach LLM-Response.

### Threading-Modell
- Global Hotkeys: Daemon Threads (pynput keyboard + optional mouse)
- Alle Tkinter UI: `TkUIThread`
- AI-Komprimierung: Separater Daemon Thread (async fire-and-forget)
- `_ignore_next_changes` Counter verhindert Auto-Crunch Feedback-Loops
- `_scan_active` Event verhindert parallele OCR-Scans

---

## Qualitätsstandards

Für jede Änderung die du machst:

1. **Tests schreiben** — Jede neue Funktion und jeder Bugfix braucht mindestens einen Test. Bestehende Tests (`tests/`) als Referenz nutzen.
2. **Tests laufen lassen** — `python -m pytest tests/ -v` muss grün bleiben.
3. **DEV-TRACKER.md aktualisieren** — Neue Bugs als BUG-XX, neue Features als FR-XX dokumentieren. Root Cause, Fix, und Status angeben.
4. **CLAUDE.md aktuell halten** — Wenn du neue Module oder signifikante Architektur-Änderungen einführst, CLAUDE.md updaten.
5. **Keine Breaking Changes** — Bestehende MCP-Tool-Signaturen und Config-Keys nicht ändern ohne Backward-Compat.
6. **Commit-Messages auf Englisch** — Kurz, präzise, im Imperativ ("Add X", "Fix Y", nicht "Added X").
7. **Code-Qualität** — Type Hints verwenden, Docstrings für öffentliche Funktionen, keine Magic Numbers.

---

## Empfohlene Reihenfolge der Arbeit

### Phase 1 — Stabilisierung & Tests (Sofort)
- [ ] Tests für `compress()` in `prompt_optimizer.py` schreiben (Mock-basiert)
- [ ] Tests für `agent_config` Content-Type in `content_router.py` ergänzen
- [ ] Tests für die 4 neuen Extraktoren (`_extract_constraints`, `_extract_inline_refs`, `_extract_tables`) schreiben
- [ ] `build.spec` aktualisieren — `content_router` und `prompt_optimizer` in `hiddenimports` aufnehmen
- [ ] PyInstaller Build testen

### Phase 2 — UX Polish (Nächster Schritt)
- [ ] AI-Compression Warnings im Toast anzeigen (Validierungs-Warnings aus `CompressResult.warnings`)
- [ ] Error-Handling verbessern: Ollama nicht erreichbar, Timeout, falsches Modell → klare Toast-Messages
- [ ] Variant-Picker: Komprimierungsstufe und Token-Count pro Variante anzeigen
- [ ] Settings: "Test Connection" Button für Ollama
- [ ] Version-Anzeige im Tray-Menü und Settings-Dialog

### Phase 3 — Feature Completion (Danach)
- [ ] MCP-Tool `ai_compress` für AI-Agenten hinzufügen
- [ ] BUG-13 fixen: Indentation-Detection für nicht-gefencten Code in `_phase_normalize`
- [ ] Eval-Suite erweitern: `evals/run_eval.py` mit CLAUDE.md-Benchmark für LLM-Komprimierung
- [ ] Context-Pack Verbesserung: Prioritätsbasiertes Laden mit Relevanz-Scoring

### Phase 4 — Release-Vorbereitung (Finales)
- [ ] README.md aktualisieren mit AI-Compression Sektion
- [ ] SECURITY.md aktualisieren (Hybrid-Architektur, 4-Schichten-Extraktion)
- [ ] Changelog für v1.0 schreiben
- [ ] Final Full Test Run + manueller QA-Test auf Windows
- [ ] Release Build erstellen und testen

---

## Befehle die du regelmäßig brauchst

```bash
# Tests laufen lassen
python -m pytest tests/ -v

# Einzelnen Test laufen lassen
python -m pytest tests/test_prompt_optimizer.py -v

# Compression Benchmark
python evals/run_eval.py

# App starten (nur auf Windows)
python src/contextcruncher/main.py

# Build erstellen (nur auf Windows mit PyInstaller installiert)
pyinstaller build.spec

# MCP-Server standalone testen
python -m contextcruncher.mcp_server
```

---

## Wichtig: Was NICHT tun

- **KEINE neuen Dependencies** ohne guten Grund. Das Projekt hat bewusst minimale Dependencies (pynput, Pillow, pyperclip, pystray, WinRT, mcp, tiktoken, httpx).
- **KEIN Cloud/Telemetry** einbauen. "Zero Footprint" ist ein Kernfeature.
- **KEINE tkinter.Tk() Instanzen** erstellen. Immer `Toplevel`.
- **KEINE LLM-Calls** in deterministische Pfade einbauen. `text_processor.py` und `skeletonizer.py` sind pure functions.
- **KEINE bestehenden Tests löschen** oder skippen. Wenn ein Test nach einer Änderung fehlschlägt, den Code fixen, nicht den Test.
- **KEINE Secrets in Commits** — `llm_keys.json`, `config.json` mit API-Keys, etc. sind in `.gitignore`.

---

Starte mit Phase 1. Lies zuerst CLAUDE.md und DEV-TRACKER.md, dann lauf die Tests, dann fang an die fehlenden Tests zu schreiben. Zeige mir regelmäßig den Fortschritt und frage bei Unklarheiten nach.
