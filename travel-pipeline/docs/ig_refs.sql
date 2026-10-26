-- 인스타 쇼핑 A2-1 — 유튜브 레퍼런스 + 외부 API 사용량.
-- 레퍼런스는 조합·분위기 참고용(결과물·캡션에 그대로 쓰지 않음). 썸네일은 화면 표시용 R2 사본
-- insta/refs/{video_id}.jpg 만 두고 생성 참조로는 쓰지 않는다. 영상 다운로드·프레임 추출 없음.
--
-- ⚠️ 실행 순서: 이 SQL 을 Supabase SQL Editor 에서 먼저 실행 → PR 머지.
-- 백엔드는 secret(service_role) 키만 쓰므로 RLS 를 켜고 GRANT 는 service_role 에만.
-- 여러 번 실행해도 안전(if not exists).

create table if not exists ig_refs (
  video_id       text primary key,                      -- 유튜브 영상 id (같은 영상 중복 금지)
  query          text,                                  -- 찾은 검색어
  title          text not null,
  channel_title  text,
  description    text,                                  -- 설명란(앞 3000자)
  desc_products  jsonb not null default '[]'::jsonb,    -- 설명란 착용 제품 [{name, brand}] — 가장 강한 단서
  views          bigint,
  published_at   timestamptz,
  thumb_key      text,                                  -- R2 썸네일 사본(화면 표시용)
  analysis       jsonb,                                 -- 룩 명세서 {looks: [...]} (비전 AI)
  status         text not null default 'new'
                 check (status in ('new', 'analyzed', 'failed', 'used')),
  error          text,
  used_at        timestamptz,
  collected_at   timestamptz not null default now()
);
create index if not exists ig_refs_status_collected on ig_refs (status, collected_at desc);

-- 외부 API 일일 사용량(유튜브 유닛 상한 · 이후 쿠팡/네이버 호출 수도 같은 표)
create table if not exists ig_api_usage (
  day     date not null,                                -- KST 날짜
  api     text not null,                                -- 'youtube' | 'coupang' | 'naver'
  units   int  not null default 0,
  calls   int  not null default 0,
  primary key (day, api)
);

alter table ig_refs enable row level security;
alter table ig_api_usage enable row level security;
revoke all on table ig_refs, ig_api_usage from anon, authenticated;
grant all on table ig_refs, ig_api_usage to service_role;
