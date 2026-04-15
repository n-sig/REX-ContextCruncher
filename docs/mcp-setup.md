# 🔌 ContextCruncher MCP — Vollständige Einrichtungsanleitung

**Version:** v0.2.0-beta  
**Voraussetzungen:** Python 3.11+, ContextCruncher-Quellcode

---

> 📖 **Alle Tools mit Beispielen:** [`docs/tools-reference.md`](tools-reference.md)

## Inhaltsverzeichnis

1. [Voraussetzungen & Installation](#1-voraussetzungen--installation)
2. [MCP mit Claude Desktop einrichten](#2-mcp-mit-claude-desktop-einrichten)
3. [MCP mit Ollama (lokal) nutzen](#3-mcp-mit-ollama-lokal-nutzen)
4. [Alle 15 MCP-Tools im Überblick](#4-alle-15-mcp-tools-im-überblick)
5. [Häufige Probleme & Lösungen](#5-häufige-probleme--lösungen)

---

## 1. Voraussetzungen & Installation

### 1.1 Abhängigkeiten installieren

Öffne eine Eingabeaufforderung im ContextCruncher-Ordner und führe aus:

```cmd
pip install mcp>=1.0.0 tiktoken>=0.7.0 httpx>=0.27.0
```

> Die GUI-Abhängigkeiten (`pynput`, `pystray`, `winrt-*`) werden für den reinen MCP-Betrieb **nicht** benötigt.

### 1.2 MCP-Server manuell testen

```cmd
cd C:\Pfad\zu\ContextCruncher
python -m contextcruncher.mcp_server
```

Wenn keine Fehlermeldung erscheint und der Prozess wartet, ist der Server einsatzbereit. Mit `Ctrl+C` beenden.

---

## 2. MCP mit Claude Desktop einrichten

### 2.1 Automatisch via Setup-Skript (empfohlen)

```cmd
cd C:\Pfad\zu\ContextCruncher
python setup_mcp.py --claude
```

Das Skript schreibt den Eintrag automatisch in:
```
%APPDATA%\Claude\claude_desktop_config.json
```

### 2.2 Manuell einrichten

1. Öffne (oder erstelle) die Datei:
   ```
   C:\Users\<Dein-Name>\AppData\Roaming\Claude\claude_desktop_config.json
   ```

2. Füge folgenden Eintrag ein (Pfad anpassen!):

```json
{
  "mcpServers": {
    "contextcruncher": {
      "command": "python",
      "args": ["-m", "contextcruncher.mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\Pfad\\zu\\ContextCruncher\\src"
      }
    }
  }
}
```

**Wichtig:** Doppelte Backslashes `\\` im JSON-Pfad nicht vergessen.

### 2.3 Claude Desktop neu starten

Beende Claude Desktop vollständig (Tray-Icon → Quit) und starte ihn neu. Der MCP-Server wird beim Start automatisch als Subprocess gestartet.

### 2.4 Verbindung prüfen

In einem neuen Chat mit Claude tippe:

```
Welche Tools hast du von ContextCruncher?
```

Claude sollte eine Liste aller 15 Tools anzeigen. Alternativ:

```
Nutze count_text_tokens für diesen Text: "Hello World"
```

---

## 3. MCP mit Ollama (lokal) nutzen

### 3.1 Ollama installieren & Modell laden

1. Ollama herunterladen von: https://ollama.com/download
2. Ein Modell installieren (Empfehlung für Prompt-Optimierung):

```cmd
ollama pull llama3
```

Ollama läuft standardmäßig auf `http://localhost:11434`.

### 3.2 Ollama-Endpoint im MCP konfigurieren

Der `optimize_prompt`-Tool von ContextCruncher unterstützt Ollama als Provider. Konfiguriere den Endpoint einmalig über das MCP-Tool `manage_optimizer_profile`:

**In Claude / AI-Client:**

```
Nutze manage_optimizer_profile mit:
  action: "set_keys"
  ollama_endpoint: "http://localhost:11434"
```

Die Einstellung wird dauerhaft in `%APPDATA%\ContextCruncher\llm_keys.json` gespeichert.

### 3.3 Ollama als Provider verwenden

#### Einfachste Nutzung (Standard-Profil mit Ollama):

```
Nutze optimize_prompt mit:
  text: "Ich möchte eine Python-Funktion die eine CSV-Datei einliest"
  provider_override: "ollama"
  model_override: "llama3"
```

#### Eigenes Profil für Ollama erstellen:

```
Nutze manage_optimizer_profile mit:
  action: "create"
  name: "mein_ollama_profil"
  provider: "ollama"
  model: "llama3"
  system_prompt: "Du bist ein Prompt-Engineer. Schreibe den Text als klaren, strukturierten LLM-Prompt um. Nur den Prompt ausgeben, nichts anderes."
```

Danach:

```
Nutze optimize_prompt mit:
  text: "Analysiere diesen Code auf Sicherheitsprobleme: ..."
  profile_name: "mein_ollama_profil"
```

### 3.4 Unterstützte Ollama-Modelle (Empfehlungen)

| Modell | Größe | Gut für |
|---|---|---|
| `llama3` | 4.7 GB | Allgemeine Prompt-Optimierung |
| `mistral` | 4.1 GB | Schnell, gute Struktur |
| `codellama` | 3.8 GB | Code-Review-Prompts |
| `phi3` | 2.3 GB | Ressourcenschonend |

Alle verfügbaren Modelle: `ollama list`

---

## 4. Alle 15 MCP-Tools im Überblick

### 📋 Clipboard & Stack

| Tool | Beschreibung | Beispiel |
|---|---|---|
| `read_clipboard` | Liest aktuellen Clipboard-Inhalt | `read_clipboard()` |
| `ocr_push_text` | Schreibt Text in Clipboard + Stack | `ocr_push_text("Mein Text")` |
| `search_stack` | Sucht im Clipboard-Verlauf | `search_stack("API key")` |
| `ocr_clear_stack` | Leert den Verlauf | `ocr_clear_stack()` |

### 🤖 AI-Kompression

| Tool | Beschreibung | Beispiel |
|---|---|---|
| `crunch_text` | Komprimiert Text (Level 1–3) | `crunch_text("langer text...", level=2)` |
| `crunch_file` | Komprimiert eine Datei | `crunch_file("C:\\code\\app.py")` |
| `crunch_directory` | Komprimiert ganzen Ordner | `crunch_directory("C:\\projekt\\src")` |
| `crunch_code_skeleton` | Nur Signaturen/Schema | `crunch_code_skeleton(code, "app.py")` |
| `crunch_file_skeleton` | Datei-Skeleton vom Disk | `crunch_file_skeleton("data.json")` |

### 📊 Token & Kosten

| Tool | Beschreibung | Beispiel |
|---|---|---|
| `count_text_tokens` | Zählt Tokens + Kostenrechnung | `count_text_tokens("mein text")` |
| `get_brevity_prompt` | System-Prompt für kürzere AI-Ausgaben | `get_brevity_prompt()` |

### 🧠 AI Context Manager

| Tool | Beschreibung | Beispiel |
|---|---|---|
| `smart_crunch` | Intelligente Kompression nach Inhalt + Intent | `smart_crunch(text, intent="summarize")` |
| `budget_loader` | Datei ans Token-Budget anpassen | `budget_loader("app.log", token_budget=2000)` |
| `diff_crunch` | Nur Änderungen zurückgeben (Delta-Modus) | `diff_crunch(text, previous_version_id="abc123")` |
| `context_pack` | Mehrere Dateien ins Budget packen | `context_pack(["a.py","b.md"], token_budget=5000)` |

### 🎯 AI Prompt Optimizer

| Tool | Beschreibung | Beispiel |
|---|---|---|
| `optimize_prompt` | Text → strukturierter LLM-Prompt | `optimize_prompt(text, profile_name="general")` |
| `list_optimizer_profiles` | Alle Profile anzeigen | `list_optimizer_profiles()` |
| `manage_optimizer_profile` | API-Keys setzen / Profile verwalten | `manage_optimizer_profile(action="set_keys", ...)` |

---

## 5. Häufige Probleme & Lösungen

### ❌ „No module named contextcruncher"

```cmd
set PYTHONPATH=C:\Pfad\zu\ContextCruncher\src
python -m contextcruncher.mcp_server
```

Oder in der `claude_desktop_config.json` den `PYTHONPATH` in `env` prüfen.

### ❌ Claude zeigt keine MCP-Tools

- Claude Desktop vollständig neu starten (nicht nur Fenster schließen)
- `claude_desktop_config.json` auf JSON-Syntaxfehler prüfen (kein trailing comma!)
- Pfad zur `src`-Directory muss absolut und korrekt sein

### ❌ Ollama-Fehler „connection refused"

- Prüfen ob Ollama läuft: `ollama list`
- Ggf. starten: `ollama serve`
- Standard-Port: `11434` — prüfen ob eine Firewall blockiert

### ❌ „httpx not installed"

```cmd
pip install httpx>=0.27.0
```

Wird nur für `optimize_prompt` mit echten API-Calls benötigt. Alle anderen Tools funktionieren ohne `httpx`.

### ❌ „API key not configured"

Für OpenAI/Anthropic muss zuerst der API-Key gesetzt werden:

```
manage_optimizer_profile(
  action="set_keys",
  openai_api_key="sk-..."
)
```

Für Ollama ist kein API-Key nötig — nur `ollama_endpoint` setzen.

---

## Schnellstart-Checkliste

```
☐ pip install mcp tiktoken httpx
☐ python setup_mcp.py --claude
☐ Claude Desktop neu starten
☐ Test: count_text_tokens("Hello World")
☐ (Optional) ollama pull llama3
☐ (Optional) manage_optimizer_profile(action="set_keys", ollama_endpoint="http://localhost:11434")
☐ (Optional) optimize_prompt(text="...", provider_override="ollama", model_override="llama3")
```
