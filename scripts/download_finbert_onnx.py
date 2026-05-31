#!/usr/bin/env python3
"""download_finbert_onnx.py — fetch ProsusAI/finbert and export to ONNX (one-time).

Produces cache/models/finbert/{model.onnx, tokenizer.json/vocab.txt} so finbert_sentiment.py
can run sentiment via onnxruntime WITHOUT torch at runtime.

Export needs torch+transformers TEMPORARILY. We try, in order:
  1. transformers.onnx / optimum export (if torch+transformers happen to be present)
  2. direct HF hub download of a pre-exported ONNX (yiyanghkust/finbert-tone-onnx or
     ProsusAI variants) via huggingface_hub — no torch needed
  3. clear instructions if neither works (the live scorer falls back to lexicon meanwhile)

Idempotent: skips if cache/models/finbert/model.onnx already exists.
"""
import os, sys, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "cache" / "models" / "finbert"
OUT.mkdir(parents=True, exist_ok=True)
ONNX = OUT / "model.onnx"

if ONNX.exists() and ONNX.stat().st_size > 1_000_000:
    print(f"[finbert] already present: {ONNX} ({ONNX.stat().st_size//1024//1024}MB) — skip")
    sys.exit(0)


def _try_hub_prebuilt():
    """Download a community pre-exported ONNX FinBERT (no torch)."""
    try:
        from huggingface_hub import hf_hub_download
    except Exception as e:
        print(f"[finbert] huggingface_hub missing ({e})"); return False
    # candidates that ship an onnx + tokenizer
    candidates = [
        ("jonngan/finbert-onnx", ["model.onnx", "tokenizer.json", "vocab.txt", "config.json",
                                   "tokenizer_config.json", "special_tokens_map.json"]),
        ("benjamalegni/finbertonnx", ["model.onnx", "tokenizer.json", "vocab.txt", "config.json"]),
    ]
    for repo, files in candidates:
        if not files:
            continue
        try:
            for f in files:
                try:
                    p = hf_hub_download(repo_id=repo, filename=f)
                except Exception:
                    continue
                dest = OUT / (Path(f).name)
                shutil.copy(p, dest)
            if (OUT / "model.onnx").exists():
                print(f"[finbert] downloaded pre-built ONNX from {repo}")
                return True
        except Exception as e:
            print(f"[finbert] {repo} failed: {e}")
    return False


def _try_torch_export():
    """Export ProsusAI/finbert -> ONNX using torch+transformers (temporary)."""
    try:
        import torch  # noqa
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
    except Exception as e:
        print(f"[finbert] torch/transformers not available for export ({e})"); return False
    try:
        name = "ProsusAI/finbert"
        tok = AutoTokenizer.from_pretrained(name)
        model = AutoModelForSequenceClassification.from_pretrained(name)
        model.eval()
        import torch
        dummy = tok("test headline", return_tensors="pt")
        torch.onnx.export(
            model, (dummy["input_ids"], dummy["attention_mask"], dummy.get("token_type_ids")),
            str(ONNX), input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["logits"],
            dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"},
                          "token_type_ids": {0: "b", 1: "s"}, "logits": {0: "b"}},
            opset_version=14,
        )
        tok.save_pretrained(str(OUT))
        print(f"[finbert] exported via torch -> {ONNX}")
        return True
    except Exception as e:
        print(f"[finbert] torch export failed: {e}"); return False


if __name__ == "__main__":
    ok = _try_hub_prebuilt() or _try_torch_export()
    if ok and ONNX.exists():
        print(f"[finbert] DONE: {ONNX} ({ONNX.stat().st_size//1024//1024}MB)")
        sys.exit(0)
    print("[finbert] could not obtain ONNX model. Live scorer will keep using the keyword "
          "lexicon fallback. To enable FinBERT: `pip install huggingface_hub` (for the "
          "pre-built ONNX) or `pip install torch transformers` (to export), then re-run.")
    sys.exit(1)
