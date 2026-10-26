-- 인스타 쇼핑 — 착장 사진 1장 생성 이력 (A1).
-- 이미지 원본은 R2 캐릭터 버킷 insta/outfits/{id}/original.png · processed.jpg, 상품 업로드는
-- insta/products/upload/{batch}/{n}.png. 여기엔 키·기획·검수·비용만.
-- 연속 금지 규칙(헤어·포즈·장소 3연속, 현관 거울 주 2회, 아이웨어 빈도)은 이 테이블 최근 이력으로 판정.
--
-- ⚠️ 실행 순서: 이 SQL 을 Supabase SQL Editor 에서 먼저 실행 → PR 머지.
-- 백엔드는 secret(service_role) 키만 쓰므로 RLS 를 켜고 GRANT 는 service_role 에만.
-- 여러 번 실행해도 안전(if not exists).

create table if not exists ig_outfits (
  id              text primary key check (id ~ '^of-[0-9]{8}-[a-z0-9]{4,12}$'),  -- 'of-20261026-a1b2c3'
  character_id    text not null references studio_characters(id),
  product_images  jsonb not null default '[]'::jsonb,   -- [{key, url, kind, desc, revealing}]
  plan            jsonb not null default '{}'::jsonb,   -- {weekday, life, location, pose, cut, hair_role, eyewear, season, reason, ...}
  prompt          text,
  refs            jsonb not null default '[]'::jsonb,   -- 넘긴 참조 URL(순서 그대로)
  image_key       text,                                 -- original.png
  processed_key   text,                                 -- processed.jpg
  review          jsonb,                                -- 마지막 검수 {pass, violations[], ...} + 시도별 기록
  attempts        int not null default 0,
  status          text not null default 'generating'
                  check (status in ('generating', 'ok', 'review_failed', 'failed')),
  error           text,
  cost_usd        numeric(10, 4) not null default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists ig_outfits_char_created on ig_outfits (character_id, created_at desc);

alter table ig_outfits enable row level security;
revoke all on table ig_outfits from anon, authenticated;
grant all on table ig_outfits to service_role;
