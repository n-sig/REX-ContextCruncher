# 📖 ContextCruncher — Benutzerhandbuch

**Version:** v2.0.1  
**Plattform:** Windows 10 (1903+) / Windows 11

---

## Inhaltsverzeichnis

1. [App starten & Tray-Icon](#1-app-starten--tray-icon)
2. [OCR — Bereich scannen](#2-ocr--bereich-scannen-strgshift2)
3. [OCR — Vollbild scannen](#3-ocr--vollbild-scannen-strgshift1)
4. [Clipboard-Stack & Navigation](#4-clipboard-stack--navigation)
5. [AI Token-Kompression](#5-ai-token-kompression-strgshifta)
6. [Varianten-System](#6-varianten-system)
7. [Auto-Crunch](#7-auto-crunch)
8. [Token Heatmap & Kostenrechner](#8-token-heatmap--kostenrechner-strgshifth)
9. [Security Scanner](#9-security-scanner-automatisch)
10. [AI Compression (v2.0)](#10-ai-compression-v20)
11. [MCP Server](#11-mcp-server)
12. [Content Router](#12-content-router)
13. [Einstellungen](#13-einstellungen)
14. [Autostart](#14-autostart)
15. [Hotkeys im Überblick](#15-hotkeys-im-überblick)

---

## 1. App starten & Tray-Icon

### Starten

```cmd
python src/contextcruncher/main.py
```

Oder per Doppelklick auf `ContextCruncher.exe` (Build).

Nach dem Start erscheint das **ContextCruncher-Icon** in der Windows-Taskleiste (System Tray, rechts unten). Die App läuft im Hintergrund — kein Fenster, keine Unterbrechung.

> **Zweite Instanz:** Wenn ContextCruncher bereits läuft, erscheint eine Hinweismeldung und die zweite Instanz beendet sich sofort.

### Tray-Menü (Rechtsklick auf das Icon)

```
┌─────────────────────────────────┐
│ [1/5] Letzter Text...  [AI Lv.2]│  ← Aktueller Eintrag
│ ─────────────────────────────── │
│ 📋 Recent                        │  ← Verlauf (letzten Einträge)
│   [1] Text vom letzten Scan      │
│   [2] Code von vorhin...         │
│ ─────────────────────────────── │
│ 📌 Pinned                        │  ← Angepinnte Einträge
│ ─────────────────────────────── │
│ 🔄 Auto-Crunch      [AUS]        │  ← Toggle
│ ⚙  Settings                      │
│ 🗑️ Clear Stack                    │
│ ✕  Exit                          │
└─────────────────────────────────┘
```

**Eintrag im Verlauf anklicken:** Kopiert den Text sofort ins Clipboard.

---

## 2. OCR — Bereich scannen (`Strg+Shift+2`)

Scannt einen selbst gewählten Bildschirmbereich mit der Windows OCR-Engine.

### So funktioniert es

1. **`Strg+Shift+2` drücken** → Der Bildschirm wird leicht abgedunkelt, der Cursor wird zum Fadenkreuz.
2. **Bereich aufziehen** → Linke Maustaste gedrückt halten und über den Text-Bereich ziehen.
3. **Loslassen** → ContextCruncher erkennt den Text, ein kurzer **Beep** und grüner **Flash** bestätigen den Erfolg.
4. **Toast-Benachrichtigung** erscheint kurz unten links mit dem Scan-Ergebnis.
5. Der Text liegt jetzt im **Clipboard** — direkt per `Strg+V` einfügbar.

### Was passiert im Hintergrund

- Text wird automatisch komprimiert → Varianten werden vorberechnet (Original, Compact, AI-Kompression)
- Eintrag landet oben auf dem **Stack** (Verlauf)
- **Secrets** (API-Keys, Passwörter) werden automatisch geschwärzt

### Wichtige Details

| Situation | Verhalten |
|---|---|
| Kein Text erkannt | Toast „⚠ No text recognized", kein Beep |
| Sehr kleiner Bereich (< 96 px) | Wird automatisch auf Mindestgröße gepaddet |
| Scan bereits aktiv | Zweiter Hotkey-Druck wird ignoriert (kein doppeltes Overlay) |
| Abbrechen | `Escape` drücken oder außerhalb klicken |

---

## 3. OCR — Vollbild scannen (`Strg+Shift+1`)

Scannt **den gesamten Bildschirminhalt** ohne Bereichsauswahl.

### Wann verwenden

- „Was steht gerade auf meinem Bildschirm?"
- Schnell den Inhalt eines nicht kopierbaren Fensters (z. B. PDF, geschützte App) erfassen
- Screenreader-Ersatz für blockierte Inhalte

### So funktioniert es

1. **`Strg+Shift+1` drücken**
2. Toast „🖥 Full Screen OCR" erscheint kurz
3. Gesamter Text aller sichtbaren Fenster wird erkannt
4. Text im Clipboard, Varianten vorberechnet

> **Tipp:** Gleichzeitig mit Region-Scan aktiv? Der Lock verhindert Überschneidungen — einer läuft immer zuerst fertig.

---

## 4. Clipboard-Stack & Navigation

ContextCruncher merkt sich die **letzten 50 Texte** (OCR-Scans + AI-Kompressionen). Du kannst zwischen ihnen blättern — das Clipboard wird dabei live aktualisiert.

### Navigation

| Aktion | Hotkey | Beschreibung |
|---|---|---|
| **Neuer blättern** | `Strg+Shift+PageUp` | Kehrt zum neueren Eintrag zurück |
| **Älter blättern** | `Strg+Shift+PageDown` | Geht einen Eintrag zurück in der Zeit |
| **Stack durchsuchen** | `Strg+Shift+Space` | Öffnet Suchmaske (s. unten) |

Nach jeder Navigation:
- Das Clipboard wird sofort mit dem neuen Eintrag befüllt
- Eine Toast-Benachrichtigung zeigt `[Position/Gesamt] Textvorschau`

### Stack-Anzeige im Toast

```
[3/7] def calculate_tax(income...  [AI Lv.2]
  ↑       ↑                           ↑
Position  Vorschau                 Aktive Variante
```

### Suche im Stack (`Strg+Shift+Space`)

Öffnet ein **Such-Popup** über dem aktuellen Fenster:

```
┌─────────────────────────────────────────┐
│ 🔎 Suche im Stack...                    │
│ ┌─────────────────────────────────────┐ │
│ │ auth                                │ │  ← Tippen zum Filtern
│ └─────────────────────────────────────┘ │
│                                         │
│ [1] def authenticate_user(token)...     │
│ [4] Bearer eyJhbGci... (API Key)        │
│ ─────────────────────────────────────── │
│ 📌 Pinned                               │
│ [P1] SQL-Query für Users                │
└─────────────────────────────────────────┘
```

- **Tippen** filtert in Echtzeit
- **Enter / Klick** → Eintrag ins Clipboard, Picker schließt sich
- **Escape** → Abbrechen ohne Auswahl

### Einträge anpinnen

Im Tray-Menü kann ein Eintrag angepinnt werden — er bleibt dann dauerhaft im **Pinned-Bereich** erhalten, auch wenn der normale Verlauf sich füllt. Maximal **10 Pins** gleichzeitig. Pins überleben einen App-Neustart.

### Stack leeren

Tray → **🗑️ Clear Stack** — löscht alle nicht-gepinnten Einträge.

---

## 5. AI Token-Kompression (`Strg+Shift+A`)

Komprimiert den **aktuellen Clipboard-Inhalt** mit der KI-Kompressionsengine und legt das Ergebnis direkt als neue aktive Variante ins Clipboard.

### Ablauf

1. Text kopieren (oder per OCR-Scan erfassen)
2. **`Strg+Shift+A` drücken**
3. Toast zeigt Ergebnis:
   ```
   ✓ [1/5] Mein Text...  [AI Lv.1]
   💾 1.240 → 890 Tokens (28% gespart)
   ```
4. Komprimierter Text liegt im Clipboard — `Strg+V` zum Einfügen

### Kompressionspipeline (v2.0)

Seit v2.0 gibt es **keine manuellen Kompressionsgrade** mehr. Die Single-Pass-Pipeline entscheidet automatisch anhand des erkannten Content-Typs (Prosa, Code, Markdown, Logs, JSON, XML, YAML, Agent Config, …) welche Phasen angewandt werden.

| Phase | Was passiert | Übersprungen bei Code? |
|---|---|---|
| 0. Detect & Protect | Content-Typ erkennen, Code-Blöcke extrahieren | — |
| 1. Normalize | Whitespace, Anführungszeichen, Einrückung | Nein (code-sichere Variante) |
| 2. Trim | Füllwörter und Stop-Words entfernen | ✅ Ja |
| 3. Optimize | Synonym-Ersetzung + URL/Pfad-Kürzung | ✅ Ja |
| 4. Structural | Markdown-Tabellen + Listen kompaktieren | ✅ Ja |
| 5. Dedup & Finalize | Sliding-Window-Dedup + finale Bereinigung | Nein |

Typische Ersparnis:
- **Prosa / Markdown:** ~25–30 %
- **Logs / strukturierte Ausgaben:** bis zu ~45 %
- **Quellcode:** ~5–10 % (Einrückung wird bewahrt)

### Context-Window-Warnung

Wenn das komprimierte Ergebnis **mehr als 75 % eines Modell-Kontextfensters** belegt, erscheint eine Warnung:

```
⚠ Context Window Warning
Claude 3.5 Sonnet: 78.3% voll
Überprüfe die Token-Heatmap (Strg+Shift+H)
```

Schwellwert einstellbar unter Settings → *Context Warn Threshold*.

---

## 6. Varianten-System

Jeder Stack-Eintrag speichert **mehrere Varianten** des gleichen Textes — vorberechnet beim Scan oder beim AI-Compact:

| Variante | Inhalt |
|---|---|
| **Original** | Unverändert wie gescannt/kopiert |
| **Compact** | Zahlen/IBAN/Telefon kompakt (z. B. `1.234.567` → `1.23M`) |
| **AI-komprimiert** | Content-type-aware Pipeline-Ergebnis |

### Zwischen Varianten wechseln

**Popup-Picker:** Der Varianten-Picker öffnet ein Win+V-artiges Overlay mit allen Varianten und Token-Anzahl. Auswahl per `↑`/`↓` und `Enter`.

> **Tipp:** Nach einem Scan findest du in der Regel die beste Variante in der AI-komprimierten Version — sie entfernt sicheres Rauschen ohne Bedeutungsverlust. Bei Code wird die Einrückung bewahrt.

---

## 7. Auto-Crunch

Auto-Crunch überwacht die Zwischenablage **automatisch** — jedes Mal wenn etwas kopiert wird, komprimiert es ContextCruncher sofort im Hintergrund.

### Aktivieren

**Tray-Menü → 🔄 Auto-Crunch (AUS)** anklicken → wird zu **🔄 Auto-Crunch (AN)**

Toast-Bestätigung: `🔄 Auto-Crunch: ACTIVE`

### Was passiert

1. Du drückst `Strg+C` in einer beliebigen App
2. ContextCruncher erkennt die Änderung (Debounce: 0,3 Sek.)
3. Text wird komprimiert (Content-type-aware Pipeline)
4. Komprimierter Text überschreibt die Zwischenablage
5. Toast: `🔄 Auto-Crunch: N Variants`

### Sicherheitsmechanismen

| Mechanismus | Beschreibung |
|---|---|
| **Debounce 0,3 s** | Schnelle `Strg+C`-Folgen lösen nur **eine** Kompression aus |
| **Min. Textlänge 5 Zeichen** | Einzelne Buchstaben / App-interne Clipboard-Events werden ignoriert |
| **Feedback-Loop-Schutz** | ContextCrunchers eigene Clipboard-Schreibvorgänge lösen keinen weiteren Cycle aus |
| **Ping-Pong-Deduplizierung** | Identische Texte werden im Stack erkannt und nach vorne sortiert statt dupliziert |

> **Hinweis:** Auto-Crunch verändert den Clipboard-Inhalt dauerhaft. Bei Code wird die code-sichere Pipeline verwendet, die Einrückung und Bezeichner bewahrt.

---

## 8. Token Heatmap & Kostenrechner (`Strg+Shift+H`)

Zeigt eine visuelle Analyse des aktuellen Clipboard-Inhalts: Token-Anzahl, Kosten und Context-Window-Auslastung für alle 6 unterstützten Modelle.

### Öffnen

**`Strg+Shift+H`** — öffnet das Heatmap-Fenster.

### Was die Heatmap zeigt

```
┌──────────────────────────────────────────────────────┐
│  Token Heatmap — 1.240 Tokens (5.830 Zeichen)        │
├──────────────────────────────────────────────────────┤
│  Modell            Tokens   Kosten    Context-Fenster │
│  GPT-4o            1.240    0.003 ¢   ░░░  1.0 %     │
│  GPT-4o mini       1.240    0.000 ¢   ░░░  1.0 %     │
│  o3 mini           1.240    0.001 ¢   ░░   0.6 %     │
│  Claude 3.5 Sonnet 1.240    0.004 ¢   ░░   0.6 %     │
│  Claude 3.5 Haiku  1.240    0.001 ¢   ░░   0.6 %     │
│  Claude 3 Opus     1.240    0.019 ¢   ░░   0.6 %     │
└──────────────────────────────────────────────────────┘
```

### Farbskala der Balken

| Farbe | Auslastung | Bedeutung |
|---|---|---|
| 🟢 Grün | < 50 % | Entspannt, viel Platz |
| 🟡 Gelb | 50–75 % | Mehr als die Hälfte verbraucht |
| 🔴 Rot | > 75 % | Gefahrenzone — Kompression empfohlen |

### Kosten verstehen

Die Kosten zeigen den **Input-Preis** für einen einzigen LLM-Aufruf mit diesem Text:

- `0.003 ¢` = 0,003 US-Cent (GPT-4o, 1.240 Tokens)
- Bei 1.000 Aufrufen täglich: `30 ¢` = ~0,30 USD/Tag

> **Tipp:** Öffne die Heatmap **vor und nach** einer Kompression, um die tatsächliche Token-Ersparnis zu messen.

---

## 9. Security Scanner (automatisch)

Der Security Scanner läuft **automatisch** bei jedem Scan und jeder Kompression — du musst nichts aktivieren.

### Was wird geschwärzt

| Muster | Erkennung | Ersetzt durch |
|---|---|---|
| OpenAI API Keys | `sk-...` | `[AI_API_KEY_REDACTED]` |
| Anthropic Keys | `sk-ant-...` | `[AI_API_KEY_REDACTED]` |
| AWS Secret Keys | `AKIA...` | `[AWS_SECRET_KEY_REDACTED]` |
| Stripe Keys | `sk_live_...` | `[STRIPE_KEY_REDACTED]` |
| Bearer Tokens | `Bearer eyJ...` | `[BEARER_TOKEN_REDACTED]` |
| Hochentropie-Strings | Shannon-Entropie ≥ 4,5 | `[HIGH_ENTROPY_REDACTED]` |

### Schutz vor False Positives

- Reine Kleinbuchstaben-Strings werden **nicht** geflaggt (kein Passwort-Alarm für Wörter)
- Kurze Tokens unter Mindestlänge werden ignoriert
- Bekannte harmlose Patterns (UUIDs in URLs, etc.) sind ausgenommen

### Beispiel

```
Vorher:  "API_KEY=sk-proj-abc123XYZ789ABCDEF..."
Nachher: "API_KEY=[AI_API_KEY_REDACTED]"
```

Der geschwärzte Text wird in **allen Varianten** und im Clipboard gespeichert — die Originaldaten verlassen das System nicht.

---

## 10. AI Compression (v2.0)

### Code-Safe Mode

Quellcode (Python, JavaScript) wird seit v2.0 automatisch erkannt — auch ohne Fenced-Code-Blöcke. Die code-sichere Pipeline bewahrt:

- **Einrückung** (Leerzeichen/Tabs bleiben exakt erhalten)
- **Einbuchstabige Parameter** (`a`, `b`, `x` werden nicht als Stop-Words entfernt)
- **String-Literale** (keine Synonym-Ersetzung innerhalb von Strings)

Destruktive Prosa-Phasen (`Trim`, `Optimize`, `Structural`) werden bei `code_*` Content-Types übersprungen.

### Hybrid AI-Compression (opt-in)

Das `ai_compress` MCP-Tool geht über deterministische Heuristiken hinaus:

1. **4-Layer Protective Extraction** — Code-Blöcke, Tabellen, Datei-/URL-Referenzen und `NEVER`/`ALWAYS`-Constraint-Keywords werden extrahiert
2. **LLM-Rewrite** — Nur der Prosa-Teil wird an den konfigurierten LLM-Provider gesendet (OpenAI, Anthropic, oder Ollama)
3. **Rück-Insertion** — Extrahierte Regionen werden byte-exakt zurückgesetzt

`ai_compress` ist **opt-in und standardmäßig deaktiviert** — kein Netzwerkverkehr ohne expliziten Aufruf.

---

## 11. MCP Server

ContextCruncher stellt einen MCP-Server mit **23 Tools** bereit, die AI-Agents direkt nutzen können.

### Quick Setup

```bash
python setup_mcp.py --all      # Alle erkannten AI-Tools
python setup_mcp.py --claude   # Nur Claude Desktop
python setup_mcp.py --cursor   # Nur Cursor
```

### Verfügbare Tools (Auswahl)

| Tool | Beschreibung |
|---|---|
| `ocr_scan_region` | Interaktive Bildschirm-OCR |
| `screenshot_full` | Vollbild-OCR |
| `crunch_text` | Deterministische Kompression |
| `smart_crunch` | Content-type-aware Kompression |
| `budget_loader` | Datei in exakt N Tokens laden |
| `diff_crunch` | Nur Änderungen seit letztem Laden |
| `context_pack` | Mehrere Dateien in ein Token-Budget packen |
| `ai_compress` | LLM-basierte semantische Kompression (opt-in) |
| `optimize_prompt` | Text in strukturierten LLM-Prompt umschreiben |
| `search_stack` | Clipboard/OCR-Verlauf durchsuchen |
| `count_text_tokens` | Token-Anzahl + Kosten pro Modell |

Vollständige Referenz: [`docs/tools-reference.md`](tools-reference.md) | Setup-Guide: [`docs/mcp-setup.md`](mcp-setup.md)

---

## 12. Content Router

Der Content Router erkennt automatisch den Typ des Eingabetextes und routet ihn durch die optimale Kompressionspipeline:

| Content-Typ | Erkennung | Routing |
|---|---|---|
| **Prosa / Markdown** | Standard-Text | Volle Pipeline |
| **Code (Python/JS)** | Struktursignale (`def`, `class`, `const`, `=>`) | Code-sichere Pipeline |
| **JSON / XML / YAML** | Strukturerkennung | Skeletonizer |
| **Agent Config** | Dateiname (CLAUDE.md, AGENTS.md) oder Keyword-Dichte | Skeleton-Skip-Variante |
| **Logs** | Timestamp-Patterns, Wiederholungen | Aggressive Dedup |

---

## 13. Einstellungen

**Öffnen:** Tray → ⚙ **Settings**

### Hotkeys konfigurieren

Jede Aktion hat einen eigenen Hotkey, der beliebig geändert werden kann:

1. Auf das Eingabefeld der Aktion klicken
2. Gewünschte Tastenkombination drücken
3. **×** löscht eine Bindung
4. Bei **Kollision** erscheint eine rote Fehlermeldung — Speichern ist blockiert

> **Tipp:** Maus-Seitentasten (**X1 / X2**) können ebenfalls als Hotkeys belegt werden — ideal für einhändigen Betrieb. Der Recorder ignoriert die ersten ~250 ms Maus-Input nach dem Öffnen, sodass ein zufälliger Daumendruck während des Klicks nicht als Binding erfasst wird.

### Verfügbare Einstellungen

| Einstellung | Optionen | Beschreibung |
|---|---|---|
| **Context Warn Threshold** | 0–100 % | Ab wann die Context-Window-Warnung erscheint (Standard: 75 %) |
| **OCR Language** | Dropdown | Erkennungssprache (alle installierten Windows-Sprachen) |
| **Autostart** | An / Aus | Beim Windows-Start automatisch starten |
| **AI Compress Provider** | OpenAI / Anthropic / Ollama | Provider für `ai_compress` (opt-in) |
| **AI Compress Model** | Freitext | Modellname für den gewählten Provider |

### OCR-Sprache ändern

Zeigt alle auf dem Windows-System installierten OCR-Sprachpakete.

**Neue Sprache installieren:** Windows-Einstellungen → Zeit & Sprache → Sprache hinzufügen → OCR-Sprachpaket herunterladen.

Danach erscheint sie automatisch im ContextCruncher-Dropdown.

---

## 14. Autostart

ContextCruncher kann mit Windows starten — ohne Aufgabenplaner, ohne Admin-Rechte.

**Aktivieren:** Settings → Autostart ✅  
**Deaktivieren:** Settings → Autostart ☐

Intern wird ein Registry-Eintrag unter  
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`  
gesetzt — nur für den aktuellen Benutzer, kein Admin nötig.

**Dev-Modus:** `"python.exe" "C:\Pfad\zu\main.py"`  
**Installiert (`.exe`):** `"C:\Pfad\zu\ContextCruncher.exe"`

---

## 15. Hotkeys im Überblick

| Aktion | Standard-Hotkey | Anpassbar |
|---|---|---|
| **Vollbild scannen** | `Strg+Shift+1` | ✅ |
| **Region scannen** | `Strg+Shift+2` | ✅ |
| **AI Komprimieren** | `Strg+Shift+A` | ✅ |
| **Neuer blättern ↑** | `Strg+Shift+PageUp` | ✅ |
| **Älter blättern ↓** | `Strg+Shift+PageDown` | ✅ |
| **Stack durchsuchen** | `Strg+Shift+Space` | ✅ |
| **Token Heatmap** | `Strg+Shift+H` | ✅ |
| **Maus X1 / X2** | *(nicht belegt)* | ✅ |

> **Warum `Strg+Shift+…` und nicht `Strg+Alt+…` oder `Alt+…`?** Die alten Defaults scheiterten an drei häufigen Setups: `Alt+Buchstabe` kapert die Office/Explorer-Menüleiste, `Strg+Alt+Buchstabe` ist physisch identisch mit `AltGr` auf deutschen/europäischen Tastaturen (→ `€`, `@`, `{` verlieren das Rennen gegen den globalen Hook), und `Strg+Shift+Pfeil` kollidiert mit Wort-Markierung in jedem Texteditor.

> Alle Hotkeys können in den **Settings** jederzeit geändert oder gelöscht werden. Kollisionen werden live erkannt und verhindert.

---

## 💡 Tipps & Tricks

**OCR für gesperrten/nicht-kopierbaren Text:**  
PDFs, DRM-geschützte E-Books, Fehlermeldungen in nativen Apps → `Strg+Shift+2` → Bereich aufziehen.

**Schnelle Code-Analyse vorbereiten:**  
Code-Datei öffnen → `Strg+Shift+2` über die relevante Funktion → AI-komprimierte Variante wählen → `Strg+V` in Chat.

**LLM-Kosten vor dem Senden prüfen:**  
Langen Text ins Clipboard → `Strg+Shift+H` → Kosten prüfen → bei Rot: `Strg+Shift+A` → `Strg+Shift+H` wieder öffnen → Einsparung sehen.

**Verlauf wiederherstellen:**  
Alten Text brauchen? `Strg+Shift+Space` öffnet die Suche, Stichwort tippen → direkt auswählen.

**Wichtiges anpinnen:**  
Tray → Eintrag anklicken → geht ins Pinned-Menü → bleibt auch nach Stack-Leeren erhalten.
