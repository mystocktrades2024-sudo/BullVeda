"""finbert_sentiment.py — local FinBERT (ONNX) headline sentiment.

Upgrades the crude keyword-lexicon news scorer (data_fetcher.get_news_sentiment) with
ProsusAI/finbert run through ONNX Runtime — NO torch dependency (we already ship
onnxruntime + tokenizers). Generative-LLM-free: FinBERT is a 3-class encoder
(positive/negative/neutral), not a chat model — so it sidesteps the no-paid-license policy
(runs fully local, free) and the LLM-out-of-the-forecast-loop rule (it's a feature scorer,
not a predictor).

Design:
  - LAZY: model + tokenizer load on first call, cached process-wide. If the ONNX model
    isn't present (not yet downloaded) OR onnxruntime/tokenizers are missing, every call
    returns None → callers fall back to the keyword lexicon. Never raises, never blocks.
  - Per-headline 3-class softmax → signed score in [-1, +1] (P(pos) - P(neg)).
  - Aggregates a list of headlines → mean signed score + label.

Model artifacts (downloaded by scripts/download_finbert_onnx.py):
  cache/models/finbert/model.onnx   + tokenizer files (vocab.txt, tokenizer_config.json …)

IMPORTANT (look-ahead): FinBERT only scores headlines available AT SCORE TIME. It is wired
into LIVE scoring (today's pillar/intelligence surfaces). It is NOT retro-applied to the
historical ML training backfill (no historical headline archive exists → that would be
leakage). A forward sentiment log (cache/ml/sentiment_log.jsonl, stamped asof) accumulates
leak-free history so FinBERT can become a true GBM feature in a future honest retrain.
"""
from __future__ import annotations
import os
import threading
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
_MODEL_DIR = BASE_DIR / "cache" / "models" / "finbert"
_ONNX_PATH = _MODEL_DIR / "model.onnx"

_LABELS = ["positive", "negative", "neutral"]  # ProsusAI/finbert id2label order

_lock = threading.Lock()
_state = {"tried": False, "ok": False, "sess": None, "tok": None}


def available() -> bool:
    """True if the ONNX model + runtime are usable (without forcing a full load)."""
    if _state["ok"]:
        return True
    if _state["tried"] and not _state["ok"]:
        return False
    return _ONNX_PATH.exists()


def _ensure_loaded() -> bool:
    if _state["ok"]:
        return True
    if _state["tried"]:
        return _state["ok"]
    with _lock:
        if _state["tried"]:
            return _state["ok"]
        _state["tried"] = True
        try:
            if not _ONNX_PATH.exists():
                return False
            import onnxruntime as ort
            from tokenizers import Tokenizer  # fast tokenizer (no torch)
            tok_json = _MODEL_DIR / "tokenizer.json"
            if tok_json.exists():
                tok = Tokenizer.from_file(str(tok_json))
            else:
                # fallback: build from vocab.txt (BERT WordPiece)
                from tokenizers import BertWordPieceTokenizer
                tok = BertWordPieceTokenizer(str(_MODEL_DIR / "vocab.txt"), lowercase=True)
            sess = ort.InferenceSession(str(_ONNX_PATH), providers=["CPUExecutionProvider"])
            _state.update(sess=sess, tok=tok, ok=True)
            return True
        except Exception:
            _state["ok"] = False
            return False


def _softmax(x):
    import math
    m = max(x)
    e = [math.exp(v - m) for v in x]
    s = sum(e) or 1.0
    return [v / s for v in e]


def score_headline(text: str) -> Optional[float]:
    """Signed sentiment in [-1, +1] = P(positive) - P(negative). None if model unavailable."""
    if not text or not _ensure_loaded():
        return None
    try:
        import numpy as np
        enc = _state["tok"].encode(text)
        ids = enc.ids[:256]
        mask = [1] * len(ids)
        # pad to a small fixed length for batch-of-1
        input_ids = np.array([ids], dtype=np.int64)
        attn = np.array([mask], dtype=np.int64)
        token_type = np.zeros_like(input_ids)
        feed = {}
        for inp in _state["sess"].get_inputs():
            n = inp.name
            if "mask" in n:
                feed[n] = attn
            elif "type" in n:
                feed[n] = token_type
            else:
                feed[n] = input_ids
        logits = _state["sess"].run(None, feed)[0][0]
        probs = _softmax(list(map(float, logits)))
        p = dict(zip(_LABELS, probs))
        return float(p.get("positive", 0.0) - p.get("negative", 0.0))
    except Exception:
        return None


def score_headlines(headlines: list[str]) -> Optional[dict]:
    """Aggregate a list → {score: signed mean, label, n, raw:[...]}. None if unavailable."""
    if not _ensure_loaded():
        return None
    vals = []
    for h in (headlines or [])[:15]:
        s = score_headline(h)
        if s is not None:
            vals.append(s)
    if not vals:
        return None
    mean = sum(vals) / len(vals)
    label = ("bullish" if mean > 0.25 else "slightly bullish" if mean > 0.05
             else "bearish" if mean < -0.25 else "slightly bearish" if mean < -0.05
             else "neutral")
    return {"score": round(mean, 4), "label": label, "n": len(vals)}


if __name__ == "__main__":
    print("finbert available:", available())
    demo = ["Apple beats earnings, raises guidance", "SEC opens fraud probe into the company",
            "Company announces quarterly dividend"]
    print("per-headline:", [score_headline(h) for h in demo])
    print("aggregate:", score_headlines(demo))
