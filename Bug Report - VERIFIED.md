# 🐞 Verified QA Report — ContextCruncher v0.1.0-alpha / v0.2.0-beta

**Erstellt:** 2026-04-12  
**Zuletzt aktualisiert:** 2026-04-13  
**Methode:** Statische Code-Analyse aller Module in `src/contextcruncher/`  
**Status-Legende:** ✅ Bestätigt · ⚠️ Teilweise · 🟢 Behoben · ❌ Nicht reproduzierbar

---

## 🟢 Alle verifizierten Bugs behoben — Übersicht

| ID | Priorität | Problem | Datei(en) | Tests |
|---|---|---|---|---|
| ~~BUG-01~~ | P1 🚨 | Security Scanner: High-Entropy Secrets nicht erkannt | `security_scanner.py` | `test_security_scanner.py` |
| ~~BUG-02~~ | P1 🚨 | Skeletonizer kein JSON/XML-Handler, README/MCP-Name falsch | `skeletonizer.py`, `mcp_server.py`, `README.md` | `test_skeletonizer.py` |
| ~~BUG-03~~ | P1 🚨 | Stack-Zähler utopisch hoch (kurze Clipboard-Events) | `clipboard_monitor.py` | `test_clipboard_monitor.py` |
| ~~BUG-04~~ | P2 🟠 | OCR-Spracheinstellung fehlt im Settings-UI | `settings.py`, `ocr.py` | `test_ocr_languages.py` |
| ~~BUG-05~~ | P2 🟠 | Hotkey-Kollisionsprüfung fehlt | `settings.py`, `config.py` | `test_hotkey_collision.py` |
| ~~BUG-06~~ | P2 🟠 | OCR schlägt bei sehr kleinen Auswahlen fehl | `ocr.py` | `test_ocr_upscale.py` |
| ~~BUG-07~~ | P3 🟡 | Auto-Crunch: Kein Debouncing | `clipboard_monitor.py` | `test_clipboard_debounce.py` |
| ~~BUG-08~~ | P3 🟡 | Autostart funktioniert nur für kompilierte .exe | `config.py` | `test_autostart_command.py` |

**Test-Suite:** 155 passed · 3 skipped (WinRT/Windows-only) · 1 failed (pre-existing, unrelated)

---

## 🟢 Behoben in dieser Session (BUG-01 bis BUG-08)

### ~~[BUG-01]~~ Security Scanner: High-Entropy Secrets werden nicht erkannt
**Status:** 🟢 Behoben  
**Datei:** `security_scanner.py`  
**Commit-Scope:** Kompletter Rewrite mit Zwei-Pass-Architektur

**Ursache:** Nur 6 hardcodierte Regex-Patterns. AWS Secret Keys, Stripe, OpenAI u. a. nicht abgedeckt. Kein Entropie-Fallback für unbekannte Secrets.

**Fix:**
- Pass 1: Erweiterte Patterns — `[AWS_SECRET_REDACTED]`, `[STRIPE_KEY_REDACTED]`, `[AI_API_KEY_REDACTED]` u. a.
- Pass 2: Shannon-Entropy-Check (`≥ 4.5`) als Catch-all für unbekannte High-Entropy-Tokens
- Guard gegen False-Positives: `_looks_like_secret()` verlangt Zeichentyp-Diversität (Groß/Zahl/Sonderzeichen)
- Pangram-False-Positive-Fix: Reine Kleinbuchstaben-Strings werden nie als Secret eingestuft

**Neue Tests:** `tests/test_security_scanner.py`

---

### ~~[BUG-02]~~ Skeletonizer ist kein JSON/XML-Skeletonizer — README/MCP-Name falsch
**Status:** 🟢 Behoben  
**Dateien:** `skeletonizer.py`, `mcp_server.py`, `README.md`

**Ursache:** `crunch_skeleton()` gab JSON/XML/YAML unverändert zurück. README und MCP-Doku nannten nicht-existentes Tool `skeletonize_json`.

**Fix:**
- Echter JSON-Skeletonizer via `json`-Stdlib: Strings > 64 Zeichen gekürzt, Arrays auf 3 Items begrenzt
- XML-Skeletonizer via `xml.etree.ElementTree`: Struktur/Attribute erhalten, langer Text gekürzt
- YAML-Skeletonizer (stdlib-Fallback wenn kein PyYAML installiert)
- README: `skeletonize_json` → `crunch_code_skeleton` / `crunch_file_skeleton`
- `mcp_server.py`: Docstring aktualisiert (9 → 15 Tools, JSON/XML/YAML erwähnt)

**Neue Tests:** `tests/test_skeletonizer.py`

---

### ~~[BUG-03]~~ Stack-Zähler zeigt utopische Werte (z. B. `2/34`)
**Status:** 🟢 Behoben  
**Datei:** `clipboard_monitor.py`

**Ursache:** Jeder Clipboard-Event von Hintergrund-Apps (IDEs, Browser, Teams) wurde auf den Stack gepusht — inklusive 1–4-Zeichen-Writes.

**Fix:** Neuer Parameter `min_text_length: int = 5` in `ClipboardMonitor.__init__()`. Clipboard-Text wird vor dem Push gegen `len(text.strip()) >= min_text_length` geprüft.

**Neue Tests:** `tests/test_clipboard_monitor.py` (15 Tests)

---

### ~~[BUG-04]~~ OCR-Spracheinstellung fehlt im Settings-UI
**Status:** 🟢 Behoben  
**Dateien:** `settings.py`, `ocr.py`

**Ursache:** `ocr_language` wurde zwar in `config.json` gespeichert, aber in `settings.py` gab es kein UI-Element zum Ändern.

**Fix:**
- Neue Funktion `get_available_languages()` in `ocr.py`: Fragt Windows-OCR-Engine ab, mappt BCP-47-Tags auf Anzeigenamen (50+ Sprachen), sortiert alphabetisch. Fallback-Liste für non-Windows.
- `settings.py`: OptionMenu im General-Bereich — zeigt verfügbare Sprachen, speichert BCP-47-Tag in config.

**Neue Tests:** `tests/test_ocr_languages.py` (11 Tests)

---

### ~~[BUG-05]~~ Hotkey-Kollisionsprüfung fehlt
**Status:** 🟢 Behoben  
**Dateien:** `settings.py`, `config.py`

**Ursache:** `pynput.GlobalHotKeys` registriert denselben Key für zwei Callbacks ohne Warnung — undefiniertes Verhalten.

**Fix:**
- Neue reine Funktion `find_hotkey_collision(hotkeys)` in `config.py` (keine Tkinter-Abhängigkeit → CI-testbar)
- `settings.py._save()`: Kollisionsprüfung vor jedem Speichern; bei Kollision wird roter Fehlertext in der UI angezeigt, Speichern abgebrochen
- Fehlermeldung zeigt Klartext-Aktionsnamen (via `HOTKEY_ACTION_LABELS`)

**Neue Tests:** `tests/test_hotkey_collision.py` (11 Tests)

---

### ~~[BUG-06]~~ OCR schlägt bei sehr kleinen Auswahlen fehl
**Status:** 🟢 Behoben  
**Datei:** `ocr.py`

**Ursache:** Zu geringes Padding (10 px) und zu niedrige Mindesthöhe (64 px) gaben dem Windows-OCR-Engine zu wenig Kontext für Einzelzeichen-Captures.

**Fix:**
- `_MIN_OCR_HEIGHT`: 64 → 96 px
- `border=10` → benannte Konstante `_OCR_PADDING = 24` px
- Hintergrundfarbe des Padding wird vom Bild-Eckpixel abgeleitet (kein hartes Weiß)

**Neue Tests:** `tests/test_ocr_upscale.py` (13 Tests)

---

### ~~[BUG-07]~~ Auto-Crunch: Kein Debouncing
**Status:** 🟢 Behoben  
**Datei:** `clipboard_monitor.py`

**Ursache:** Bei schnellem Kopieren (Ctrl+C mehrfach) wurde für jeden Sequence-Number-Change sofort eine Kompression gestartet — blockierte den Monitor-Thread unnötig.

**Fix:** Neuer Parameter `debounce_delay: float = 0.3` in `ClipboardMonitor.__init__()`. Der `_run()`-Loop verwendet lokale State-Variablen (`_debounce_seq`, `_debounce_time`) für eine Drei-Zustands-Logik: *detect → timer starten → warten → verarbeiten*. `debounce_delay=0` erhält das ursprüngliche Sofort-Verhalten.

**Neue Tests:** `tests/test_clipboard_debounce.py` (10 Tests)

---

### ~~[BUG-08]~~ Autostart funktioniert nur für kompilierte .exe
**Status:** 🟢 Behoben  
**Datei:** `config.py`

**Ursache:** `_get_exe_path()` schrieb im Dev-Modus den Pfad zur `.py`-Datei in den Registry-Run-Key. Windows kann `.py`-Dateien ohne Python im PATH nicht starten.

**Fix:** `_get_exe_path()` → `_get_autostart_command()` mit korrektem Verhalten je Modus:

| Modus | Registry-Wert vorher | Registry-Wert nachher |
|---|---|---|
| Frozen (.exe) | `"C:\...\app.exe"` | `"C:\...\app.exe"` (unverändert) |
| Dev-Modus | `"C:\...\main.py"` ❌ | `"C:\Python311\python.exe" "C:\...\main.py"` ✅ |

**Neue Tests:** `tests/test_autostart_command.py` (10 Tests)

---

## 🟢 Behoben (durch vorherigen Bugfix-Commit, vor dieser Session)

| ID | Problem | Fix |
|---|---|---|
| ~~BUG-F1~~ | Mehrere `tk.Tk()` Instanzen → Absturz | `TkManager` Singleton in `feedback.py` |
| ~~BUG-F2~~ | Hotkey-Recorder Listener läuft ewig | `_cancel_recording()` bei Modifier-only Release |
| ~~BUG-F3~~ | Doppelter Scan per schnellem Hotkey | `_scan_active` Lock in `main.py` |
| ~~BUG-F4~~ | Auto-Crunch Ping-Pong Loop | `_ignore_next_changes += 2` vor Write |
| ~~BUG-F5~~ | Navigate-Beep am Stack-Rand | `navigate()` gibt `None` am Boundary zurück |
| ~~BUG-F6~~ | `saved_percent` vor XML-Wrap berechnet | Berechnung nach `xml_wrap` verschoben |
| ~~BUG-F7~~ | OCR-Sprach-Setting ignoriert | `language`-Parameter in `recognise()` |
| ~~BUG-F8~~ | DPI-Awareness pro Scan gesetzt | Einmalig beim Start in `main.py` |
| ~~BUG-F9~~ | Kein Singleton-Schutz | Windows Named Mutex in `main.py` |
| ~~BUG-F10~~ | Kein Error-Log | Rotating `app.log` in `%APPDATA%` |

---

## ⚠️ Bekannte offene Punkte

### Pre-existing Test-Failure (nicht durch diese Session verursacht)
**Datei:** `tests/test_stack.py::TestTextStackLabel::test_label_shows_mode`  
**Ursache:** Test prüft `"compact" in label` (Kleinschreibung), aber `stack.label()` liefert `[Compact]` (Großschreibung).  
**Empfehlung:** Entweder Test anpassen (`"Compact" in label`) oder `stack.py` normalisieren — 1-Zeilen-Fix.

---

## 💡 Feature Requests

- **[FR-01]** Vollbild-OCR per Hotkey für Nutzer (derzeit nur via MCP headless)
- **[FR-02]** Token Counter → Kosten-Schätzung in Cent (GPT-4o / Claude Preise)
- **[FR-03]** Context-Window-Warnung wenn Paste-Text > X% eines Modells füllt
- **[FR-04]** Maustasten (Seitentasten) als Hotkeys belegbar
- **[FR-05]** Stack-Persistenz optional (Session-Datei beim Beenden schreiben)
