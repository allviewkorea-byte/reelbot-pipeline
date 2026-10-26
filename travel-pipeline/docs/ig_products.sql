-- 인스타 쇼핑 A2-2 — 상품 픽(쿠팡 파트너스 + 네이버 쇼핑 공식 API).
-- ig_products: 검색으로 고른 상품(1등 + 예비). 이미지는 R2 insta/products/{channel}/{product_id}.jpg 사본.
-- ig_looks: 레퍼런스 룩 1개 = 코디 1벌. items 에 아이템별 명세·1등·예비·점수를 담는다(룩-상품 연결).
--
-- ⚠️ 실행 순서: 이 SQL 을 Supabase SQL Editor 에서 먼저 실행 → PR 머지.
-- 백엔드는 secret(service_role) 키만 쓰므로 RLS 를 켜고 GRANT 는 service_role 에만.
-- 여러 번 실행해도 안전(if not exists).

create table if not exists ig_products (
  id              bigint generated always as identity primary key,
  channel         text not null check (channel in ('coupang', 'naver')),
  product_id      text not null,                       -- 통로의 상품 id
  name            text not null,
  mall            text,
  brand           text,
  category        text,
  price           int,
  image_url       text,                                -- 원본 이미지 URL
  image_key       text,                                -- R2 사본(합성·화면용)
  link            text,                                -- 상품 링크
  affiliate_link  text,                                -- 쿠팡 제휴 딥링크(네이버는 비움)
  raw             jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (channel, product_id)
);

create table if not exists ig_looks (
  id              text primary key check (id ~ '^lk-[0-9]{8}-[a-z0-9]{4,12}$'),
  ref_video_id    text references ig_refs(video_id),
  look_index      int not null default 0,
  concept         text,
  spec            jsonb not null default '{}'::jsonb,  -- 레퍼런스 룩 명세서(그대로)
  items           jsonb not null default '[]'::jsonb,  -- [{index, kind, spec, pick, backups[], scores{product_id: {...}}, note}]
  combo           jsonb,                               -- 조합 검사(색 수·포인트·교체 기록)
  status          text not null default 'picking'
                  check (status in ('picking', 'picked', 'failed', 'approved', 'rejected')),
  error           text,
  usage           jsonb not null default '{}'::jsonb,  -- 이번 픽의 호출 수(쿠팡·네이버·비전)
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists ig_looks_created on ig_looks (created_at desc);

alter table ig_products enable row level security;
alter table ig_looks enable row level security;
revoke all on table ig_products, ig_looks from anon, authenticated;
grant all on table ig_products, ig_looks to service_role;
