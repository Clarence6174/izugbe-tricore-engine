"""
╔══════════════════════════════════════════════════════════════════╗
║  IZUGBE TRI-CORE ENGINE  ·  v2.0                                ║
║  Lead Developer : Madu Chinemerem Clarence                       ║
║  Core Language  : Python 3.8+                                    ║
║  Pipeline       : English → Izugbe → Akagu Cipher               ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Generator

# ──────────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────────

LIGHT_VOWELS   = frozenset("aịọụ")
HEAVY_VOWELS   = frozenset("eiou")
ALL_VOWELS     = LIGHT_VOWELS | HEAVY_VOWELS

DIGRAPHS: frozenset[str] = frozenset(
    ["ch", "gb", "gh", "gw", "kp", "kw", "nw", "ny", "sh"]
)

# Akagu cipher map — digraphs MUST appear before singles in matching
AKAGU_MAP: dict[str, str] = {
    # ── Digraphs ──────────────────────────────────────────────────
    "ch": "\u75BE",
    "gb": "\u5931",
    "gh": "\u5B9F",
    "gw": "\u5BA4",
    "kp": "\u6E7F",
    "kw": "\u0051",   # Q — Akagu kw glyph
    "nw": "\u5AC9",
    "ny": "\u6F06",
    "sh": "\u8CEA",
    # ── Dotted vowels ─────────────────────────────────────────────
    "ị":  "\u1ECB",
    "ọ":  "\u1ECD",
    "ụ":  "\u1EE5",
    # ── Standard vowels ───────────────────────────────────────────
    "a": "a", "e": "e", "i": "i", "o": "o", "u": "u",
    # ── Consonants ────────────────────────────────────────────────
    "b": "b", "d": "d", "f": "\u0060",
    "g": "g", "h": "h", "j": "j", "k": "k",
    "l": "l", "m": "m", "n": "n",
    "ṅ": "\u00F1",
    "p": "p", "r": "r", "s": "s", "t": "t",
    "v": "v", "w": "w", "y": "y", "z": "z",
}

# Reverse map: akagu unicode char → izugbe letter (for glyph lookup)
AKAGU_TO_IZUGBE: dict[str, str] = {v: k for k, v in AKAGU_MAP.items()}

# English-keyboard multi-char substitutions (applied in this order)
_MULTI_SUBS: list[tuple[str, str]] = [
    ("oo", "ọ"), ("ii", "ị"), ("uu", "ụ"),
    ("ng", "ṅ"), ("ph", "f"), ("qu", "kw"),
    ("ck", "k"), ("kk", "k"), ("tt", "t"),
    ("ss", "s"), ("ll", "l"), ("rr", "r"),
]

_DISALLOWED_FINALS = frozenset("bdfghjklprstvyz")
_ENG_SUFFIX_RE     = re.compile(r"(ance|ence|tion|sion|ment|ness|ous|ive|ck|tch)$", re.I)
_ENG_CLUSTER_RE    = re.compile(r"\b(cl|cr|bl|br|fl|fr|gl|gr|pl|pr|str|spl|spr|thr)", re.I)
_CONSONANT_RUN_RE  = re.compile(r"[^aeiouịọụ ]{3,}")

# ──────────────────────────────────────────────────────────────────
#  DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────

class Severity(Enum):
    OK      = auto()
    INFO    = auto()
    WARNING = auto()
    ERROR   = auto()


@dataclass
class Diag:
    core:    str
    sev:     Severity
    message: str

    def as_dict(self) -> dict:
        return {"core": self.core, "sev": self.sev.name, "message": self.message}


@dataclass
class PhonemeToken:
    """One phoneme in the encoded output."""
    izugbe:  str          # source Izugbe letter(s), e.g. "ch", "ị"
    akagu:   str          # Akagu unicode character
    codepoint: str        # e.g. "U+75BE"

    def as_dict(self) -> dict:
        return {
            "izugbe":    self.izugbe,
            "akagu":     self.akagu,
            "codepoint": self.codepoint,
        }


@dataclass
class Core1Result:
    original:   str
    normalized: str
    diags:      list[Diag] = field(default_factory=list)


@dataclass
class Core2Result:
    token:  str
    valid:  bool
    diags:  list[Diag] = field(default_factory=list)


@dataclass
class Core3Result:
    tokens:  list[PhonemeToken] = field(default_factory=list)
    encoded: str = ""           # full concatenated Akagu string


# ──────────────────────────────────────────────────────────────────
#  CORE 1 — NORMALIZER
# ──────────────────────────────────────────────────────────────────

class Core1_Normalizer:
    """Lowercases input and applies English-keyboard → Izugbe substitutions."""

    def process(self, raw: str) -> Core1Result:
        result = Core1Result(original=raw, normalized="")
        token  = raw.strip().lower()

        # ── Foreign screening (pre-substitution) ─────────────────────
        sm = _ENG_SUFFIX_RE.search(token)
        cm = _ENG_CLUSTER_RE.search(token)
        if sm:
            result.diags.append(Diag("CORE-1", Severity.WARNING,
                f"'{raw}' carries the English suffix '-{sm.group(1)}' — "
                "this is a foreign name. Encoding is approximate."))
        elif cm:
            result.diags.append(Diag("CORE-1", Severity.WARNING,
                f"'{raw}' has the consonant cluster '{cm.group(1)}' absent "
                "in Igbo phonology — likely a foreign name."))

        # ── Multi-char substitutions ──────────────────────────────────
        applied: list[str] = []
        for src, dst in _MULTI_SUBS:
            if src in token:
                token = token.replace(src, dst)
                applied.append(f"{src}→{dst}")

        # c→k (but NOT c in ch)
        new = re.sub(r"c(?!h)", "k", token)
        if new != token:
            applied.append("c→k")
            token = new

        # x→ks
        if "x" in token:
            token = token.replace("x", "ks")
            applied.append("x→ks")

        if applied:
            result.diags.append(Diag("CORE-1", Severity.INFO,
                f"Substitutions applied: {', '.join(applied)}"))
        else:
            result.diags.append(Diag("CORE-1", Severity.INFO,
                "No substitutions needed — input appears to be native Izugbe."))

        # ── Post-normalisation phonotactics ───────────────────────────
        if _CONSONANT_RUN_RE.search(token):
            result.diags.append(Diag("CORE-1", Severity.WARNING,
                f"'{token}' contains a 3+ consonant cluster — "
                "unusual in Igbo CV phonotactics."))

        if token and token[-1] in _DISALLOWED_FINALS:
            result.diags.append(Diag("CORE-1", Severity.WARNING,
                f"'{token}' ends in '{token[-1]}' — Igbo words typically "
                "end in a vowel or nasal (m / n / ṅ)."))

        result.normalized = token
        return result


# ──────────────────────────────────────────────────────────────────
#  CORE 2 — VALIDATOR  (Dị Ọcha)
# ──────────────────────────────────────────────────────────────────

class Core2_Validator:
    """Validates Onwu phoneme set membership and vowel harmony."""

    _ALLOWED = frozenset(AKAGU_MAP.keys())

    def process(self, token: str) -> Core2Result:
        result = Core2Result(token=token, valid=False)

        # ── 1. Symbol membership ──────────────────────────────────────
        bad = [t for t in self._tokenise(token) if t != " " and t not in self._ALLOWED]
        if bad:
            result.diags.append(Diag("CORE-2", Severity.ERROR,
                f"Unrecognised symbols {bad!r} — not in the 36-letter Onwu alphabet."))
            return result

        result.diags.append(Diag("CORE-2", Severity.OK,
            "All symbols confirmed within the 36-letter Izugbe/Onwu alphabet."))

        # ── 2. Vowel harmony (per root) ───────────────────────────────
        any_violation = False
        for word in token.split():
            vowels  = [c for c in word if c in ALL_VOWELS]
            lights  = [c for c in vowels if c in LIGHT_VOWELS]
            heavies = [c for c in vowels if c in HEAVY_VOWELS]
            if lights and heavies:
                any_violation = True
                result.diags.append(Diag("CORE-2", Severity.WARNING,
                    f"Vowel harmony: '{word}' mixes "
                    f"Light {{{', '.join(sorted(set(lights)))}}} + "
                    f"Heavy {{{', '.join(sorted(set(heavies)))}}}. "
                    "May be a loanword, compound, or foreign name."))

        if not any_violation:
            result.diags.append(Diag("CORE-2", Severity.OK,
                "Vowel harmony passed — root is phonologically pure."))

        result.valid = True
        return result

    @staticmethod
    def _tokenise(s: str) -> list[str]:
        out, i = [], 0
        while i < len(s):
            pair = s[i:i+2]
            if pair in DIGRAPHS:
                out.append(pair); i += 2
            else:
                out.append(s[i]); i += 1
        return out


# ──────────────────────────────────────────────────────────────────
#  CORE 3 — ENCODER
# ──────────────────────────────────────────────────────────────────

class Core3_Encoder:
    """
    Converts validated Izugbe → Akagu cipher.
    Digraphs are matched greedily before single phonemes.
    Yields one PhonemeToken at a time for streaming.
    """

    def process(self, token: str) -> Core3Result:
        result = Core3Result()
        for pt in self._encode_stream(token):
            result.tokens.append(pt)
        result.encoded = "".join(t.akagu for t in result.tokens)
        return result

    def stream(self, token: str) -> Generator[PhonemeToken, None, None]:
        """Yield one PhonemeToken at a time — use for SSE streaming."""
        yield from self._encode_stream(token)

    @staticmethod
    def _encode_stream(token: str) -> Generator[PhonemeToken, None, None]:
        i = 0
        while i < len(token):
            ch = token[i]
            if ch == " ":
                yield PhonemeToken(izugbe=" ", akagu=" ", codepoint="U+0020")
                i += 1
                continue
            pair = token[i:i+2]
            if pair in DIGRAPHS and pair in AKAGU_MAP:
                a = AKAGU_MAP[pair]
                yield PhonemeToken(
                    izugbe=pair, akagu=a,
                    codepoint=f"U+{ord(a):04X}"
                )
                i += 2
            elif ch in AKAGU_MAP:
                a = AKAGU_MAP[ch]
                yield PhonemeToken(
                    izugbe=ch, akagu=a,
                    codepoint=f"U+{ord(a):04X}"
                )
                i += 1
            else:
                # Pass-through unmapped character
                yield PhonemeToken(izugbe=ch, akagu=ch, codepoint=f"U+{ord(ch):04X}")
                i += 1


# ──────────────────────────────────────────────────────────────────
#  PIPELINE ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────

class IzugbeTriCoreEngine:
    """
    Orchestrates Core1 → Core2 → Core3.

    Usage (batch)
    ─────────────
        engine = IzugbeTriCoreEngine()
        result = engine.run("Chinemerem")

    Usage (streaming — for SSE)
    ───────────────────────────
        for event in engine.run_stream("Chinemerem"):
            # event is a dict with 'stage' and payload
            send_sse(event)
    """

    def __init__(self) -> None:
        self.core1 = Core1_Normalizer()
        self.core2 = Core2_Validator()
        self.core3 = Core3_Encoder()

    # ── Batch mode ────────────────────────────────────────────────────

    def run(self, text: str) -> dict:
        r1 = self.core1.process(text)
        r2 = self.core2.process(r1.normalized)
        r3 = self.core3.process(r1.normalized) if r2.valid else Core3Result()
        return {
            "original":   text,
            "normalized": r1.normalized,
            "valid":      r2.valid,
            "encoded":    r3.encoded,
            "tokens":     [t.as_dict() for t in r3.tokens],
            "core1_diags":[d.as_dict() for d in r1.diags],
            "core2_diags":[d.as_dict() for d in r2.diags],
        }

    # ── Streaming mode ────────────────────────────────────────────────

    def run_stream(self, text: str) -> Generator[dict, None, None]:
        """
        Yields dicts — each is one SSE event payload.
        Stages: core1 → core2 → (per-token) core3 → done
        """
        # ── Core 1 ───────────────────────────────────────────────────
        r1 = self.core1.process(text)
        yield {
            "stage": "core1",
            "original":   text,
            "normalized": r1.normalized,
            "diags": [d.as_dict() for d in r1.diags],
        }

        # ── Core 2 ───────────────────────────────────────────────────
        r2 = self.core2.process(r1.normalized)
        yield {
            "stage": "core2",
            "valid": r2.valid,
            "diags": [d.as_dict() for d in r2.diags],
        }

        if not r2.valid:
            yield {"stage": "aborted", "reason": "Core-2 validation failed."}
            return

        # ── Core 3 — stream one token per event ──────────────────────
        encoded_so_far = ""
        for pt in self.core3.stream(r1.normalized):
            encoded_so_far += pt.akagu
            yield {
                "stage":          "core3_token",
                "token":          pt.as_dict(),
                "encoded_so_far": encoded_so_far,
            }

        yield {
            "stage":   "done",
            "original":   text,
            "normalized": r1.normalized,
            "encoded":    encoded_so_far,
        }
