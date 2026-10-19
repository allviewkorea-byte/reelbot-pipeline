-- music_tracks.language — 곡별 가사 언어 ko | en | inst (대표 결정 2026-10-19)
-- 보컬 영상은 곡마다 연주곡(약 25%)·영어(나머지의 70%)·한국어(30%)로 섞인다. Suno 1회 = 2클립은
-- 같은 요청이라 둘 다 같은 값이 기록된다(이후 쌍둥이 번갈아 쓰기 PR 에서 language 로 거른다).
-- 기존 행은 NULL(언어 미기록) — 백필 없음(옛 곡은 language 로 고르지 않는다).
--
-- ⚠️ Supabase SQL 에디터에서 1회 수동 실행. **머지(배포) 전에 먼저 실행**.
--    배포 후 곡 저장(upsert)에 language 키가 실리므로, 컬럼이 없으면 PostgREST 400 으로
--    곡 DB 기록이 실패한다(R2 저장은 되지만 재활용·라이브러리 기록이 빠짐).
--    GRANT 재부여 포함(불변원칙).

ALTER TABLE music_tracks
  ADD COLUMN IF NOT EXISTS language text;

GRANT ALL ON TABLE music_tracks TO service_role, anon, authenticated;

-- 확인(컬럼이 보이면 OK):
-- SELECT column_name, data_type FROM information_schema.columns
--  WHERE table_name = 'music_tracks' AND column_name = 'language';
