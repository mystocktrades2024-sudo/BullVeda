-- ============================================================================
-- 0020 · Seed data · roles + initial portfolio_state singleton
-- ============================================================================
-- capability_registry rows are loaded by scripts/load_reference.py (parsed
-- from data/capability_registry.json).
-- ============================================================================

insert into public.roles (role, label, description) values
  ('admin',  'Administrator', 'Full read+write on all tables, including governance.'),
  ('trader', 'Trader',        'Read all + write portfolio/positions/watchlist/alerts.'),
  ('quant',  'Quant',         'Read-only access for analytics + backtests.'),
  ('viewer', 'Viewer',        'Read-only dashboard access.')
on conflict (role) do update
  set label = excluded.label,
      description = excluded.description;

-- Initial portfolio_state singleton (created if missing). Starting equity
-- matches today's local state; ETL will overwrite on first sync.
insert into public.portfolio_state (id, equity, cash, margin_reserved, starting_equity)
values (1, 100000, 100000, 0, 100000)
on conflict (id) do nothing;
