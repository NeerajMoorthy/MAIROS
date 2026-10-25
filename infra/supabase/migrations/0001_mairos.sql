-- MAIROS on Supabase — schema and access lockdown.
--
-- Run once in the Supabase SQL editor (or `supabase db push`). Two consumers
-- share this database:
--
--   1. The FastAPI backend (Fly.io) — `mairos.*` document tables. It also
--      creates these itself on first start (app/db.py), so this section is
--      here for review and for databases where the API role cannot run DDL.
--   2. Better Auth (Next.js on Cloudflare) — `public.user`, `session`,
--      `account`, `verification`, `jwks`. The authoritative way to create
--      these is `npx @better-auth/cli migrate` from apps/web, which tracks
--      Better Auth's own schema version; the definitions below match
--      Better Auth 1.x with the JWT plugin and are provided for review.
--
-- Security: Supabase exposes the `public` schema through its Data API to
-- anyone holding the project's anon key. Every table below has row-level
-- security ENABLED with NO policies, which refuses the anon and authenticated
-- Data API roles outright. The application connects as the table owner over
-- the Postgres connection string and is unaffected.

-- ---------------------------------------------------------------------------
-- 1. MAIROS metadata (FastAPI)
-- ---------------------------------------------------------------------------
create schema if not exists mairos;

create table if not exists mairos.meta (
    key   text primary key,
    value text not null
);

do $$
declare
    t text;
begin
    foreach t in array array['projects', 'documents', 'papers', 'patents', 'tasks', 'evaluations'] loop
        execute format(
            'create table if not exists mairos.%I (
                 id          text primary key,
                 project_id  text,
                 created_at  text,
                 payload     jsonb not null
             )', t);
        execute format('create index if not exists idx_%s_project on mairos.%I (project_id)', t, t);
        execute format('create index if not exists idx_%s_created on mairos.%I (created_at)', t, t);
        execute format('alter table mairos.%I enable row level security', t);
    end loop;
end $$;

alter table mairos.meta enable row level security;

-- ---------------------------------------------------------------------------
-- 2. Better Auth (Next.js)
-- ---------------------------------------------------------------------------
create table if not exists public."user" (
    "id"            text primary key,
    "name"          text not null,
    "email"         text not null unique,
    "emailVerified" boolean not null default false,
    "image"         text,
    "createdAt"     timestamptz not null default now(),
    "updatedAt"     timestamptz not null default now()
);

create table if not exists public."session" (
    "id"          text primary key,
    "expiresAt"   timestamptz not null,
    "token"       text not null unique,
    "createdAt"   timestamptz not null default now(),
    "updatedAt"   timestamptz not null default now(),
    "ipAddress"   text,
    "userAgent"   text,
    "userId"      text not null references public."user" ("id") on delete cascade
);
create index if not exists idx_session_user on public."session" ("userId");

create table if not exists public."account" (
    "id"                    text primary key,
    "accountId"             text not null,
    "providerId"            text not null,
    "userId"                text not null references public."user" ("id") on delete cascade,
    "accessToken"           text,
    "refreshToken"          text,
    "idToken"               text,
    "accessTokenExpiresAt"  timestamptz,
    "refreshTokenExpiresAt" timestamptz,
    "scope"                 text,
    "password"              text,
    "createdAt"             timestamptz not null default now(),
    "updatedAt"             timestamptz not null default now()
);
create index if not exists idx_account_user on public."account" ("userId");

create table if not exists public."verification" (
    "id"         text primary key,
    "identifier" text not null,
    "value"      text not null,
    "expiresAt"  timestamptz not null,
    "createdAt"  timestamptz default now(),
    "updatedAt"  timestamptz default now()
);

-- JWT plugin key store. The private key is encrypted by Better Auth with
-- BETTER_AUTH_SECRET; RLS keeps even the ciphertext off the Data API.
create table if not exists public."jwks" (
    "id"         text primary key,
    "publicKey"  text not null,
    "privateKey" text not null,
    "createdAt"  timestamptz not null default now(),
    "expiresAt"  timestamptz
);

alter table public."user"         enable row level security;
alter table public."session"      enable row level security;
alter table public."account"      enable row level security;
alter table public."verification" enable row level security;
alter table public."jwks"         enable row level security;
