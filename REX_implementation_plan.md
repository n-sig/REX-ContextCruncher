# 🛠️ ContextCruncher — Implementierungsplan

**Basierend auf:** [Codebase Review](file:///C:/Users/LetsPlay/.gemini/antigravity/brain/419d2179-6888-4a19-bc67-201e355c858a/artifacts/codebase_review.md)  
**Ziel:** Alle identifizierten Issues beheben, Note von B+ auf A- heben  
**Regel:** Nach JEDEM Task → `python -m pytest tests/ -v` ausführen. Alle 444+ Tests müssen grün bleiben.

---

## Phase 1 — Kritische Docs & Versions-Fixes (Keine Code-Logik-Änderungen)

### Task 1.1: Version synchronisieren
**Dateien:** `__init__.py`, `README.md`, `CHANGELOG.md`  
**Problem:** `README.md` sagt v2.0.1, `__init__.py` sagt `2.0.0`, CHANGELOG endet bei 2.0.0.

**Anweisung:**
1. In [__init__.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/__init__.py) `__version__` auf `"2.0.1"` bumpen
2. In `CHANGELOG.md` einen `## [2.0.1] - 2026-04-27` Block am Anfang hinzufügen mit Kategorie `### Fixed` und allen Fixes aus diesem Plan, die bereits erledigt sind
3. Sicherstellen, dass README-Badge und `__init__` identisch sind

**Validierung:** `python -c "from contextcruncher import __version__; assert __version__ == '2.0.1'"`

---

### Task 1.2: User-Guide komplett neu schreiben
**Datei:** [docs/user-guide.md](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/docs/user-guide.md)  
**Problem:** Zeigt v0.2.0-beta, falsche Hotkeys (`Ctrl+Alt+S`, `Ctrl+Alt+F`, `Alt+H`), fehlende v2.0 Features.

**Anweisung:**
1. Version-Header auf `v2.0.1` ändern (Zeile 3)
2. ALLE Hotkey-Referenzen durch die echten Defaults aus [config.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/config.py) ersetzen:
   - `Ctrl+Alt+S` → `Ctrl+Shift+2` (Scan Region)
   - `Ctrl+Alt+F` → `Ctrl+Shift+1` (Full Screen OCR)
   - `Ctrl+Alt+C` → `Ctrl+Shift+A` (AI Compact)
   - `Alt+H` → `Ctrl+Shift+H` (Token Heatmap)
3. Kapitelüberschriften und TOC-Links aktualisieren
4. Neue Sections hinzufügen: AI Compression (v2.0), MCP Server, Content Router
5. Hotkey-Tabelle am Ende (Kapitel 12) komplett aus `CLAUDE.md` Zeile 106-114 übernehmen
6. Maus-Seitentasten erwähnen (X1/X2 konfigurierbar)

**Quelle der Wahrheit:** `CLAUDE.md` Zeilen 104-125 und `config.py` `DEFAULT_HOTKEYS`

---

### Task 1.3: README Privacy-Tabelle korrigieren
**Datei:** `README.md`  
**Problem:** Behauptet "No HTTP client, no websocket" — stimmt nicht wenn `ai_compress`/`optimize_prompt` aktiv.

**Anweisung:**  
Die Zeile die "No HTTP client" oder ähnliches behauptet, mit Fußnote versehen:
```
*By default.* When opt-in AI tools (`ai_compress`, `optimize_prompt`) are explicitly invoked, `httpx` makes calls to the configured LLM provider. See [SECURITY.md](SECURITY.md) for details.
```

---

## Phase 2 — Memory & Robustheit (Kleine, sichere Code-Fixes)

### Task 2.1: DiffCache Size-Limit einbauen
**Datei:** [diff_cache.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/diff_cache.py)  
**Problem:** `_cache` dict wächst unbegrenzt → Memory Leak bei langen Sessions.

**Anweisung:**
1. `collections.OrderedDict` importieren
2. `__init__` ändern: `self._cache: OrderedDict[str, str] = OrderedDict()` und `self._timestamps` analog
3. Konstante `_MAX_CACHE_SIZE = 100` am Modulanfang
4. In `store()` nach dem Einfügen: Wenn `len(self._cache) > _MAX_CACHE_SIZE`, ältesten Eintrag mit `self._cache.popitem(last=False)` entfernen (und Timestamp analog)
5. Bestehende Tests in `tests/` prüfen und ggf. einen Test für das Eviction-Verhalten hinzufügen

**Test:** Neuer Test `test_diff_cache_eviction` der 150 Einträge speichert und prüft, dass `cache.size() <= 100`.

---

### Task 2.2: MCP search_stack mit stack_size anreichern
**Datei:** [mcp_server.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/mcp_server.py) Zeile 260-291  
**Problem:** Leerer Stack vs. "nichts gefunden" nicht unterscheidbar für AI-Agents.

**Anweisung:**  
Return-Wert von `search_stack` ändern: Statt `list[dict]` ein `dict` zurückgeben:
```python
return {
    "stack_size": _stack.size(),
    "results": entries,  # oder die message-Liste
}
```

> [!WARNING]
> Bestehende Tests für `search_stack` werden brechen! Alle Stellen die `search_stack()` testen, müssen auf das neue Dict-Format angepasst werden. Grep nach `search_stack` in `tests/`.

---

### Task 2.3: Auto-Crunch Toggle thread-safe machen
**Datei:** [tray.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/tray.py) Zeile 321-325  
**Problem:** `_auto_crunch_enabled` Toggle ohne Lock — potentielle Race Condition.

**Anweisung:**
1. In `__init__`: `self._toggle_lock = threading.Lock()` hinzufügen
2. `_handle_toggle_auto_crunch` wrappen:
```python
def _handle_toggle_auto_crunch(self, icon, item):
    with self._toggle_lock:
        self._auto_crunch_enabled = not self._auto_crunch_enabled
        if self._on_toggle_auto_crunch:
            self._on_toggle_auto_crunch(self._auto_crunch_enabled)
    self.update_menu()
```

---

## Phase 3 — Security Scanner verbessern

### Task 3.1: IPv4-Pattern kontext-sensitiv machen
**Datei:** [security_scanner.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/security_scanner.py) Zeile 70-71  
**Problem:** `3.11.0.1` (Python-Version) wird als IP redaktiert.

**Anweisung:**  
Den einfachen Regex durch eine Funktion ersetzen:
1. IPv4-Pattern aus `_DEFAULT_SECRETS_PATTERNS` entfernen
2. Neue Funktion `_redact_ips(text: str) -> str` die:
   - Alle IPv4-Matches findet
   - Für jeden Match prüft: Steht davor `version`, `v`, `Ver`, `python`, `node`, `npm`? → Skip
   - Sind alle Oktette ≤ 255? (Pflicht für echte IPs)
   - Nur redaktieren wenn KEIN Versions-Kontext
3. In `redact_secrets()` nach Pass 1, vor Pass 2 aufrufen
4. Tests: `"Python 3.11.0.1"` → NICHT redaktiert. `"connect to 192.168.1.1"` → redaktiert.

---

### Task 3.2: UUID-Redaktion kontext-sensitiv machen
**Datei:** [security_scanner.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/security_scanner.py) Zeile 59-62  
**Problem:** UUIDs in URLs und Konfigdateien werden zerstört.

**Anweisung:**  
Analog zu Task 3.1:
1. UUID-Pattern in eine Funktion `_redact_uuids(text: str) -> str` extrahieren
2. Skip wenn UUID Teil einer URL ist (`http://`, `https://`, `://` davor)
3. Skip wenn UUID in typischem Config-Kontext steht (`id:`, `uuid:`, `correlation`)
4. Redaktieren nur bei Standalone-UUIDs oder in Kombination mit Secret-Keywords (`secret`, `token`, `key`, `password`)

> [!IMPORTANT]
> Trade-off: Lieber zu vorsichtig (nicht redaktieren) als URLs zerstören. Das Tool verarbeitet primär Entwickler-Kontext.

---

## Phase 4 — Code-Qualität (Refactoring)

### Task 4.1: Provider-Credentials entduplizieren
**Datei:** [prompt_optimizer.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/prompt_optimizer.py)  
**Problem:** Identische Provider-Auflösung in `optimize()` (Z.800-845) und `compress()` (Z.988-1065).

**Anweisung:**
1. Neue private Funktion erstellen:
```python
@dataclass
class _ProviderCredentials:
    provider: str
    model: str
    api_key: str
    endpoint: str
    error: str = ""

def _resolve_credentials(provider: str, model: str) -> _ProviderCredentials:
    """Resolve API keys/endpoints for the given provider."""
    config = get_provider_config()
    # ... einmalige Implementierung der provider-switch-Logik
```
2. Beide Funktionen (`optimize`, `compress`) refactoren um `_resolve_credentials()` zu nutzen
3. Bei `error != ""` den jeweiligen Result-Typ mit dem Error zurückgeben

**Validierung:** Alle `test_prompt_optimizer*.py` und `test_ai_compress*.py` Tests müssen grün bleiben.

---

### Task 4.2: Skeletonizer JS/TS Regex-Fallback verbessern
**Datei:** [skeletonizer.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/skeletonizer.py)  
**Problem:** Class method shorthands (`bar() {}`) und Getters/Setters werden nicht erkannt.

**Anweisung:**  
In `_crude_js_ts_skeleton()` die Regex-Patterns erweitern um:
- Method shorthand: `^\s+\w+\s*\(` (indented identifier gefolgt von Klammer)
- Getter/Setter: `^\s+(get|set)\s+\w+\s*\(`
- Arrow functions in Klassen: `^\s+\w+\s*=\s*\(`
- Static methods: `^\s+static\s+`

Tests mit einem JS-Snippet das diese Patterns enthält schreiben.

---

### Task 4.3: _relevance_score für CamelCase verbessern
**Datei:** [mcp_server.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/mcp_server.py) Zeile 916-931  
**Problem:** `getStackSize` wird als ein Wort behandelt.

**Anweisung:**
1. Hilfsfunktion `_tokenize(text: str) -> set[str]` erstellen die:
   - Auf Whitespace splittet
   - CamelCase aufbricht: `getStackSize` → `{get, stack, size, getstacksize}`
   - snake_case aufbricht: `get_stack_size` → `{get, stack, size, get_stack_size}`
2. In `_relevance_score` statt `.split()` die neue `_tokenize()` verwenden

---

## Phase 5 — Tray Thread-Safety verifizieren

### Task 5.1: Settings-Handler Thread-Modell prüfen
**Datei:** [tray.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/tray.py) Zeile 332-335  
**Problem:** `_handle_settings` startet einen neuen Thread — falls dort Tk-UI erstellt wird, verstößt das gegen Design-Decision #1.

**Anweisung:**
1. In [main.py](file:///c:/Users/LetsPlay/Desktop/ContextCruncher/src/contextcruncher/main.py) prüfen was `_on_settings` tut
2. Falls es `schedule()` oder `root.after()` nutzt → Thread-Wrapper ist redundant aber harmlos. Kommentar hinzufügen warum.
3. Falls es direkt `Toplevel()` erstellt → **Critical Fix:** Thread-Wrapper durch `get_tk_manager().schedule()` ersetzen

---

## Phase 6 — Abschluss

### Task 6.1: CHANGELOG finalisieren
**Datei:** `CHANGELOG.md`  
Alle erledigten Fixes aus Phase 1-5 unter `[2.0.1]` eintragen.

### Task 6.2: Vollständiger Testlauf
```bash
python -m pytest tests/ -v
```
Alle Tests müssen grün sein. Neue Tests aus den Tasks müssen enthalten sein.

### Task 6.3: CLAUDE.md aktualisieren
Bug-Tracker in CLAUDE.md um die neuen Fixes erweitern (BUG-15 ff.).

---

## Zusammenfassung

| Phase | Tasks | Risiko | Geschätzt |
|---|---|---|---|
| 1 — Docs | 1.1, 1.2, 1.3 | ⬜ Kein | 30 min |
| 2 — Memory | 2.1, 2.2, 2.3 | 🟨 Niedrig | 25 min |
| 3 — Security | 3.1, 3.2 | 🟨 Mittel | 30 min |
| 4 — Refactoring | 4.1, 4.2, 4.3 | 🟧 Mittel | 40 min |
| 5 — Thread-Safety | 5.1 | 🟨 Niedrig | 10 min |
| 6 — Abschluss | 6.1, 6.2, 6.3 | ⬜ Kein | 15 min |

**Gesamt: ~14 Tasks, ~2.5h Arbeitszeit**
