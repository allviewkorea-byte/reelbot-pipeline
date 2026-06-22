-- music_uploads — Rooftop Music 영상의 유튜브(Revezen) 업로드 기록.
-- 레포에 마이그레이션 러너가 없으므로 Supabase SQL 에디터에서 1회 수동 실행한다.
-- ⚠️ 신규 테이블은 GRANT 필수(누락 시 PostgREST 401 permission denied) — music_tracks.sql 동일 패턴.

create table if not exists music_uploads (
  id               bigint generated always as identity primary key,
  slug             text,                    -- 주제 slug
  mix_id           text,                    -- 믹스 ID
  youtube_video_id text,                    -- 업로드된 영상 ID
  youtube_url      text,
  uploaded_at      timestamptz default now()
);

-- 조회 편의(slug·최신순).
create index if not exists music_uploads_slug_idx
  on music_uploads (slug, uploaded_at desc);

-- 🚨 GRANT — 기존 테이블과 동일 패턴(service_role / anon / authenticated).
grant all on table music_uploads to service_role, anon, authenticated;
grant usage, select on all sequences in schema public to service_role, anon, authenticated;
