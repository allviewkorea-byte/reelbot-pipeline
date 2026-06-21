-- music_themes — Rooftop Music 주제 생성기(music_theme) 산출물 영구 기록.
-- 레포에 마이그레이션 러너가 없으므로 Supabase SQL 에디터에서 1회 수동 실행한다.
-- ⚠️ 신규 테이블은 GRANT 필수(누락 시 PostgREST 401 permission denied) — music_tracks.sql 동일 패턴.

create table if not exists music_themes (
  slug         text primary key,        -- 영문 소문자_스네이크 (R2/DB 키)
  title_kr     text,                    -- 유튜브 제목용 한국어
  genre        text,
  situation    text,                    -- use-case (운동/공부/드라이브 등)
  mood         text,
  type         text,                    -- vocal | instrumental
  style_prompt text,                    -- Suno 용 영어 스타일 프롬프트
  lyric_tone   text,                    -- vocal 일 때만 한 줄, instrumental 은 null
  track_count  int,
  payload      jsonb,                   -- 생성된 원본 JSON 보존
  created_at   timestamptz default now()
);

-- 최근 주제(장르 dedup) 조회용 — created_at 역순.
create index if not exists music_themes_created_idx
  on music_themes (created_at desc);

-- 🚨 GRANT — 기존 테이블과 동일 패턴(service_role / anon / authenticated).
grant all on table music_themes to service_role, anon, authenticated;
