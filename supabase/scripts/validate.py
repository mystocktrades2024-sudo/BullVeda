"""End-to-end validation: FK integrity, table naming, data flow.

Run after a scan to confirm the analysis pipeline is writing into every
expected sub-table and that all FK constraints hold.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import pg_conn  # noqa: E402


def banner(title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    with pg_conn() as c, c.cursor() as cur:

        # ====== 1. NAMING ======
        banner("1. TABLE-NAMING AUDIT")
        cur.execute("""
            select tablename from pg_tables
             where schemaname='public' and tablename not like 'decision_log_%'
             order by tablename
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"Total user tables: {len(tables)}")
        issues = []
        for t in tables:
            if not re.match(r'^[a-z][a-z0-9_]*$', t):
                issues.append(f"bad chars: {t}")
            if '__' in t:
                issues.append(f"double underscore: {t}")
            if t != t.lower():
                issues.append(f"not lowercase: {t}")
        if issues:
            for x in issues: print("  X " + x)
        else:
            print("  OK all table names snake_case + lowercase")

        # ====== 2. FK INTEGRITY ======
        banner("2. FOREIGN KEY INTEGRITY")
        cur.execute("""
            select tc.table_name, kcu.column_name,
                   ccu.table_name  as foreign_table,
                   ccu.column_name as foreign_column
              from information_schema.table_constraints tc
              join information_schema.key_column_usage kcu
                on tc.constraint_name=kcu.constraint_name
               and tc.table_schema=kcu.table_schema
              join information_schema.constraint_column_usage ccu
                on ccu.constraint_name=tc.constraint_name
               and ccu.table_schema=tc.table_schema
             where tc.constraint_type='FOREIGN KEY'
               and tc.table_schema='public'
             order by tc.table_name, kcu.column_name
        """)
        fks = cur.fetchall()
        print(f"Total FK constraints: {len(fks)}")

        orphans = []
        for ttbl, tcol, ftbl, fcol in fks:
            try:
                cur.execute(
                    f"select count(*) from public.\"{ttbl}\" t "
                    f" where t.\"{tcol}\" is not null "
                    f"   and not exists (select 1 from public.\"{ftbl}\" f where f.\"{fcol}\" = t.\"{tcol}\")"
                )
                n = cur.fetchone()[0]
                if n > 0:
                    orphans.append((ttbl, tcol, ftbl, fcol, n))
            except Exception as e:
                orphans.append((ttbl, tcol, ftbl, fcol, f"ERROR: {str(e)[:50]}"))
        if orphans:
            print(f"  FOUND {len(orphans)} FK issue(s):")
            for ttbl, tcol, ftbl, fcol, n in orphans:
                print(f"    X {ttbl}.{tcol} -> {ftbl}.{fcol}: {n}")
        else:
            print(f"  OK all {len(fks)} foreign keys clean (0 orphans)")

        # ====== 3. DATA FLOW ======
        banner("3. DATA FLOW — recent ticker_analyses + child fill")
        cur.execute("""
            select id, ticker, run_id, verdict, score
              from public.ticker_analyses
             order by analyzed_at desc limit 5
        """)
        recent = cur.fetchall()
        print(f"Most recent {len(recent)} ticker_analyses:")
        for aid, t, rid, v, s in recent:
            print(f"  aid={aid} ticker={t} run={rid} verdict={v} score={s}")

        if not recent:
            print("  no analyses yet"); return
        sample_aid, sample_t, *_ = recent[0]
        print(f"\nChecking child-table fill for analysis_id={sample_aid} ({sample_t}):")

        CHILD_TABLES = [
            'analysis_pricing','analysis_scoring','analysis_verdict','analysis_conviction',
            'trade_plans','trade_plan_entries','trade_plan_risk','risk_sizing',
            'technicals_ema','technicals_momentum','technicals_volatility','technicals_pattern',
            'technicals_trend','technicals_volume_flow','technicals_position','technicals_52w',
            'technicals_relative_strength','technicals_sr_vwap','technicals_loc_volume',
            'options_snapshot','options_intelligence','options_kpis',
            'zacks_data','tier1_signals',
            'news_sentiment_snapshot','reddit_wsb_snapshot','stocktwits_snapshot',
            'insider_summary','congressional_summary','institutional_trend',
        ]
        filled, empty, errs = [], [], []
        for ct in CHILD_TABLES:
            try:
                cur.execute(f"select count(*) from public.{ct} where analysis_id=%s", (sample_aid,))
                n = cur.fetchone()[0]
                (filled if n > 0 else empty).append(ct)
            except Exception as e:
                errs.append((ct, str(e)[:40]))
        print(f"  populated ({len(filled)}/{len(CHILD_TABLES)}): " + ", ".join(filled))
        if empty:
            print(f"  empty ({len(empty)}): " + ", ".join(empty))
        if errs:
            print(f"  errors: " + str(errs[:5]))

        # ====== 4. AGGREGATE counts ======
        banner("4. POPULATED TABLE TOTALS")
        cur.execute("""
            select tablename from pg_tables
             where schemaname='public' and tablename not like 'decision_log_%'
             order by tablename
        """)
        all_tables = [r[0] for r in cur.fetchall()]
        rows = []
        for t in all_tables:
            try:
                cur.execute(f'select count(*) from public."{t}"')
                n = cur.fetchone()[0]
                if n > 0:
                    rows.append((t, n))
            except Exception:
                pass
        rows.sort(key=lambda x: -x[1])
        print(f"Populated tables: {len(rows)} / {len(all_tables)}")
        for t, n in rows[:30]:
            print(f"  {t:38s} {n:>10,d}")


if __name__ == "__main__":
    main()
