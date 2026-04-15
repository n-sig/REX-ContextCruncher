# 🛠️ ContextCruncher MCP — Tool-Referenz

Vollständige Dokumentation aller **22 Tools** und **2 Resources** des ContextCruncher MCP Servers.

**Kategorien:**
- [📋 Clipboard & Stack](#-clipboard--stack-5-tools) — Daten lesen, schreiben, verwalten
- [✂️ Text-Kompression](#️-text-kompression-6-tools) — Token-Einsparung für AI-Kontexte
- [🧠 AI Context Manager](#-ai-context-manager-4-tools) — Intelligentes Kontext-Engineering
- [⚡ diff_crunch & budget_loader](#-diff_crunch--budget_loader) — Präzises Token-Budgeting
- [🎯 AI Prompt Optimizer](#-ai-prompt-optimizer-3-tools) — Prompts strukturieren via LLM
- [📡 Resources](#-resources-2-passive-ressourcen) — Passive Kontextquellen

---

## 📋 Clipboard & Stack (5 Tools)

### `read_clipboard`

Liest den aktuellen Inhalt der Windows-Zwischenablage.

**Wann benutzen:** Wenn der Nutzer sagt „Ich hab gerade etwas kopiert", „Schau dir meinen Clipboard an", oder bevor eine Kompression gestartet wird.

**Parameter:** keine

**Rückgabe:** `string` — Clipboard-Text oder `"Clipboard is empty."`

**Beispiel:**
```
read_clipboard()
→ "def calculate_tax(income: float) -> float:\n    return income * 0.19"
```

---

### `ocr_push_text`

Schreibt Text in die Zwischenablage **und** legt ihn oben auf den Stack — damit ist er sofort per `Ctrl+V` einfügbar.

**Wann benutzen:** Wenn der AI-Agent einen fertigen Text (Code, Antwort, Zusammenfassung) für den Nutzer bereitstellen will, ohne Copy-Paste.

| Parameter | Typ | Beschreibung |
|---|---|---|
| `text` | `str` | Der Text, der ins Clipboard geschrieben wird |

**Rückgabe:** Bestätigung mit den ersten 80 Zeichen

**Beispiel:**
```python
ocr_push_text("SELECT * FROM users WHERE created_at > '2025-01-01';")
→ "Pushed to stack and clipboard (51 chars): SELECT * FROM users WHERE..."
```

**Typischer Ablauf:**
```
Nutzer: "Schreib mir eine SQL-Abfrage für aktive User und leg sie ins Clipboard"
→ Agent generiert Query → ocr_push_text(query) → Nutzer drückt Ctrl+V
```

---

### `search_stack`

Durchsucht den Clipboard-/OCR-Verlauf nach einem Suchbegriff. Ohne Query: alle Einträge.

**Wann benutzen:** „Hab ich letzte Woche was über Docker kopiert?", „Zeig mir alle Einträge", Recovery von alten Clipboard-Inhalten.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `query` | `str` | `""` | Suchbegriff (case-insensitive). Leer = alle Einträge |

**Rückgabe:** Liste mit `index`, `text` (aktive Variante), `original`, `compact`

**Beispiel:**
```python
search_stack("authentication")
→ [
    {"index": 0, "text": "def authenticate_user(token)...", "original": "...", "compact": "..."},
    {"index": 3, "text": "Bearer token: eyJhbGci...", ...}
  ]

search_stack("")   # Gesamter Stack
→ alle Einträge
```

---

### `ocr_get_current`

Gibt den **aktuell aktiven** Stack-Eintrag zurück — genau das, was bei `Ctrl+V` eingefügt würde.

**Parameter:** keine

**Beispiel:**
```python
ocr_get_current()
→ "Error: Connection refused to localhost:5432"
```

---

### `ocr_clear_stack`

Löscht den gesamten Stack-Verlauf.

**Parameter:** keine

**Beispiel:**
```python
ocr_clear_stack()
→ "Stack cleared (12 entries removed)."
```

---

## ✂️ Text-Kompression (6 Tools)

### `crunch_text`

Komprimiert beliebigen Text für token-effiziente AI-Verarbeitung. Gibt den komprimierten Text plus detaillierte Statistiken zurück.

**Wann benutzen:** Vor dem Senden großer Texte (Web-Scrapes, Logs, Dokumentation) an ein LLM — spart 10–45 % Token.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `text` | `str` | — | Text zum Komprimieren |
| `level` | `int` | `2` | Kompressionsgrad (1–3) |

**Level-Übersicht:**

| Level | Name | Ersparnis | Code-sicher? | Einsatzgebiet |
|---|---|---|---|---|
| `1` | 🪶 Light | ~10 % | ✅ Ja | Code, strukturierte Daten |
| `2` | 🦖 Token-Cruncher | ~25 % | ⚠️ Nur Prosa | Dokumentation, E-Mails, Web-Inhalte |
| `3` | 💀 Annihilator | ~45 % | ❌ Nein | Boilerplate-schwere Web-Scrapes, Logs |

**Rückgabe:**
```json
{
  "compressed_text": "...",
  "original_tokens": 1240,
  "compressed_tokens": 890,
  "tokens_saved": 350,
  "saved_percent": 28.2,
  "techniques_applied": ["whitespace_removal", "stop_word_removal"],
  "content_type": "prose",
  "level_used": 2
}
```

**Beispiel:**
```python
crunch_text("The quick brown fox jumps over the lazy dog. " * 100, level=2)
→ {"compressed_text": "quick brown fox jumps lazy dog. " * 100 (gekürzt),
   "saved_percent": 24.1, ...}
```

> **⚠️ Wichtig:** Level 2 und 3 entfernen Stop-Wörter. Für Code immer Level 1 oder `crunch_code_skeleton` verwenden.

---

### `crunch_file`

Liest eine Datei von der Festplatte und komprimiert sie direkt.

**Wann benutzen:** Wenn man eine bestimmte Datei komprimiert in den Kontext laden will.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `path` | `str` | — | Absoluter oder relativer Pfad zur Datei |
| `level` | `int` | `2` | Kompressionsgrad (1–3) |

**Beispiel:**
```python
crunch_file("C:\\projekt\\README.md", level=2)
→ {
    "file": "README.md",
    "compressed_text": "# MeinProjekt\n...",
    "original_tokens": 3200,
    "compressed_tokens": 2100,
    "saved_percent": 34.4
  }
```

---

### `crunch_directory`

Komprimiert alle Textdateien in einem Verzeichnis (rekursiv). Ignoriert automatisch `.git`, `__pycache__`, `node_modules`, `dist`, `build`.

**Wann benutzen:** Ganzes Projekt-Docs-Verzeichnis, `src/`-Ordner, Konfigurationsdateien.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `path` | `str` | — | Pfad zum Verzeichnis |
| `level` | `int` | `2` | Kompressionsgrad (1–3) |
| `max_files` | `int` | `20` | Max. Anzahl Dateien |

**Beispiel:**
```python
crunch_directory("C:\\projekt\\docs", level=2, max_files=10)
→ {
    "combined_text": "--- README.md ---\n...\n\n--- INSTALL.md ---\n...",
    "files_processed": 7,
    "total_original_tokens": 12400,
    "total_compressed_tokens": 8200,
    "total_saved_percent": 33.9,
    "summary": "7 files: 12,400 → 8,200 tokens (33.9% saved)"
  }
```

---

### `crunch_code_skeleton`

Erzeugt ein **semantisches Skelett** aus Code oder strukturierten Daten (JSON/XML/YAML).

- **Python/JS/TS:** Alle Funktionskörper werden durch `pass` ersetzt — nur Signaturen, Klassen und Kommentare bleiben.
- **JSON/XML/YAML:** Tiefe Verschachtelung bleibt erhalten, lange String-Werte und große Arrays werden gekürzt.

**Wann benutzen:** Wenn man einem AI-Agent die Architektur einer 5000-Zeilen-Codebasis in ~300 Token erklären will. Oder das Schema einer 200KB API-Response in ~50 Token.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `text` | `str` | — | Quelltext |
| `filename` | `str` | `"code.py"` | Dateiname inkl. Extension für Parser-Auswahl |

**Unterstützte Extensions:** `.py`, `.pyw`, `.js`, `.ts`, `.jsx`, `.tsx`, `.json`, `.xml`, `.yaml`, `.yml`

**Beispiel — Python-Code:**
```python
code = """
def calculate_tax(income: float, rate: float = 0.19) -> float:
    '''Berechnet die Steuer.'''
    base = income * rate
    adjustment = 0
    if income > 100000:
        adjustment = base * 0.05
    return base + adjustment

class TaxCalculator:
    def __init__(self, country: str):
        self.country = country
    def compute(self, income: float) -> float:
        return calculate_tax(income)
"""

crunch_code_skeleton(code, "tax.py")
→ {
    "skeleton_text": "def calculate_tax(income: float, rate: float = 0.19) -> float:\n    pass\n\nclass TaxCalculator:\n    def __init__(self, country: str):\n        pass\n    def compute(self, income: float) -> float:\n        pass",
    "original_tokens": 85,
    "compressed_tokens": 34,
    "saved_percent": 60.0
  }
```

**Beispiel — JSON-Schema:**
```python
crunch_code_skeleton('{"users": [{"id": 1, "name": "Alice", "email": "alice@..."}, ...500 weitere]}', "api.json")
→ Schema mit gekürzten Werten und Arrays auf 3 Einträge begrenzt
```

---

### `crunch_file_skeleton`

Wie `crunch_code_skeleton`, liest aber direkt von der Festplatte.

| Parameter | Typ | Beschreibung |
|---|---|---|
| `path` | `str` | Absoluter Pfad zur Quelldatei |

**Beispiel:**
```python
crunch_file_skeleton("C:\\projekt\\src\\api\\routes.py")
→ Nur Funktionssignaturen aller Route-Handler (~80 % Token gespart)
```

---

### `count_text_tokens`

Zählt exakt die LLM-Tokens eines Texts mit `tiktoken` und berechnet Kosten für alle 6 Modelle.

**Wann benutzen:** Vor dem Senden großer Texte — Budget prüfen. Nach Kompression — Einsparung messen.

| Parameter | Typ | Beschreibung |
|---|---|---|
| `text` | `str` | Zu analysierender Text |

**Rückgabe:**
```json
{
  "token_count": 1240,
  "char_count": 5830,
  "chars_per_token": 4.7,
  "cost_estimates_usc": {
    "GPT-4o": 0.0031,
    "GPT-4o mini": 0.000186,
    "Claude 3.5 Sonnet": 0.00372,
    ...
  },
  "summary": "1,240 tokens (5,830 chars) | GPT-4o: 0.0031 ¢  |  Claude 3.5 Sonnet: 0.00372 ¢ (~est)"
}
```

**Beispiel — Workflow:**
```python
# 1. Original messen
before = count_text_tokens(my_big_text)
# → 8.400 Tokens | GPT-4o: 0.021 ¢

# 2. Komprimieren
result = crunch_text(my_big_text, level=2)

# 3. Ergebnis messen
after = count_text_tokens(result["compressed_text"])
# → 5.900 Tokens | GPT-4o: 0.0148 ¢  → 30% gespart
```

---

### `get_brevity_prompt`

Gibt einen System-Prompt-Snippet zurück, der das AI-Modell anweist, deutlich kürzer zu antworten (~50–70 % Output-Einsparung).

**Parameter:** keine

**Wann benutzen:** Als Prefix für alle Prompts in Token-knappen Kontexten, oder wenn man nur schnelle Antworten ohne Ausschweifungen will.

**Beispiel:**
```python
brevity = get_brevity_prompt()

# In deinem System-Prompt:
system_prompt = brevity + "\n\n" + dein_normaler_system_prompt
```

**Output (gekürzt):**
```
BREVITY MODE ACTIVE. Follow these rules strictly:
- Use minimal words. No filler, no fluff, no pleasantries.
- Code: write only the changed parts, not full files.
- Target: reduce your response length by 70% vs your normal style.
```

---

## 🧠 AI Context Manager (4 Tools)

Diese Tools bilden den Kern des intelligenten Kontext-Engineerings. Im Gegensatz zur manuellen Kompression erkennen sie den Inhaltstyp automatisch und wählen die optimale Strategie.

### `smart_crunch`

Komprimiert Text **automatisch** — erkennt den Inhaltstyp (Python-Code, JSON, Log, Prosa, Markdown, E-Mail...) und wählt die passende Pipeline.

**Wann benutzen:** Immer wenn man nicht weiß, welcher Level oder welche Strategie optimal ist. Standard-Tool für gemischte Inhalte.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `text` | `str` | — | Zu komprimierender Text |
| `intent` | `str` | `"understand"` | Verwendungszweck (s. unten) |
| `filename` | `str` | `""` | Optionaler Dateiname für bessere Erkennung |

**Intent-Optionen:**

| Intent | Ziel | Typischer Einsatz |
|---|---|---|
| `understand` | Bedeutung erhalten, Rauschen entfernen | Allgemein, Standard |
| `code_review` | Code-Struktur maximieren | Code-Analyse, Debugging |
| `extract_data` | Zahlen/Namen/Daten fokussieren | Datenauswertung |
| `summarize` | Maximale Reduktion | Nur Key-Facts nötig |

**Rückgabe:**
```json
{
  "compressed_text": "...",
  "strategy_used": "secret_redaction → skeleton:code_python",
  "content_type": "code_python",
  "confidence": 0.93,
  "what_was_removed": ["Skeleton stripped 420 tokens (82% of structure)"],
  "original_tokens": 520,
  "compressed_tokens": 94,
  "saved_percent": 81.9
}
```

**Beispiele:**

```python
# Python-Code → erkennt code_python → Skeleton-Strategie
smart_crunch(python_source, intent="understand", filename="main.py")
→ strategy: "skeleton:code_python", saved: ~80%

# Log-File → erkennt log → Level-3-Kompression
smart_crunch(log_content, intent="summarize", filename="app.log")
→ strategy: "level_3", saved: ~45%

# JSON-API-Antwort → erkennt data_json → Schema-Skeleton
smart_crunch(api_json, intent="understand")
→ strategy: "skeleton:data_json", saved: ~70%

# Prosa-Artikel → erkennt prose → Level-2
smart_crunch(article, intent="summarize")
→ strategy: "level_3", saved: ~45%
```

> **Tipp:** Der `confidence`-Wert zeigt, wie sicher die Strategie-Wahl ist. Unter 0.80 empfiehlt sich ein Blick in `explain_compression`.

---

### `explain_compression`

**Previews** alle vier Intent-Strategien — ohne den Text zu verändern. Zeigt Ersparnisse, Confidence und was entfernt würde.

**Wann benutzen:** Vor einer wichtigen Kompression, wenn man entscheiden will wie aggressiv vorzugehen ist.

| Parameter | Typ | Beschreibung |
|---|---|---|
| `text` | `str` | Zu analysierender Text |
| `filename` | `str` | Optionaler Dateiname-Hinweis |

**Rückgabe:**
```json
{
  "content_type": "code_python",
  "original_tokens": 1840,
  "recommended_intent": "code_review",
  "recommendation_reason": "Best savings (78.2%) with confidence >= 85%",
  "per_intent_analysis": {
    "understand":    {"strategy": "skeleton:code_python", "token_savings_percent": 75.1, "confidence": 0.93},
    "code_review":   {"strategy": "level_1",              "token_savings_percent": 78.2, "confidence": 0.99},
    "extract_data":  {"strategy": "skeleton:code_python", "token_savings_percent": 75.1, "confidence": 0.90},
    "summarize":     {"strategy": "skeleton:code_python", "token_savings_percent": 75.1, "confidence": 0.88}
  }
}
```

**Beispiel-Workflow:**
```python
# Analyse: Was würde passieren?
preview = explain_compression(big_code_file, "server.py")
# → recommended: "code_review" mit 78% Einsparung

# Dann gezielt anwenden:
result = smart_crunch(big_code_file, intent="code_review", filename="server.py")
```

---

### `budget_loader`

Lädt eine Datei in **exakt N Token** — nie mehr. Intelligent: versteht Struktur und weiß, was bei Kürzungen wichtig ist.

**Analogie:** Wie `head -n 100` für Zeilen — aber für Tokens, und inhaltsbewusst.

**Wann benutzen:** Wenn ein AI-Agent ein festes Token-Budget hat und eine Datei so vollständig wie möglich laden will.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `path` | `str` | — | Pfad zur Datei |
| `token_budget` | `int` | `4000` | Maximale Token-Anzahl |
| `priority` | `str` | `"auto"` | Was bei Kürzung priorisiert wird |

**Priority-Optionen:**

| Priority | Verhalten | Auto-erkannt für |
|---|---|---|
| `auto` | Erkennt Typ und wählt optimal | — |
| `signatures` | Nur Funktions-/Klassen-Signaturen | Python, JS, TS |
| `schema` | Nur Keys/Typen, keine Werte | JSON, YAML |
| `recent` | Neueste Zeilen zuerst | Log-Dateien |
| `structure` | Headings + erste Sätze | Markdown, Docs |

**Rückgabe:**
```json
{
  "file": "server.py",
  "text": "def route_handler(...): pass\n...",
  "is_complete": false,
  "priority_used": "signatures",
  "original_tokens": 8400,
  "result_tokens": 4000,
  "token_budget": 4000,
  "tokens_saved": 4400,
  "summary": "server.py: 8,400 tokens → 4,000 tokens (signatures)"
}
```

**Beispiele:**
```python
# Python-Datei mit 8K Tokens in 2K Token-Budget
budget_loader("C:\\src\\api.py", token_budget=2000)
→ Nur Signaturen, is_complete: false

# Log-Datei — neueste Zeilen priorisieren
budget_loader("C:\\logs\\app.log", token_budget=1000, priority="recent")
→ Letzte ~1000 Token des Logs

# Markdown-Doku — nur Struktur
budget_loader("C:\\docs\\README.md", token_budget=500, priority="structure")
→ Alle Headings + erste Sätze jeder Sektion

# Kleine Datei — komplett laden
budget_loader("C:\\config\\.env.example", token_budget=4000)
→ is_complete: true, gesamte Datei
```

---

### `context_pack`

Packt **mehrere Dateien** in einen gemeinsamen Token-Block. Verteilt das Budget intelligent nach Relevanz zur Frage.

**Wann benutzen:** Code-Review über mehrere Dateien, Multi-File-Debugging, RAG-Pipelines, komplexe Fragen die mehrere Quellen brauchen.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `paths` | `list[str]` | — | Liste absoluter Dateipfade |
| `token_budget` | `int` | `10000` | Gesamt-Token für alle Dateien |
| `question` | `str` | `""` | Frage → relevanteste Dateien kriegen mehr Budget |

**Rückgabe:**
```json
{
  "packed_context": "--- main.py ---\n...\n\n--- config.py ---\n...",
  "files_included": 3,
  "files_skipped": 0,
  "tokens_used": 4820,
  "saved_percent": 42.1,
  "per_file": [
    {"file": "main.py", "original_tokens": 3200, "actual_tokens": 2100, "relevance_score": 0.85},
    {"file": "config.py", "original_tokens": 800, "actual_tokens": 800, "is_complete": true},
    ...
  ]
}
```

**Beispiele:**
```python
# Drei Dateien, gleichmäßig verteilt (keine Frage)
context_pack(
    ["C:\\src\\main.py", "C:\\src\\config.py", "C:\\tests\\test_main.py"],
    token_budget=6000
)

# Mit Frage → relevanteste Dateien bekommen mehr Budget
context_pack(
    ["C:\\src\\auth.py", "C:\\src\\models.py", "C:\\src\\routes.py", "C:\\README.md"],
    token_budget=8000,
    question="authentication token validation error"
)
→ auth.py bekommt den größten Budget-Anteil
```

---

## ⚡ diff_crunch & budget_loader

### `diff_crunch`

Gibt beim **zweiten Aufruf derselben Datei nur noch die Änderungen** zurück — spart in langen Sessions 90 %+ Token.

**Wann benutzen:** Wenn man eine Datei im Laufe einer Session mehrfach liest (z. B. nach jedem Code-Edit). Statt jedes Mal 2000 Token zu schicken, nur noch die 50-Token-Änderungen.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `text` | `str` | — | Aktueller Text-Inhalt |
| `previous_version_id` | `str` | `""` | `version_id` aus dem letzten Aufruf |

**Ablauf:**

```
1. Erster Aufruf (kein previous_version_id):
   → mode: "full", text: "...", version_id: "a1b2c3d4e5f6g7h8"

2. Datei bearbeiten...

3. Zweiter Aufruf (mit previous_version_id):
   → mode: "delta", changes_only: "@@ -12,7 +12,9 @@\n-old line\n+new line\n..."
      delta_tokens: 45, full_tokens: 1840, tokens_saved: 1795, saved_percent: 97.6

4. Keine Änderung:
   → mode: "unchanged", tokens_saved: 1840, saved_percent: 100.0
```

**Vollständiges Beispiel:**
```python
# Erste Anfrage — lädt vollständig
r1 = diff_crunch(open("server.py").read())
vid = r1["version_id"]    # merken!

# ... User editiert server.py ...

# Zweite Anfrage — nur Delta
r2 = diff_crunch(open("server.py").read(), previous_version_id=vid)
# r2["mode"] == "delta"  →  nur die geänderten Zeilen

# version_id für nächste Runde aktualisieren
vid = r2["version_id"]
```

> **Hinweis:** Wenn das Delta größer als der Volltext wäre (z. B. sehr kurze Texte), wird automatisch `mode: "full"` zurückgegeben.

---

## 🎯 AI Prompt Optimizer (3 Tools)

### `optimize_prompt`

Schreibt einen rohen Text mithilfe eines LLM in einen **strukturierten, effektiven Prompt** um. Unterstützt OpenAI, Anthropic und Ollama (lokal).

**Voraussetzung:** API-Key konfigurieren via `manage_optimizer_profile(action="set_keys", ...)` oder Ollama lokal laufen lassen.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `text` | `str` | — | Roher Text der optimiert werden soll |
| `profile` | `str` | `"general"` | Profil-Name (s. `list_optimizer_profiles`) |
| `provider` | `str` | `""` | Überschreibt Profil-Provider (openai/anthropic/ollama) |
| `model` | `str` | `""` | Überschreibt Modell-Name |

**Built-in Profile:**

| Profil | Stärke |
|---|---|
| `general` | Allgemeine Prompt-Strukturierung |
| `code_reviewer` | Code-Review-Prompts mit Kontext + Review-Fragen |
| `data_analyst` | Datenanalyse-Prompts mit Struktur + Output-Format |
| `summarizer` | Zusammenfassungs-Prompts mit Länge + Zielgruppe |
| `translator` | Übersetzungs-Prompts mit Sprachpaar + Ton |

**Beispiele:**

```python
# Einfacher Text → strukturierter Prompt (mit OpenAI)
optimize_prompt(
    "Ich will wissen ob mein Python-Code gut ist",
    profile="code_reviewer"
)
→ {
    "optimized_prompt": "You are a senior Python engineer. Review the following code for:\n1. Security vulnerabilities\n2. Performance bottlenecks\n3. PEP 8 compliance\n4. Edge cases\n\nProvide specific line-number references...",
    "input_tokens": 12,
    "output_tokens": 89,
    "latency_ms": 820
  }

# Mit Ollama (keine Kosten, lokal)
optimize_prompt(
    "Analysiere die Verkaufszahlen der letzten 3 Monate",
    profile="data_analyst",
    provider="ollama",
    model="llama3"
)

# Mit Anthropic
optimize_prompt(
    "Übersetze diesen Text ins Englische",
    profile="translator",
    provider="anthropic",
    model="claude-3-haiku-20240307"
)
```

---

### `list_optimizer_profiles`

Zeigt alle verfügbaren Profile (built-in + eigene) und den Konfigurations-Status der Provider.

**Parameter:** keine

**Beispiel:**
```python
list_optimizer_profiles()
→ {
    "profiles": [
      {"name": "general",       "provider": "openai", "model": "gpt-4o-mini", "is_builtin": true},
      {"name": "code_reviewer", "provider": "openai", "model": "gpt-4o-mini", "is_builtin": true},
      {"name": "mein_profil",   "provider": "ollama", "model": "llama3",      "is_builtin": false}
    ],
    "provider_config": {
      "openai_configured": true,
      "anthropic_configured": false,
      "ollama_endpoint": "http://localhost:11434"
    }
  }
```

---

### `manage_optimizer_profile`

Konfiguriert API-Keys, erstellt oder löscht Custom-Profile.

**Actions:**

| Action | Beschreibung |
|---|---|
| `set_keys` | API-Keys und Ollama-Endpoint speichern |
| `create` | Neues Custom-Profil erstellen |
| `delete` | Custom-Profil löschen (Built-ins sind geschützt) |

**Beispiele:**

```python
# API-Keys konfigurieren (einmalig)
manage_optimizer_profile(
    action="set_keys",
    openai_api_key="sk-...",
    anthropic_api_key="sk-ant-...",
    ollama_endpoint="http://localhost:11434"
)

# Custom-Profil für deutsche Prompts
manage_optimizer_profile(
    action="create",
    name="deutsch_reviewer",
    provider="ollama",
    model="llama3",
    system_prompt="Du bist ein erfahrener Softwareentwickler. Schreibe den Text als präzisen Code-Review-Prompt auf Deutsch um. Struktur: 1) Kontext, 2) Zu prüfende Aspekte, 3) Erwartetes Ergebnis. Nur den Prompt ausgeben.",
    temperature=0.2
)

# Profil wieder löschen
manage_optimizer_profile(action="delete", name="deutsch_reviewer")
```

---

## 📡 Resources (2 Passive Ressourcen)

Resources sind passive Kontextquellen — der AI-Agent kann sie jederzeit lesen, ohne einen Funktionsaufruf zu machen.

### `clipboard://current`

Gibt immer den aktuellen Clipboard-Inhalt zurück. Equivalent zu `read_clipboard()`, aber als passiver Kontext.

**URI:** `clipboard://current`

**Einsatz:** In System-Prompts oder als Kontext-Referenz, wenn der Agent ständig über den aktuellen Clipboard-Inhalt Bescheid wissen soll.

---

### `clipboard://history`

Gibt den gesamten Clipboard-Verlauf als formatierten Text zurück (max. 10 Einträge, neueste zuerst).

**URI:** `clipboard://history`

**Format:**
```
[1] def authenticate_user(token: str) -> bool:...
[2] SELECT * FROM users WHERE active = 1
[3] Error: Connection refused to localhost:5432
```

---

## 🔗 Tool-Kombinationen (Empfohlene Workflows)

### Workflow 1 — Großes Projekt analysieren

```python
# Alle wichtigen Dateien in 8K Token packen
packed = context_pack(
    ["main.py", "config.py", "models.py", "utils.py"],
    token_budget=8000,
    question="database connection error"
)
# → packed["packed_context"] direkt als Kontext verwenden
```

### Workflow 2 — Datei wiederholt lesen (Coding Session)

```python
# Erstmalig laden
r1 = diff_crunch(open("server.py").read())
vid = r1["version_id"]

# Nach jedem Edit nur noch Delta
r2 = diff_crunch(open("server.py").read(), previous_version_id=vid)
vid = r2["version_id"]  # für nächste Runde
```

### Workflow 3 — Log-Analyse mit Budget

```python
# Nur die neuesten 2000 Token eines Logs
result = budget_loader("C:\\logs\\app.log", token_budget=2000, priority="recent")
# → result["text"] enthält die neuesten Log-Zeilen
```

### Workflow 4 — Kompression strategisch wählen

```python
# Erst analysieren
preview = explain_compression(my_text, "api.py")
# → recommended_intent: "code_review"

# Dann mit optimalem Intent anwenden
compressed = smart_crunch(my_text, intent="code_review", filename="api.py")
```

### Workflow 5 — Token-Budget vor API-Call prüfen

```python
# Vor dem Senden prüfen
stats = count_text_tokens(my_context)
if stats["token_count"] > 4000:
    compressed = crunch_text(my_context, level=2)
    my_context = compressed["compressed_text"]
```
