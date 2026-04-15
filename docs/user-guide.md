# 📖 ContextCruncher — Benutzerhandbuch

**Version:** v0.2.0-beta  
**Plattform:** Windows 10 (1903+) / Windows 11

---

## Inhaltsverzeichnis

1. [App starten & Tray-Icon](#1-app-starten--tray-icon)
2. [OCR — Bereich scannen](#2-ocr--bereich-scannen-strg--alt--s)
3. [OCR — Vollbild scannen](#3-ocr--vollbild-scannen-strg--alt--f)
4. [Clipboard-Stack & Navigation](#4-clipboard-stack--navigation)
5. [AI Token-Kompression](#5-ai-token-kompression-strg--alt--c)
6. [Varianten-System](#6-varianten-system)
7. [Auto-Crunch](#7-auto-crunch)
8. [Token Heatmap & Kostenrechner](#8-token-heatmap--kostenrechner-alt--h)
9. [Security Scanner](#9-security-scanner-automatisch)
10. [Einstellungen](#10-einstellungen)
11. [Autostart](#11-autostart)
12. [Hotkeys im Überblick](#12-hotkeys-im-überblick)

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

## 2. OCR — Bereich scannen (`Strg + Alt + S`)

Scannt einen selbst gewählten Bildschirmbereich mit der Windows OCR-Engine.

### So funktioniert es

1. **`Strg + Alt + S` drücken** → Der Bildschirm wird leicht abgedunkelt, der Cursor wird zum Fadenkreuz.
2. **Bereich aufziehen** → Linke Maustaste gedrückt halten und über den Text-Bereich ziehen.
3. **Loslassen** → ContextCruncher erkennt den Text, ein kurzer **Beep** und grüner **Flash** bestätigen den Erfolg.
4. **Toast-Benachrichtigung** erscheint kurz oben rechts mit dem Scan-Ergebnis.
5. Der Text liegt jetzt im **Clipboard** — direkt per `Strg + V` einfügbar.

### Was passiert im Hintergrund

- Text wird automatisch komprimiert → bis zu **5 Varianten** werden vorberechnet (Original, Compact, AI Lv.1–3)
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

## 3. OCR — Vollbild scannen (`Strg + Alt + F`)

Scannt **den gesamten Bildschirminhalt** ohne Bereichsauswahl.

### Wann verwenden

- „Was steht gerade auf meinem Bildschirm?"
- Schnell den Inhalt eines nicht kopierbaren Fensters (z. B. PDF, geschützte App) erfassen
- Screenreader-Ersatz für blockierte Inhalte

### So funktioniert es

1. **`Strg + Alt + F` drücken**
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
| **Älter blättern** | `Strg + Shift + ↓` | Geht einen Eintrag zurück in der Zeit |
| **Neuer blättern** | `Strg + Shift + ↑` | Kehrt zum neueren Eintrag zurück |
| **Stack durchsuchen** | `Strg + Shift + →` | Öffnet Suchmaske (s. unten) |

Nach jeder Navigation:
- Das Clipboard wird sofort mit dem neuen Eintrag befüllt
- Eine Toast-Benachrichtigung zeigt `[Position/Gesamt] Textvorschau`

### Stack-Anzeige im Toast

```
[3/7] def calculate_tax(income...  [AI Lv.2]
  ↑       ↑                           ↑
Position  Vorschau                 Aktive Variante
```

### Suche im Stack (`Strg + Shift + →`)

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

## 5. AI Token-Kompression (`Strg + Alt + C`)

Komprimiert den **aktuellen Clipboard-Inhalt** mit der KI-Kompressionsengine und legt das Ergebnis direkt als neue aktive Variante ins Clipboard.

### Ablauf

1. Text kopieren (oder per OCR-Scan erfassen)
2. **`Strg + Alt + C` drücken**
3. Toast zeigt Ergebnis:
   ```
   ✓ [1/5] Mein Text...  [AI Lv.1]
   💾 1.240 → 890 Tokens (28% gespart)
   ```
4. Komprimierter Text liegt im Clipboard — `Strg + V` zum Einfügen

### Kompressionsgrade

| Level | Name | Token-Ersparnis | Einsatzgebiet |
|---|---|---|---|
| **1** | 🪶 Light | ~10 % | Code, strukturierte Daten — **code-sicher** |
| **2** | 🦖 Token-Cruncher | ~25 % | Dokumentation, E-Mails, Prosa |
| **3** | 💀 Annihilator | ~45 % | Web-Scrapes, Boilerplate-schwere Texte |

**Level einstellen:** Settings → *AI Compact Level* (Standard: Level 1)

### Context-Window-Warnung

Wenn das komprimierte Ergebnis **mehr als 75 % eines Modell-Kontextfensters** belegt, erscheint eine Warnung:

```
⚠ Context Window Warning
Claude 3.5 Sonnet: 78.3% voll
Überprüfe die Token-Heatmap (Alt+H)
```

Schwellwert einstellbar unter Settings → *Context Warn Threshold*.

---

## 6. Varianten-System

Jeder Stack-Eintrag speichert **bis zu 5 Varianten** des gleichen Textes — vorberechnet beim Scan oder beim AI-Compact:

| Variante | Inhalt |
|---|---|
| **Original** | Unverändert wie gescannt/kopiert |
| **Compact** | Zahlen/IBAN/Telefon kompakt (z. B. `1.234.567` → `1.23M`) |
| **AI Lv.1** | 🪶 Light-Kompression |
| **AI Lv.2** | 🦖 Token-Cruncher |
| **AI Lv.3** | 💀 Annihilator |

### Zwischen Varianten wechseln

**Methode 1 — Cycle (Standard):**  
`Strg + Shift + →` wechselt zur nächsten Variante (Original → Compact → AI Lv.1 → ... → zurück zu Original).  
Toast zeigt: `[2/5] Compact  💾 12% gespart`

**Methode 2 — Popup-Picker:**  
Settings → *Variant Mode: Popup* — dann öffnet `Strg + Shift + →` einen visuellen Picker:

```
┌─────────────────────────────────────────┐
│ Wähle eine Variante                     │
│                                         │
│  ◉ Original        (1.240 Tokens)       │
│  ○ Compact         (1.090 Tokens, -12%) │
│  ○ AI Lv.1         (  890 Tokens, -28%) │
│  ○ AI Lv.2         (  740 Tokens, -40%) │
│  ○ AI Lv.3         (  620 Tokens, -50%) │
└─────────────────────────────────────────┘
```

> **Tipp:** Nach einem Scan findest du in der Regel die beste Variante in **AI Lv.1** — er entfernt nur sicheres Rauschen (Leerzeichen, Einrückungen) ohne Bedeutungsverlust.

---

## 7. Auto-Crunch

Auto-Crunch überwacht die Zwischenablage **automatisch** — jedes Mal wenn etwas kopiert wird, komprimiert es ContextCruncher sofort im Hintergrund.

### Aktivieren

**Tray-Menü → 🔄 Auto-Crunch (AUS)** anklicken → wird zu **🔄 Auto-Crunch (AN)**

Toast-Bestätigung: `🔄 Auto-Crunch: ACTIVE`

### Was passiert

1. Du drückst `Strg + C` in einer beliebigen App
2. ContextCruncher erkennt die Änderung (Debounce: 0,3 Sek.)
3. Text wird komprimiert (mit dem konfigurierten Level)
4. Komprimierter Text überschreibt die Zwischenablage
5. Toast: `🔄 Auto-Crunch: N Variants`

### Sicherheitsmechanismen

| Mechanismus | Beschreibung |
|---|---|
| **Debounce 0,3 s** | Schnelle `Strg+C`-Folgen lösen nur **eine** Kompression aus |
| **Min. Textlänge 5 Zeichen** | Einzelne Buchstaben / App-interne Clipboard-Events werden ignoriert |
| **Feedback-Loop-Schutz** | ContextCrunchers eigene Clipboard-Schreibvorgänge lösen keinen weiteren Cycle aus |

> **Hinweis:** Auto-Crunch verändert den Clipboard-Inhalt dauerhaft. Für Code oder formatierte Texte empfiehlt sich Level 1.

---

## 8. Token Heatmap & Kostenrechner (`Alt + H`)

Zeigt eine visuelle Analyse des aktuellen Clipboard-Inhalts: Token-Anzahl, Kosten und Context-Window-Auslastung für alle 6 unterstützten Modelle.

### Öffnen

**`Alt + H`** — öffnet das Heatmap-Fenster (kein Clipboard-Inhalt nötig zum Öffnen, der aktuelle wird geladen).

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

## 10. Einstellungen

**Öffnen:** Tray → ⚙ **Settings**

### Hotkeys konfigurieren

Jede Aktion hat einen eigenen Hotkey, der beliebig geändert werden kann:

1. Auf das Eingabefeld der Aktion klicken
2. Gewünschte Tastenkombination drücken
3. **×** löscht eine Bindung
4. Bei **Kollision** erscheint eine rote Fehlermeldung — Speichern ist blockiert

> **Tipp:** Maus-Seitentasten (**X1 / X2**) können ebenfalls als Hotkeys belegt werden — ideal für einhändigen Betrieb.

### Verfügbare Einstellungen

| Einstellung | Optionen | Beschreibung |
|---|---|---|
| **AI Compact Level** | 1 / 2 / 3 | Kompressionsgrad für `Strg+Alt+C` |
| **Variant Mode** | Cycle / Popup | Wie `Strg+Shift+→` reagiert |
| **Context Warn Threshold** | 0–100 % | Ab wann die Context-Window-Warnung erscheint (Standard: 75 %) |
| **OCR Language** | Dropdown | Erkennungssprache (alle installierten Windows-Sprachen) |
| **Autostart** | An / Aus | Beim Windows-Start automatisch starten |

### OCR-Sprache ändern

Zeigt alle auf dem Windows-System installierten OCR-Sprachpakete.

**Neue Sprache installieren:** Windows-Einstellungen → Zeit & Sprache → Sprache hinzufügen → OCR-Sprachpaket herunterladen.

Danach erscheint sie automatisch im ContextCruncher-Dropdown.

---

## 11. Autostart

ContextCruncher kann mit Windows starten — ohne Aufgabenplaner, ohne Admin-Rechte.

**Aktivieren:** Settings → Autostart ✅  
**Deaktivieren:** Settings → Autostart ☐

Intern wird ein Registry-Eintrag unter  
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`  
gesetzt — nur für den aktuellen Benutzer, kein Admin nötig.

**Dev-Modus:** `"python.exe" "C:\Pfad\zu\main.py"`  
**Installiert (`.exe`):** `"C:\Pfad\zu\ContextCruncher.exe"`

---

## 12. Hotkeys im Überblick

| Aktion | Standard-Hotkey | Anpassbar |
|---|---|---|
| **Region scannen** | `Strg + Alt + S` | ✅ |
| **Vollbild scannen** | `Strg + Alt + F` | ✅ |
| **AI Komprimieren** | `Strg + Alt + C` | ✅ |
| **Älter blättern** | `Strg + Shift + ↓` | ✅ |
| **Neuer blättern** | `Strg + Shift + ↑` | ✅ |
| **Variante / Suche** | `Strg + Shift + →` | ✅ |
| **Token Heatmap** | `Alt + H` | ✅ |
| **Maus X1 / X2** | *(nicht belegt)* | ✅ |

> Alle Hotkeys können in den **Settings** jederzeit geändert oder gelöscht werden. Kollisionen werden live erkannt und verhindert.

---

## 💡 Tipps & Tricks

**OCR für gesperrte/nicht-kopierbaren Text:**  
PDFs, DRM-geschützte E-Books, Fehlermeldungen in nativen Apps → `Strg + Alt + S` → Bereich aufziehen.

**Schnelle Code-Analyse vorbereiten:**  
Code-Datei öffnen → `Strg + Alt + S` über die relevante Funktion → `Strg + Shift + →` bis `AI Lv.1` → `Strg + V` in Chat.

**LLM-Kosten vor dem Senden prüfen:**  
Langen Text ins Clipboard → `Alt + H` → Kosten prüfen → bei Rot: `Strg + Alt + C` → `Alt + H` wieder öffnen → Einsparung sehen.

**Verlauf wiederherstellen:**  
Alten Text brauchen? `Strg + Shift + →` öffnet die Suche, Stichwort tippen → direkt auswählen.

**Wichtiges anpinnen:**  
Tray → Eintrag anklicken → geht ins Pinned-Menü → bleibt auch nach Stack-Leeren erhalten.
