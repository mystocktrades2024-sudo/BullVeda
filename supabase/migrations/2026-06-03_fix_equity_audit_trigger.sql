-- Fix: trg_equity_audit() referenced the OLD equity_audit schema
-- (timestamp, old_equity, new_equity, old_cash, new_cash, invested, reason) but the
-- table was migrated to (id, occurred_at, event_type, delta, balance_after, note,
-- sync_key). The drift caused every portfolio_state UPDATE to fail with
-- 42703 "column timestamp of relation equity_audit does not exist", blocking the
-- portfolio_state row in the SQLite→Supabase sync. (2026-06-03)
--
-- ROLLBACK (original definition):
--   CREATE OR REPLACE FUNCTION public.trg_equity_audit() RETURNS trigger LANGUAGE plpgsql AS $$
--   BEGIN
--     IF (OLD.equity IS DISTINCT FROM NEW.equity) OR (OLD.cash IS DISTINCT FROM NEW.cash) THEN
--       INSERT INTO equity_audit (timestamp, old_equity, new_equity, old_cash, new_cash, invested, reason)
--       VALUES (NOW(), OLD.equity, NEW.equity, OLD.cash, NEW.cash, COALESCE(NEW.equity-NEW.cash,0),
--               'auto-trigger on portfolio_state UPDATE');
--     END IF; RETURN NEW; END; $$;

CREATE OR REPLACE FUNCTION public.trg_equity_audit()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF (OLD.equity IS DISTINCT FROM NEW.equity)
       OR (OLD.cash IS DISTINCT FROM NEW.cash) THEN
        INSERT INTO equity_audit (occurred_at, event_type, delta, balance_after, note, sync_key)
        VALUES (
            NOW(),
            'auto-trigger',
            COALESCE(NEW.equity - OLD.equity, 0),
            NEW.equity,
            'portfolio_state UPDATE (cash ' || COALESCE(OLD.cash::text,'?') || ' -> ' || COALESCE(NEW.cash::text,'?') || ')',
            md5(clock_timestamp()::text || COALESCE(NEW.equity::text,''))
        );
    END IF;
    RETURN NEW;
END;
$function$;
