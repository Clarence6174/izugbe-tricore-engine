# Contributing to Izugbe Tri-Core Engine

Thank you for your interest in contributing to this project. This is a
linguistic engineering system bridging Igbo language preservation with
software craftsmanship. Contributions that respect both the technical
and cultural dimensions of the work are warmly welcomed.

---

## Project Context

| Item | Detail |
|------|--------|
| **Lead Developer** | Madu Chinemerem Clarence |
| **Language** | Python 3.8+ |
| **Stack** | Flask · SSE · SVG |
| **Script Font** | Akagu — Chiadikobi Nwaubani (2015) |
| **Linguistic Base** | Igbo Izugbe (Onwu orthography, 36 letters) |

---

## Getting Started

```bash
git clone <repo-url>
cd izugbe_backend

pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

---

## Project Structure

```
izugbe_backend/
├── app.py                  ← Flask server + HTML UI + SSE endpoints
├── izugbe_engine.py        ← Tri-Core pipeline (Core1, Core2, Core3)
├── akagu_glyphs.py         ← 36 Akagu SVG glyph paths (auto-generated)
├── architecture.excalidraw ← System architecture diagram
├── requirements.txt
├── CONTRIBUTING.md
└── README.md
```

---

## The Three Cores — Design Contract

Each Core is a **plain Python class** with a `process()` method.
They must remain **independent** — no Core imports another.
The `IzugbeTriCoreEngine` orchestrator wires them together.

```
Core1_Normalizer   →   Core2_Validator   →   Core3_Encoder
    .process(raw)       .process(token)       .process(token)
    → Core1Result       → Core2Result         → Core3Result
```

### Core 1 — Normalizer
- Input: raw user string (any casing, any script proximity)
- Output: lowercase Izugbe string with substitutions applied
- Must **not** break Igbo digraphs (`ch`, `nw`, `ny`, etc.)
- The regex `c(?!h)` pattern for `c→k` must be preserved

### Core 2 — Validator (Dị Ọcha)
- Must check **symbol membership** against all 36 Onwu phonemes
- Must check **vowel harmony** per word/root, not across spaces
- Light vowels: `{a, ị, ọ, ụ}` — Heavy vowels: `{e, i, o, u}`
- Validation failure should block Core 3, not crash

### Core 3 — Encoder
- **Digraphs must always be matched before singles** — this is non-negotiable
- Must support both batch (`.process()`) and streaming (`.stream()`)
- The `.stream()` generator is used by the SSE endpoint — keep it lazy

---

## Adding a New Core

Future cores (e.g. Core 4 — Odinani Dictionary, Core 5 — Prayer Cipher)
should follow this pattern:

```python
# izugbe_engine.py

@dataclass
class Core4Result:
    token:  str
    matches: list[dict]
    diags:   list[Diag] = field(default_factory=list)

class Core4_OdinaniDictionary:
    """Looks up validated Izugbe tokens in the Odinani lexicon."""

    def process(self, token: str) -> Core4Result:
        result = Core4Result(token=token, matches=[])
        # ... lookup logic ...
        return result
```

Then wire it into `IzugbeTriCoreEngine.run()` and `run_stream()`.

---

## API Conventions

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | HTML interface (served by Flask) |
| `/api/translate` | POST | Batch pipeline — returns full JSON |
| `/api/stream` | GET | SSE pipeline — streams per token |
| `/api/glyphs` | GET | All 36 Akagu SVG glyphs |

### SSE Event Schema

Every event emitted from `/api/stream` is a JSON object with a `stage` key:

```
stage: "core1"         → normalized string + Core-1 diagnostics
stage: "core2"         → valid bool + Core-2 diagnostics
stage: "core3_token"   → one PhonemeToken + encoded_so_far
stage: "done"          → final encoded string
stage: "aborted"       → reason string (Core-2 failure)
stage: "stream_end"    → signals EventSource can close
```

Do not add new stages without updating the frontend `EventSource` handler
in `app.py`.

---

## Diagnostic Severity Levels

```python
class Severity(Enum):
    OK      # Everything passed
    INFO    # Informational — substitution applied, etc.
    WARNING # Suspicious — foreign name, harmony violation
    ERROR   # Fatal — unknown symbol, blocks Core 3
```

Warnings must **never** block the pipeline. Only `ERROR` aborts.

---

## Linguistic Guidelines

This project encodes the **Igbo language** — a tonal language spoken by
over 45 million people, primarily in southeastern Nigeria. Please:

- Do not alter the 36-letter Onwu mapping without linguistic justification
- Igbo vowel harmony is a real phonological feature — treat warnings as
  informative, not errors (many names naturally cross harmony sets)
- Digraphs (`ch`, `gb`, `gh`, `gw`, `kp`, `kw`, `nw`, `ny`, `sh`) are
  single phonemes in Igbo — they must never be split during encoding
- The Akagu script glyphs are the intellectual property of
  **Chiadikobi Nwaubani** (2015). Do not redistribute them outside
  the scope of this project without permission

---

## Code Style

- Python 3.8+ compatible (`from __future__ import annotations`)
- Type hints on all public methods
- `@dataclass` for all result objects
- No external dependencies beyond `flask` — keep it lean
- Snake_case for variables/functions, PascalCase for classes
- Each Core class gets its own section clearly delimited with
  `# ─────` banners in `izugbe_engine.py`

---

## Running Tests

```bash
# Quick smoke test — all cores, batch mode
python3 -c "
from izugbe_engine import IzugbeTriCoreEngine
engine = IzugbeTriCoreEngine()
names = ['Chinemerem','Nwachukwu','nwanyị','ụlọ','Clarence']
for n in names:
    r = engine.run(n)
    print(f'{n:16} -> {r[\"normalized\"]:18} -> {r[\"encoded\"]}')
"

# SSE stream test
python3 -c "
from izugbe_engine import IzugbeTriCoreEngine
engine = IzugbeTriCoreEngine()
for event in engine.run_stream('Chukwuemeka'):
    print(event)
"
```

---

## Submitting Changes

1. Fork the repository
2. Create a branch: `git checkout -b feature/core4-odinani`
3. Make your changes — keep each Core's contract intact
4. Run the smoke tests above
5. Open a pull request with a clear description of what changed and why

For linguistic changes (new substitution rules, phoneme additions),
please include a reference to an Igbo orthography source.

---

*Ọ dị mma. Jee ozi.*
