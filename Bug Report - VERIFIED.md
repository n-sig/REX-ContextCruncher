# 🐞 Verified QA Report — ContextCruncher v0.1.0-alpha / v0.2.0-beta

**Erstellt:** 2026-04-12  
**Methode:** Statische Code-Analyse aller Module in `src/contextcruncher/`  
**Status-Legende:** ✅ Bestätigt · ⚠️ Teilweise · 🟢 Behoben · ❌ Nicht reproduzierbar

---

## 🚨 P1 — Kritisch

### [BUG-01] Security Scanner: High-Entropy Secrets werden nicht erkannt
**Status:** ✅ Bestätigt  
**Datei:** `security_scanner.py`

Der Scanner kennt exakt 6 hardcodierte Regex-Patterns. Alles andere läuft ungeprüft durch.

**Konkret fehlende Patterns (Code-Beweis):**

| Secret-Typ | Beispiel | Pattern vorhanden? |
|---|---|---|
| AWS Access Key ID | `AKIA...` | ✅ Ja |
| **AWS Secret Access Key** | `wJalrXUtn...` | ❌ Nein |
| **Stripe Live Key** | `sk_live_...` | ❌ Nein |
| **Stripe Test Key** | `sk_test_...` | ❌ Nein |
| **PayPal / Braintree** | `access_token$...` | ❌ Nein |
| **OpenAI API Key** | `sk-proj-...` | ❌ Nein |
| **GCP Service Account JSON** | `"private_key": "-----BEGIN..."` in String | ❌ Kein rekursives Scanning |
| GitHub Token (ghp_) | `ghp_...` | ✅ Ja |
| JWT | `eyJ...` | ✅ Ja |
| UUID | Standard-Format | ✅ Ja |
| Private Key Block | `-----BEGIN...` | ✅ Ja |
| IPv4-Adresse | `192.168.x.x` | ✅ Ja (aber: zu aggressiv — trifft auch Versionsnummern wie `1.0.0.1`) |

**Kein Entropie-Check:** Secrets ohne bekannte Präfixe (z. B. zufällige 40-char-Strings) werden nie erkannt.  
**Kein rekursives JSON-Parsing:** `{"key": "{\"private_key\": \"...\"}" }` — eingebettetes JSON wird nicht aufgelöst.

**Auswirkung:** Falsches Sicherheitsgefühl. Stripe-, PayPal- und GCP-Credentials gehen unzensiert an LLMs.

**Fix:**
```python
# Fehlende Patterns ergänzen:
"[STRIPE_KEY_REDACTED]":  re.compile(r'\bsk_(?:live|test)_[a-zA-Z0-9]{24,}\b'),
"[OPENAI_KEY_REDACTED]":  re.compile(r'\bsk-(?:proj-)?[a-zA-Z0-9\-_]{32,}\b'),
"[GENERIC_SECRET_REDACTED]": Shannon-Entropie > 4.5 bei Strings > 20 Zeichen
```

---

### [BUG-02] Skeletonizer ist kein JSON/XML-Skeletonizer — README/MCP-Name falsch
**Status:** ✅ Bestätigt + Zusatzfund  
**Dateien:** `skeletonizer.py`, `mcp_server.py`, `README.md`

`skeletonizer.py` ist ausschließlich ein **Code-Skeletonizer** (Python via AST, JS/TS via Regex). JSON/XML wird gar nicht verarbeitet.

```python
# skeletonizer.py — crunch_skeleton():
def crunch_skeleton(text: str, filename: str = "code.py") -> str:
    ext = filename.split('.')[-1].lower()
    if ext in ('py', 'pyw'):
        return crunch_python(text)       # ✅ funktioniert
    elif ext in ('js', 'ts', 'jsx', 'tsx'):
        return _crude_js_ts_skeleton(text)  # ⚠️ Regex, rudimentär
    return text  # ← JSON, XML, YAML → unveränderter Originaltext zurück!
```

**Zusatzfund — MCP-Tool-Name stimmt nicht:**  
- README und MCP-Dokumentation listen `skeletonize_json` als Tool  
- Im `mcp_server.py` heißt das Tool **`crunch_code_skeleton`** — `skeletonize_json` existiert nicht  
- Nutzer, die `skeletonize_json` aufrufen, erhalten einen MCP-Fehler

**Auswirkung:** Feature wie beschrieben nicht vorhanden. JSON-Payloads werden nicht reduziert.

**Fix:** Echten JSON-Skeletonizer implementieren:
```python
import json
def skeletonize_json(text: str, max_str_len: int = 64, max_array_items: int = 1) -> str:
    data = json.loads(text)
    return json.dumps(_reduce(data, max_str_len, max_array_items), indent=2)
```

---

### [BUG-03] Stack-Zähler zeigt utopische Werte (z. B. `2/34`)
**Status:** ✅ Bestätigt  
**Datei:** `clipboard_monitor.py`, `main.py`

Der `ClipboardMonitor` pusht **jeden** Clipboard-Event auf den Stack — auch von Hintergrund-Apps (Browser, IDEs, Teams, etc.), die still in die Zwischenablage schreiben, ohne dass der User etwas kopiert hat. Diese Einträge sind im Tray-Menü nicht sichtbar (weil sie leer oder Systemnachrichten sind), zählen aber trotzdem in `len(stack._items)` mit.

**Ergebnis:** User kopiert 2 Dinge, Anzeige zeigt `2/34`.

**Fix:** Whitelist für sinnvolle Stack-Einträge — z. B. nur pushen wenn `len(text.strip()) > 5`, oder einen "silent push"-Modus ohne Tray-Eintrag einführen.

---

## 🟠 P2 — Hoch

### [BUG-04] OCR-Spracheinstellung fehlt im Settings-UI
**Status:** ✅ Bestätigt  
**Dateien:** `settings.py`, `config.py`, `ocr.py`

- `config.py` speichert `"ocr_language": "auto"` ✅  
- `ocr.py` liest den Wert seit unserem Fix korrekt aus ✅  
- `settings.py` hat **kein UI-Element** für diese Einstellung — der User kann sie nicht ändern ❌  

**Fix:** Dropdown in `open_settings()` ergänzen (analog zum bestehenden AI-Compression-Dropdown), das verfügbare Windows-OCR-Sprachen auflistet und den Wert in `config.json` speichert.

---

### [BUG-05] Hotkey-Kollisionsprüfung fehlt
**Status:** ✅ Bestätigt  
**Datei:** `settings.py`

Beim Speichern in `_save()` wird nicht geprüft, ob zwei Aktionen denselben Hotkey haben. `pynput.GlobalHotKeys` registriert dann denselben Key für zwei Callbacks — das Verhalten ist undefiniert (meistens gewinnt der letzte Eintrag lautlos).

**Fix:**
```python
def _save():
    new_hotkeys = {action: field.combo for action, field in fields.items()}
    # Kollisionsprüfung
    used = {}
    for action, combo in new_hotkeys.items():
        if combo and combo in used:
            show_error(f"Konflikt: '{combo}' ist für '{used[combo]}' und '{action}' belegt.")
            return
        if combo:
            used[combo] = action
```

---

### [BUG-06] OCR schlägt bei sehr kleinen Auswahlen fehl
**Status:** ⚠️ Teilweise — Schutz vorhanden, aber unzureichend  
**Datei:** `ocr.py`

`_upscale_for_ocr()` fügt 10px Padding und skaliert auf min. 64px Höhe hoch. Das reicht für Einzelzeichen-Captures (z. B. ein einzelnes Icon-Label) jedoch oft nicht aus, da der Windows-OCR-Engine ein Mindestkontext um das Zeichen herum benötigt.

**Fix:** Padding von 10px auf 20–30px erhöhen, und `_MIN_OCR_HEIGHT` von 64 auf 96px.

---

## 🟡 P3 — Mittel

### [BUG-07] Auto-Crunch: Kein Debouncing
**Status:** ✅ Bestätigt  
**Datei:** `clipboard_monitor.py`

Bei schnellem Kopieren (z. B. Ctrl+C, Ctrl+C, Ctrl+C in schneller Folge) startet `_handle_clipboard_change` für jeden Event sofort. Die Kompression für Level 3/4 blockiert den Monitor-Thread für jede einzelne Änderung.

**Fix:** 300ms Debounce-Logik im `_run()`-Loop:
```python
# Nur auslösen wenn 300ms keine neue Änderung kam
if current_seq != self.last_seq:
    self._pending_seq = current_seq
    self._pending_time = time.time()
elif self._pending_seq and time.time() - self._pending_time > 0.3:
    # Jetzt verarbeiten
```

---

### [BUG-08] Autostart funktioniert nur für kompilierte .exe
**Status:** ✅ Bestätigt  
**Datei:** `config.py`

```python
def _get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable      # .exe — korrekt
    return os.path.abspath(sys.argv[0])  # .py-Datei — startet nicht ohne Python im PATH
```

Im Dev-Modus schreibt der Registry-Eintrag den Pfad zur `.py`-Datei. Windows weiß nicht, wie es eine `.py` ausführt, wenn Python nicht im `PATH` ist.

**Fix:** Im Dev-Modus Autostart deaktivieren oder `python.exe path/to/main.py` als Registry-Value schreiben.

---

## 🟢 Behoben (durch vorherigen Bugfix-Commit)

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

## 💡 Feature Requests

- **[FR-01]** Vollbild-OCR per Hotkey für Nutzer (derzeit nur via MCP headless)
- **[FR-02]** Token Counter → Kosten-Schätzung in Cent (GPT-4o / Claude Preise)
- **[FR-03]** Context-Window-Warnung wenn Paste-Text > X% eines Modells füllt
- **[FR-04]** Maustasten (Seitentasten) als Hotkeys belegbar
- **[FR-05]** Stack-Persistenz optional (Session-Datei beim Beenden schreiben)
