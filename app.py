"""
╔═══════════════════════════════════════════════════════════════════╗
║  Izugbe Tri-Core Engine — Pure Python Backend                    ║
║  Lead Developer : Madu Chinemerem Clarence                        ║
║                                                                   ║
║  Run:  python app.py                                              ║
║                                                                   ║
║  Endpoints                                                        ║
║  ─────────────────────────────────────────────────────────────── ║
║  POST /api/translate     → JSON batch translation                 ║
║  GET  /api/stream?name=… → text/event-stream (SSE, per token)    ║
║  GET  /api/glyphs        → JSON (all 36 Akagu SVG glyphs)        ║
║  GET  /api/phonemes      → JSON (Izugbe phoneme reference)       ║
║  GET  /api/health        → JSON (server health check)            ║
╚═══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import time
from flask import Flask, Response, jsonify, request, stream_with_context

from izugbe_engine import (
    IzugbeTriCoreEngine,
    AKAGU_MAP,
    AKAGU_TO_IZUGBE,
    DIGRAPHS,
    LIGHT_VOWELS,
    HEAVY_VOWELS,
)
from akagu_glyphs import AKAGU_GLYPHS

# ──────────────────────────────────────────────────────────────────
app    = Flask(__name__)
engine = IzugbeTriCoreEngine()

# ──────────────────────────────────────────────────────────────────
#  SSE HELPER
# ──────────────────────────────────────────────────────────────────

def sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event frame."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ──────────────────────────────────────────────────────────────────
#  MIDDLEWARE — CORS open for local dev
# ──────────────────────────────────────────────────────────────────

@app.after_request
def set_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found. See /api/health for available routes."}), 404

@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "Method not allowed."}), 405

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error.", "detail": str(e)}), 500


# ──────────────────────────────────────────────────────────────────
#  GET /api/health
# ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
def api_health():
    """
    Health check + API route map.

    Response
    --------
    {
      "status":   "ok",
      "engine":   "IzugbeTriCoreEngine v2.0",
      "glyphs":   36,
      "routes":   { ... }
    }
    """
    return jsonify({
        "status":   "ok",
        "engine":   "IzugbeTriCoreEngine v2.0",
        "author":   "Madu Chinemerem Clarence",
        "glyphs":   len(AKAGU_GLYPHS),
        "phonemes": len(AKAGU_MAP),
        "routes": {
            "POST /api/translate":  "Batch translate — full JSON pipeline result",
            "GET  /api/stream":     "SSE streaming translate — ?name=<izugbe_word>",
            "GET  /api/glyphs":     "All 36 Akagu SVG glyph outlines",
            "GET  /api/phonemes":   "Complete Izugbe -> Akagu phoneme reference",
            "GET  /api/health":     "This route",
        },
    })


# ──────────────────────────────────────────────────────────────────
#  GET /api/glyphs
# ──────────────────────────────────────────────────────────────────

@app.get("/api/glyphs")
def api_glyphs():
    """
    Return all 36 Akagu SVG glyph outlines keyed by Izugbe letter.

    Response shape per entry
    ------------------------
    {
      "a": {
        "cat":     "Vowel",
        "viewBox": "-40 -20 1212 940",
        "path":    "M960.00 5.00 C970.00 ..."
      },
      ...
    }
    """
    return jsonify(AKAGU_GLYPHS)


# ──────────────────────────────────────────────────────────────────
#  GET /api/phonemes
# ──────────────────────────────────────────────────────────────────

@app.get("/api/phonemes")
def api_phonemes():
    """
    Complete Izugbe -> Akagu phoneme reference table.

    Response
    --------
    {
      "total": 36,
      "light_vowels": ["a", "i", "o", "u"],
      "heavy_vowels": ["e", "i", "o", "u"],
      "digraphs":     ["ch", "gb", ...],
      "map": [
        {
          "izugbe":    "ch",
          "akagu":     "\u75BE",
          "codepoint": "U+75BE",
          "category":  "Digraph"
        },
        ...
      ]
    }
    """
    entries = []
    for izugbe, akagu in AKAGU_MAP.items():
        if izugbe in DIGRAPHS:
            cat = "Digraph"
        elif izugbe in LIGHT_VOWELS or izugbe in HEAVY_VOWELS:
            cat = "Vowel"
        else:
            cat = "Consonant"
        entries.append({
            "izugbe":    izugbe,
            "akagu":     akagu,
            "codepoint": f"U+{ord(akagu):04X}",
            "category":  cat,
        })

    order = {"Digraph": 0, "Vowel": 1, "Consonant": 2}
    entries.sort(key=lambda x: (order[x["category"]], x["izugbe"]))

    return jsonify({
        "total":        len(entries),
        "light_vowels": sorted(LIGHT_VOWELS),
        "heavy_vowels": sorted(HEAVY_VOWELS),
        "digraphs":     sorted(DIGRAPHS),
        "map":          entries,
    })


# ──────────────────────────────────────────────────────────────────
#  POST /api/translate
# ──────────────────────────────────────────────────────────────────

@app.post("/api/translate")
def api_translate():
    """
    Batch translate — runs the full three-core pipeline and returns
    a complete JSON result in a single response.

    Request body
    ------------
    { "name": "Chinemerem" }

    Response
    --------
    {
      "original":    "Chinemerem",
      "normalized":  "chinemerem",
      "valid":       true,
      "encoded":     "\u75BEinemerem",
      "tokens": [
        { "izugbe": "ch", "akagu": "\u75BE", "codepoint": "U+75BE" },
        { "izugbe": "i",  "akagu": "i",      "codepoint": "U+0069" },
        ...
      ],
      "core1_diags": [
        { "core": "CORE-1", "sev": "INFO", "message": "..." }
      ],
      "core2_diags": [
        { "core": "CORE-2", "sev": "OK",   "message": "..." }
      ]
    }

    Error responses
    ---------------
    400  { "error": "Missing or empty 'name' field." }
    """
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Missing or empty 'name' field."}), 400

    return jsonify(engine.run(name))


# ──────────────────────────────────────────────────────────────────
#  GET /api/stream
# ──────────────────────────────────────────────────────────────────

@app.get("/api/stream")
def api_stream():
    """
    SSE streaming translate — emits one event per pipeline stage / token.
    Connect with EventSource or curl -N.

    Query param
    -----------
    ?name=Chinemerem

    Event sequence
    --------------
    data: {"stage": "core1",       "original": "...", "normalized": "...", "diags": [...]}
    data: {"stage": "core2",       "valid": true, "diags": [...]}
    data: {"stage": "core3_token", "token": {...}, "encoded_so_far": "..."}
    ...  (one core3_token per phoneme)
    data: {"stage": "done",        "original": "...", "normalized": "...", "encoded": "..."}

    On validation failure
    ---------------------
    data: {"stage": "aborted", "reason": "Core-2 validation failed."}

    Usage examples
    --------------
    # curl
    curl -N "http://localhost:5000/api/stream?name=Nwachukwu"

    # Python (pip install sseclient-py requests)
    import json, requests, sseclient
    resp = requests.get("http://localhost:5000/api/stream", params={"name": "Nwachukwu"}, stream=True)
    for event in sseclient.SSEClient(resp):
        print(json.loads(event.data))
    """
    name = (request.args.get("name") or "").strip()
    if not name:
        def _err():
            yield sse_event({"stage": "error", "reason": "Missing 'name' query parameter."})
        return Response(_err(), mimetype="text/event-stream")

    def generate():
        for event_data in engine.run_stream(name):
            yield sse_event(event_data)
            time.sleep(0.06)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────────
#  ENTRYPOINT
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Izugbe Tri-Core Engine  ·  Pure Backend             ║")
    print("║  Author : Madu Chinemerem Clarence                   ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  POST  /api/translate                                ║")
    print("║  GET   /api/stream?name=…                            ║")
    print("║  GET   /api/glyphs                                   ║")
    print("║  GET   /api/phonemes                                 ║")
    print("║  GET   /api/health                                   ║")
    print("╚══════════════════════════════════════════════════════╝")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
