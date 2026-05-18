#!/usr/bin/env python3
"""config_history_writer.py — Write config diff to Supabase.
Invoked by infra/hooks/post-commit when config/*.json files change."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def _flatten_dict(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_dict(v, key))
        else:
            out[key] = v
    return out


def _git_show(path, rev):
    try:
        out = subprocess.check_output(["git", "show", f"{rev}:{path}"], cwd=str(ROOT), timeout=10)
        return json.loads(out.decode("utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", required=True)
    ap.add_argument("--author", default="")
    ap.add_argument("--files", required=True)
    args = ap.parse_args()
    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    try:
        from supabase_client import sb_client
        sb = sb_client()
        if sb is None: return 0
    except Exception:
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    config_paths = [p.strip() for p in args.files.split("\n") if p.strip()]
    config_rows = []
    flag_rows = []

    for path in config_paths:
        after = _git_show(path, args.commit)
        before = _git_show(path, args.commit + "~1")
        if after is None and before is None: continue
        diff = {}
        if before and after:
            bf = _flatten_dict(before)
            af = _flatten_dict(after)
            for k in set(bf.keys()) | set(af.keys()):
                bv, av = bf.get(k), af.get(k)
                if bv != av:
                    diff[k] = {"before": bv, "after": av}
                    if k.endswith("_enabled") and isinstance(av, bool):
                        flag_rows.append({
                            "flipped_at": now_iso, "flag_path": k,
                            "old_value": json.dumps(bv), "new_value": json.dumps(av),
                            "git_commit": args.commit,
                            "note": f"changed in {path}",
                        })
        elif after and not before:
            diff = {k: {"before": None, "after": v} for k, v in _flatten_dict(after).items()}
        elif before and not after:
            diff = {k: {"before": v, "after": None} for k, v in _flatten_dict(before).items()}

        config_rows.append({
            "changed_at": now_iso, "git_commit": args.commit,
            "author": args.author, "config_path": path,
            "config_after": after or {}, "config_diff": diff,
            "note": f"{len(diff)} keys changed",
        })

    if config_rows:
        try:
            sb.table("config_history").insert(config_rows).execute()
            print(f"  ✓ config_history +{len(config_rows)}")
        except Exception as e:
            print(f"  ! config_history: {e}")
    if flag_rows:
        try:
            sb.table("feature_flag_changes").insert(flag_rows).execute()
            print(f"  ✓ feature_flag_changes +{len(flag_rows)}")
        except Exception as e:
            print(f"  ! feature_flag_changes: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
