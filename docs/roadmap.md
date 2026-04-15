# 🔮 VISION.md — ContextCruncher Evolution Roadmap

**Stand:** 2026-04-14  
**Status:** Living Document — wird mit jeder Phase aktualisiert

---

## Wo wir herkommen

ContextCruncher startete als ein **OCR Clipboard Manager** — Text vom Bildschirm lesen, in den Zwischenspeicher packen, und für AI-Modelle komprimieren. Ein "Text-Shredder" mit 3 Kompressionsstufen.

## Wo wir jetzt stehen

**ContextCruncher ist ein AI Context Manager.** 22 MCP-Tools, die AI-Agenten aktiv nutzen um ihr eigenes Context-Window intelligent zu füllen. Nicht mehr "Text kürzer machen", sondern "die richtige Information in weniger Tokens".

```
v0.1.0  OCR Clipboard Stack + Compression Levels
v0.2.0  AI Context Manager + Prompt Optimizer (22 MCP Tools)
        ├── smart_crunch       — Content-aware compression
        ├── budget_loader      — Token-budget-aware file loading
        ├── diff_crunch        — Delta-only transmission
        ├── context_pack       — Multi-file relevance bundling
        ├── explain_compression — Strategy transparency
        ├── optimize_prompt    — LLM-powered prompt rewriting
        └── profile management — Custom profiles + API keys
```

---

## Wo wir hinwollen

### Phase 5: `repo_map` — Codebase Intelligence

**Status:** 🔵 Geplant  
**Priorität:** P1 🚨  
**Aufwand:** 🟡 Mittel  
**Dependencies:** Nutzt bestehenden Skeletonizer + Token Counter

**Das Problem:**  
Jeder AI-Agent der ein Repo zum ersten Mal sieht, muss hunderte Dateien lesen um die Architektur zu verstehen. Das verbrennt tausende Tokens bevor die eigentliche Arbeit beginnt.

**Die Lösung:**  
Ein einziger Tool-Call liefert eine strukturierte Karte des gesamten Repos — innerhalb eines Token-Budgets.

```python
repo_map("C:/project/", token_budget=2000)
```

**Output-Beispiel:**
```
📁 myproject (34 files, 6 dirs)

src/
  main.py           — App entry, Flask server         [180 LOC]
    → app, init_db(), register_routes()
  auth.py           — JWT auth, session handling       [420 LOC]
    → login(), verify_token(), refresh_session()
  models/
    user.py         — SQLAlchemy User model            [95 LOC]
      → class User(db.Model), validate_email()
    order.py        — Order + LineItem models          [210 LOC]
      → class Order, class LineItem, total_price()

tests/
  test_auth.py      [12 tests]
  test_models.py    [8 tests]

config/
  settings.py       — ENV-based config                 [45 LOC]
  docker-compose.yml — Postgres + Redis                [30 lines]
```

**Warum das ein Game-Changer ist:**
- AI versteht ein 50.000-Token-Repo in **500 Tokens**
- Perfekter Einstiegspunkt vor `context_pack` oder `budget_loader`
- Nutzt bestehenden Skeletonizer für Signatur-Extraktion
- Null neue Dependencies

**Implementierung:**
| Komponente | Details |
|---|---|
| `repo_mapper.py` (neu) | Directory Walker + Signatur-Extraktion + Budget-Fitting |
| `mcp_server.py` | Neues Tool `repo_map` |
| File-Detection | `.gitignore`-aware, erkennt `node_modules`, `__pycache__`, etc. |
| Budget-Strategie | Wichtige Dateien (entry points, configs) bekommen mehr Platz |

---

### Phase 6: Image Cruncher — Vision-Model-Optimierung

**Status:** 🔵 Geplant  
**Priorität:** P2 🟠

Vision-Modelle (GPT-4o, Claude 3.5) berechnen Kosten pro **Image Tile** (512×512 px). Ein 520×520 Bild kostet 4 Tiles; ein Smart-Resize auf 512×512 senkt es auf 1 Tile — gleiche Qualität, Bruchteil der Kosten.

| Feature | Was es tut | Vorteil |
|---|---|---|
| **Smart Resize** | Skaliert auf AI-optimal 1024px / 1560px | Massive Vision-Token-Einsparung |
| **Grayscale Mode** | Optional B&W-Konvertierung | Kleiner, reicht für Code/Text-OCR |
| **Format-Konvertierung** | PNG/TIFF → WebP/JPEG | Schnellerer Upload, weniger Bandbreite |
| **Metadata Stripping** | Entfernt EXIF (GPS, Kamera) | Privacy + kleinere Datei |
| **MCP Tool** | `crunch_image` — AI-Agent kann Bilder direkt optimieren | Kompletter Workflow |

---

### Phase 7: Desktop Application v2

**Status:** 🔵 Geplant  
**Priorität:** P3 🟢

- **Visual Clipboard History** mit Thumbnails und Text-Vorschau
- **Side-by-Side Variant Comparison** — Original vs. AI Lv.3 auf einen Blick
- **Image Cruncher Controls** — Resize-Slider, Format-Picker, Quality-Preview
- **Drag & Drop** — Dateien oder Bilder direkt ins Fenster ziehen
- **Statistics Dashboard** — Gesamt-Token-Einsparung, Kompressionsraten über Zeit
- **Prompt Optimizer UI** — Profile verwalten, API-Keys konfigurieren, Prompt-Preview

---

## Architektur-Prinzipien

Diese Prinzipien gelten für alle zukünftigen Phasen:

| Prinzip | Bedeutung |
|---|---|
| **Zero Collateral Damage** | Neue Features werden additiv gebaut. Bestehende Module bleiben unverändert. |
| **Module = Testbar** | Jedes neue Modul hat einen eigenen Testfile. Keine MCP-Server-Abhängigkeit in Tests. |
| **MCP-First** | Neue Funktionen werden zuerst als MCP-Tool gebaut, GUI folgt später. |
| **Budget-Aware** | Jedes Tool das Text zurückgibt, akzeptiert ein `token_budget` Parameter. |
| **Minimal Dependencies** | Neue Dependencies nur wenn unvermeidbar. Bevorzuge Standardbibliothek. |
| **Opt-In für Netzwerk** | Features die externe Server kontaktieren sind strikt Opt-in. Lokale Alternativen (Ollama) werden immer unterstützt. |

---

## Technischer Status

```
Modules:     24 Python files in src/contextcruncher/
MCP Tools:   22 exposed tools
Tests:       333 passing (3 pre-existing env-specific failures)
Dependencies: pynput, Pillow, pyperclip, pystray, WinRT, mcp, tiktoken, httpx
Providers:   OpenAI, Anthropic, Ollama (local)
```

---

> **ContextCruncher ist vom "Text-Shredder" zum "AI Context Manager" geworden.**  
> Das nächste Ziel: Vom Context Manager zum **Codebase Intelligence Layer** — die AI versteht nicht nur was sie liest, sondern weiß sofort wo sie suchen muss.
