-- music_tracks — Rooftop Music 생성곡(sunoapi.org) 메타 영구 저장.
-- 레포에 마이그레이션 러너가 없으므로 Supabase SQL 에디터에서 1회 수동 실행한다.
-- ⚠️ 신규 테이블은 GRANT 필수(누락 시 PostgREST 401 permission denied).

create table if not exists music_tracks (
  id         text primary key,          -- audio_id (곡 단위 고유, 멱등 upsert 키)
  theme_slug text not null,             -- 예: cafe_jazz, lofi_rain
  task_id    text,                      -- suno 생성 요청 단위(요청당 2곡)
  audio_id   text,
  title      text,
  tags       text,                      -- suno tags(콤마 문자열)
  duration   numeric,                   -- 초
  r2_key     text,                      -- music-masters/{theme_slug}/{audio_id}.mp3
  status     text,                      -- SUCCESS 등
  used       boolean not null default false,  -- #46 재활용: true=사용됨 / false=재활용 가능
  genre      text not null default '',        -- #46 재활용 매칭용 장르 id(예: citypop). 빈값=레거시(제외)
  created_at timestamptz default now()
);

-- 조회 편의(테마별 최신순).
create index if not exists music_tracks_theme_created_idx
  on music_tracks (theme_slug, created_at desc);

-- #46 재활용 검색(같은 장르 미사용 트랙 최신순) 인덱스.
create index if not exists music_tracks_genre_used_idx
  on music_tracks (genre, used, created_at desc);

-- 🚨 GRANT — 기존 테이블과 동일 패턴(service_role / anon / authenticated).
grant all on table music_tracks to service_role, anon, authenticated;

-- ─────────────────────────────────────────────────────────────────────
-- #46 마이그레이션 — 기존 배포본에 컬럼만 추가(대표가 배포 전 1회 실행).
alter table music_tracks
  add column if not exists used boolean not null default false;
alter table music_tracks
  add column if not exists genre text not null default '';
grant select, insert, update on music_tracks to anon, authenticated, service_role;
