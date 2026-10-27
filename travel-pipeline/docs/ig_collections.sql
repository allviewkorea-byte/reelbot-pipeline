-- 인스타 쇼핑 A3 — 컬렉션 릴스(같은 자세·배경, 옷만 바꾼 Look 1~N).
-- ⚠️ 실행 순서: 이 SQL 을 Supabase SQL Editor 에서 먼저 실행 → PR 머지. 여러 번 실행해도 안전.
create table if not exists ig_collections (
  id            text primary key check (id ~ '^cl-[0-9]{8}-[a-z0-9]{4,12}$'),
  character_id  text not null,
  theme         jsonb not null default '{}'::jsonb,   -- 컨셉·표지 카피·검색어·베이스
  looks         jsonb not null default '[]'::jsonb,   -- [{n, image_key, outfit_id?, product{...}, review}]
  base_items    jsonb not null default '[]'::jsonb,
  video_key     text,
  cover_key     text,
  status        text not null default 'making' check (status in ('making', 'ok', 'failed', 'hidden')),
  error         text,
  cost_usd      numeric,
  usage         jsonb not null default '{}'::jsonb,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists ig_collections_created on ig_collections (created_at desc);
alter table ig_collections enable row level security;
revoke all on table ig_collections from anon, authenticated;
grant all on table ig_collections to service_role;
