"""Retrieval-Augmented Generation for the Kairos AI chat.

Indexes SwingTrade's static docs + dynamic logs into a local ChromaDB,
embeds via Ollama's nomic-embed-text. Used by server.py /api/chat to
inject "RELEVANT KNOWLEDGE" before the LLM generates.

Public API:
    retrieve(query, k=5) -> list[{text, source, score, meta}]
    build_index(force_rebuild=False) -> dict  # build statistics

Storage: cache/rag/chroma/  (gitignored, regenerable from sources)
Embed model: nomic-embed-text (274MB local Ollama model)
"""
from __future__ import annotations
import json
import time
import hashlib
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
RAG_DIR = BASE_DIR / "cache" / "rag" / "chroma"
RAG_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
COLLECTION = "swingtrade"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    import chromadb
    _client = chromadb.PersistentClient(path=str(RAG_DIR))
    _collection = _client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    return _collection


def _embed(text: str) -> list:
    """One embedding via Ollama. Returns list[float] of dim 768."""
    import httpx
    with httpx.Client(timeout=30.0) as cx:
        r = cx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]


def _embed_batch(texts: list) -> list:
    """Sequential embed (Ollama doesn't batch yet). ~30ms per item on M3 Max."""
    return [_embed(t) for t in texts]


def _hid(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _chunk_text(text: str, max_chars: int = 1500, overlap: int = 150) -> list:
    """Sliding-window chunker for long markdown. ~500 tokens per chunk."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        end = min(i + max_chars, len(text))
        # Try to break on a paragraph or sentence boundary
        if end < len(text):
            for sep in ("\n\n", "\n", ". ", " "):
                p = text.rfind(sep, i + max_chars // 2, end)
                if p != -1:
                    end = p + len(sep)
                    break
        chunks.append(text[i:end].strip())
        i = end - overlap if end < len(text) else end
    return [c for c in chunks if len(c) > 50]


# ── Source readers ──────────────────────────────────────────────────────────

def _read_static_docs() -> list:
    """Markdown docs that describe the system rules. Re-index on commit."""
    items = []
    targets = [
        BASE_DIR / "CLAUDE.md",
        *sorted((BASE_DIR / "docs").glob("*.md")),
    ]
    for p in targets:
        if not p.exists():
            continue
        try:
            text = p.read_text()
        except Exception:
            continue
        rel = str(p.relative_to(BASE_DIR))
        for i, chunk in enumerate(_chunk_text(text)):
            items.append({
                "id": f"doc:{rel}:{i}",
                "text": chunk,
                "source": rel,
                "kind": "doc",
            })
    return items


def _read_decision_log(days: int = 90) -> list:
    """One decision per line; each becomes a single semantic chunk."""
    p = BASE_DIR / "data" / "decision_log.jsonl"
    if not p.exists():
        return []
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    items = []
    keep_verdicts = {"BUY", "SHORT", "SELL", "EXIT", "KILL"}  # skip noisy WATCH/SCORE
    with p.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("date", "") < cutoff:
                continue
            if d.get("verdict") not in keep_verdicts:
                continue
            ticker = d.get("ticker", "?")
            text = (
                f"DECISION {d.get('date')} · {ticker} · {d.get('verdict')}\n"
                f"Reason: {d.get('reason') or '-'}\n"
                f"Setup: {d.get('setup_type','-')} · "
                f"Regime: {d.get('regime4','-')} · "
                f"Direction: {d.get('direction','-')}\n"
                f"Score: {d.get('score','-')} · RS: {d.get('rs_rank','-')} · "
                f"R:R: {d.get('rr_ratio','-')} · Entry: {d.get('entry_price','-')}\n"
                f"Gates hit: {','.join(d.get('gates_hit') or []) or 'none'} · "
                f"Catalyst: {d.get('has_catalyst', False)}"
            )
            items.append({
                "id": f"dec:{d.get('date')}:{ticker}:{_hid(text)}",
                "text": text,
                "source": f"decision_log:{d.get('date')}",
                "kind": "decision",
                "ticker": ticker,
                "verdict": d.get("verdict"),
                "date": d.get("date"),
            })
    return items


def _read_picks_history() -> list:
    """Closed trades with outcome → one chunk per trade."""
    p = BASE_DIR / "cache" / "picks_history.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
    except Exception:
        return []
    items = []
    for t in (d.get("trades") or []):
        ticker = t.get("ticker", "?")
        outcome_pct = t.get("return_pct") if t.get("return_pct") is not None else t.get("pnl_pct")
        text = (
            f"CLOSED TRADE · {ticker} · {t.get('entry_date','?')} → {t.get('exit_date','?')}\n"
            f"Setup: {t.get('setup_type','-')} · Direction: {t.get('direction','long')}\n"
            f"Entry: {t.get('entry_price','-')} · Exit: {t.get('exit_price','-')} · "
            f"Return: {outcome_pct}% · Hold: {t.get('hold_days','-')}d\n"
            f"Exit reason: {t.get('exit_reason','-')} · "
            f"Regime at entry: {t.get('regime','-')} · "
            f"Conviction: {t.get('conviction','-')}"
        )
        items.append({
            "id": f"trd:{ticker}:{t.get('entry_date','?')}:{_hid(text)}",
            "text": text,
            "source": f"picks_history:trade",
            "kind": "trade",
            "ticker": ticker,
            "setup": t.get("setup_type"),
            "return_pct": outcome_pct,
        })
    return items


# ── Public API ──────────────────────────────────────────────────────────────

def build_index(force_rebuild: bool = False, verbose: bool = True,
                include_history: bool = False) -> dict:
    """Re-embed sources and upsert into Chroma. ~30ms per chunk on M3 Max.

    Default: indexes ONLY timeless system docs (CLAUDE.md + docs/*.md).
    The live ticker/regime/portfolio context already comes from the
    /api/chat handler via cache/last_bundle.json — indexing historical
    decisions or closed trades would create stale data that conflicts
    with what the user sees on screen.

    Pass include_history=True only when explicitly auditing past behavior.
    """
    col = _get_collection()
    if force_rebuild:
        if verbose:
            print("[rag] force_rebuild=True — dropping existing collection")
        global _client, _collection
        _client.delete_collection(COLLECTION)
        _collection = None
        col = _get_collection()

    sources = [("docs", _read_static_docs)]
    if include_history:
        sources.extend([
            ("decisions", _read_decision_log),
            ("trades", _read_picks_history),
        ])
    stats = {}
    t0 = time.time()
    for label, fn in sources:
        items = fn()
        if not items:
            stats[label] = 0
            continue
        # Filter to those not already indexed (by id)
        existing_ids = set()
        try:
            # Chroma get() with no ids returns up to limit
            page = col.get(limit=10000)
            existing_ids = set(page.get("ids") or [])
        except Exception:
            pass
        new_items = [it for it in items if it["id"] not in existing_ids]
        if not new_items:
            stats[label] = 0
            if verbose:
                print(f"[rag] {label}: 0 new (already indexed {len(items)})")
            continue
        if verbose:
            print(f"[rag] {label}: embedding {len(new_items)} new items...")
        # Embed in chunks to avoid OOM (and so we can print progress)
        BATCH = 32
        all_embeds = []
        for i in range(0, len(new_items), BATCH):
            batch = new_items[i : i + BATCH]
            embeds = _embed_batch([b["text"] for b in batch])
            all_embeds.extend(embeds)
            if verbose:
                print(f"[rag] {label}: {min(i+BATCH, len(new_items))}/{len(new_items)}")
        col.add(
            ids=[b["id"] for b in new_items],
            embeddings=all_embeds,
            documents=[b["text"] for b in new_items],
            metadatas=[{k: v for k, v in b.items()
                        if k not in ("id", "text") and v is not None}
                       for b in new_items],
        )
        stats[label] = len(new_items)
    stats["total_elapsed_sec"] = round(time.time() - t0, 1)
    stats["collection_size"] = col.count()
    if verbose:
        print(f"[rag] done · {stats}")
    return stats


def retrieve(query: str, k: int = 5,
             min_score: float = 0.25) -> list:
    """Embed query, search collection, return top-k chunks.

    Returns: [{text, source, kind, score, ticker?}, ...]
    score is cosine similarity (0..1, higher = better).
    """
    if not query or not query.strip():
        return []
    try:
        col = _get_collection()
        if col.count() == 0:
            return []
        qvec = _embed(query)
        res = col.query(query_embeddings=[qvec], n_results=k,
                        include=["documents", "metadatas", "distances"])
    except Exception as e:
        print(f"[rag] retrieve error: {e}")
        return []
    out = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        # cosine distance = 1 - similarity (Chroma config'd for cosine space)
        sim = 1.0 - dist
        if sim < min_score:
            continue
        out.append({
            "text": doc,
            "source": (meta or {}).get("source", "?"),
            "kind": (meta or {}).get("kind", "?"),
            "ticker": (meta or {}).get("ticker"),
            "score": round(sim, 3),
        })
    return out


def index_size() -> int:
    try:
        return _get_collection().count()
    except Exception:
        return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="drop + rebuild")
    ap.add_argument("--include-history", action="store_true",
                    help="also index decision_log + picks_history (off by default to avoid stale conflicts)")
    ap.add_argument("--query", help="test query after build")
    args = ap.parse_args()
    print(build_index(force_rebuild=args.rebuild, include_history=args.include_history))
    if args.query:
        print(f"\n--- retrieve('{args.query}') ---")
        for r in retrieve(args.query, k=5):
            print(f"[{r['score']:.3f}] {r['source']} ({r['kind']}):")
            print(f"  {r['text'][:200]}...")
            print()
