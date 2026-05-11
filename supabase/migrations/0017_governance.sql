-- ============================================================================
-- 0017 · Governance · users · roles · RBAC · open items
-- ============================================================================

create table if not exists public.roles (
  role                 text primary key,
  label                text,
  description          text,
  is_active            boolean default true,
  created_at           timestamptz default now()
);

create table if not exists public.users (
  id                   uuid primary key references auth.users(id) on delete cascade,
  email                text unique not null,
  role                 text not null references public.roles(role) on delete restrict default 'viewer',
  display_name         text,
  created_at           timestamptz default now(),
  last_login_at        timestamptz
);

create table if not exists public.capability_registry (
  id                   text primary key,
  kind                 text check (kind in ('tab','sub_tab','action')),
  label                text,
  group_id             text,
  module               text,
  default_roles        text[],
  is_enabled           boolean default true,
  meta_json            jsonb,
  updated_at           timestamptz default now()
);
create index cap_reg_kind_idx  on public.capability_registry(kind);
create index cap_reg_group_idx on public.capability_registry(group_id);

create table if not exists public.role_capabilities (
  role                 text not null references public.roles(role) on delete cascade,
  capability_id        text not null references public.capability_registry(id) on delete cascade,
  granted              boolean default true,
  primary key (role, capability_id)
);

create table if not exists public.open_items (
  id                   text primary key,
  priority             text check (priority in ('P0','P1','P2','P3') or priority is null),
  section              text,
  item                 text,
  what                 text,
  how                  text,
  effort               text,
  status               text check (status in ('OPEN','IN_PROGRESS','DONE','DEFERRED','REJECTED') or status is null),
  risk_win             text,
  notes                text,
  how_to_test          text,
  date_fixed           date,
  commit               text,
  created_at           timestamptz default now(),
  updated_at           timestamptz default now()
);
create index open_items_status_idx   on public.open_items(status);
create index open_items_priority_idx on public.open_items(priority);
create trigger open_items_set_updated before update on public.open_items
  for each row execute function public.tg_set_updated_at();
