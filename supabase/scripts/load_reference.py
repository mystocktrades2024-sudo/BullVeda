"""Load reference data into Supabase:
  - tickers (from cache/last_bundle.json sp500/r1000/r2000/ticker_sources)
  - capability_registry (from data/capability_registry.json)
  - role_capabilities (derived from capability_registry default_roles)
  - open_items (from data/open_items.json)
  - config_snapshots (snapshot of current config/config.json)

Idempotent — uses ON CONFLICT DO UPDATE.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn, repo_root  # noqa: E402

ROOT = repo_root()


def load_tickers(cur) -> int:
    bundle = ROOT / "cache" / "last_bundle.json"
    if not bundle.exists():
        print(f"  · skip tickers: {bundle} missing")
        return 0
    data = json.loads(bundle.read_text())
    seen: dict[str, dict] = {}

    for t in data.get("sp500_list", []) or []:
        seen.setdefault(t, {})["in_sp500"] = True
    for t in data.get("russell1000_list", []) or []:
        seen.setdefault(t, {})["in_r1000"] = True
    for t in data.get("russell2000_list", []) or []:
        seen.setdefault(t, {})["in_r2000"] = True

    # ticker_sources has richer metadata when available
    for t, meta in (data.get("ticker_sources") or {}).items():
        seen.setdefault(t, {})
        if isinstance(meta, dict):
            for k in ("sector", "industry", "name"):
                if meta.get(k):
                    seen[t][k] = meta[k]

    rows = [
        (
            t,
            v.get("name"),
            v.get("sector"),
            v.get("industry"),
            bool(v.get("in_sp500")),
            bool(v.get("in_r1000")),
            bool(v.get("in_r2000")),
        )
        for t, v in seen.items()
        if t and isinstance(t, str)
    ]

    if not rows:
        print("  · no tickers to load")
        return 0

    cur.executemany(
        """
        insert into public.tickers (ticker, name, sector, industry, in_sp500, in_r1000, in_r2000)
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (ticker) do update set
            name      = coalesce(excluded.name, public.tickers.name),
            sector    = coalesce(excluded.sector, public.tickers.sector),
            industry  = coalesce(excluded.industry, public.tickers.industry),
            in_sp500  = excluded.in_sp500 or public.tickers.in_sp500,
            in_r1000  = excluded.in_r1000 or public.tickers.in_r1000,
            in_r2000  = excluded.in_r2000 or public.tickers.in_r2000,
            last_seen = now()
        """,
        rows,
    )
    return len(rows)


def load_capability_registry(cur) -> tuple[int, int]:
    path = ROOT / "data" / "capability_registry.json"
    if not path.exists():
        print(f"  · skip capability_registry: {path} missing")
        return 0, 0
    cfg = json.loads(path.read_text())

    cap_rows = []
    role_cap_rows = []

    for kind in ("tabs", "sub_tabs", "actions"):
        for cap_id, meta in (cfg.get(kind) or {}).items():
            cap_rows.append(
                (
                    cap_id,
                    kind.rstrip("s"),  # tabs → tab
                    meta.get("label"),
                    meta.get("group"),
                    meta.get("module"),
                    meta.get("default_roles") or [],
                    True,
                    json.dumps(meta),
                )
            )
            for role in meta.get("default_roles") or []:
                role_cap_rows.append((role, cap_id))

    cur.executemany(
        """
        insert into public.capability_registry
            (id, kind, label, group_id, module, default_roles, is_enabled, meta_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        on conflict (id) do update set
            kind          = excluded.kind,
            label         = excluded.label,
            group_id      = excluded.group_id,
            module        = excluded.module,
            default_roles = excluded.default_roles,
            meta_json     = excluded.meta_json,
            updated_at    = now()
        """,
        cap_rows,
    )

    cur.executemany(
        """
        insert into public.role_capabilities (role, capability_id, granted)
        values (%s, %s, true)
        on conflict (role, capability_id) do update set granted = true
        """,
        role_cap_rows,
    )

    return len(cap_rows), len(role_cap_rows)


def load_open_items(cur) -> int:
    path = ROOT / "data" / "open_items.json"
    if not path.exists():
        print(f"  · skip open_items: {path} missing")
        return 0
    payload = json.loads(path.read_text())
    items = payload.get("items") or []
    rows = [
        (
            it.get("id"),
            it.get("priority"),
            it.get("section"),
            it.get("item"),
            it.get("what"),
            it.get("how"),
            it.get("effort"),
            it.get("status"),
            it.get("risk_win"),
            it.get("notes"),
            it.get("how_to_test"),
            it.get("date_fixed") or None,
            it.get("commit"),
        )
        for it in items
        if it.get("id")
    ]
    cur.executemany(
        """
        insert into public.open_items
            (id, priority, section, item, what, how, effort, status,
             risk_win, notes, how_to_test, date_fixed, commit)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (id) do update set
            priority    = excluded.priority,
            section     = excluded.section,
            item        = excluded.item,
            what        = excluded.what,
            how         = excluded.how,
            effort      = excluded.effort,
            status      = excluded.status,
            risk_win    = excluded.risk_win,
            notes       = excluded.notes,
            how_to_test = excluded.how_to_test,
            date_fixed  = excluded.date_fixed,
            commit      = excluded.commit,
            updated_at  = now()
        """,
        rows,
    )
    return len(rows)


def snapshot_config(cur) -> str | None:
    path = ROOT / "config" / "config.json"
    if not path.exists():
        print(f"  · skip config snapshot: {path} missing")
        return None
    body = path.read_text()
    h = hashlib.sha256(body.encode()).hexdigest()[:16]
    cur.execute(
        """
        insert into public.config_snapshots (hash, config_json, note)
        values (%s, %s::jsonb, %s)
        on conflict (hash) do nothing
        """,
        (h, body, "initial migration snapshot"),
    )
    return h


def main():
    conn = pg_conn()
    try:
        with conn, conn.cursor() as cur:
            n_t = load_tickers(cur)
            print(f"  tickers loaded: {n_t}")

            n_c, n_rc = load_capability_registry(cur)
            print(f"  capability_registry: {n_c} rows · role_capabilities: {n_rc} rows")

            n_o = load_open_items(cur)
            print(f"  open_items: {n_o} rows")

            h = snapshot_config(cur)
            print(f"  config_snapshot hash: {h}")
    finally:
        conn.close()
    print("✓ Reference data loaded")


if __name__ == "__main__":
    main()
