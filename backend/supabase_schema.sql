-- MTP ReportGen — run once in Supabase: SQL Editor → New query → Run
-- Backend uses the service_role key (Settings → API). It bypasses RLS.

create table if not exists public.users (
    username text primary key,
    password_hash text not null,
    role text not null,
    department text
);

create table if not exists public.sessions (
    token text primary key,
    username text not null references public.users(username) on delete cascade,
    expires_at timestamptz not null
);

create index if not exists sessions_username_idx on public.sessions (username);
create index if not exists sessions_expires_at_idx on public.sessions (expires_at);

create table if not exists public.mtp_records (
    id bigint generated always as identity primary key,
    report_date date not null,
    department text not null,
    content text,
    status text not null default 'draft',
    submitted_at timestamptz not null default now(),
    unique (report_date, department)
);

create index if not exists mtp_records_date_idx on public.mtp_records (report_date desc);
create index if not exists mtp_records_dept_idx on public.mtp_records (department, report_date desc);

create table if not exists public.executive_summaries (
    id bigint generated always as identity primary key,
    report_date date not null unique,
    content text not null,
    status text not null default 'draft',
    updated_at timestamptz not null default now()
);

create table if not exists public.reports (
    id bigint generated always as identity primary key,
    report_date date not null,
    departments jsonb not null default '[]'::jsonb,
    file_path text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists reports_date_idx on public.reports (report_date desc);

alter table public.users enable row level security;
alter table public.sessions enable row level security;
alter table public.mtp_records enable row level security;
alter table public.executive_summaries enable row level security;
alter table public.reports enable row level security;

-- No anon/authenticated policies: browser keys cannot read users or submissions.
-- The FastAPI server uses the service role key, which bypasses RLS.

insert into storage.buckets (id, name, public)
values ('reports', 'reports', false)
on conflict (id) do nothing;
