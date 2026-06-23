-- music_uploads.show_playlist — 영상별 PLAY LIST 표시 토글 (작업지시서 #39)
-- 싱글곡 영상은 OFF, 플레이리스트 영상은 ON. 채널 전체 design_config 가 아니라 영상(mix)별.
-- 기본값 true → 기존 영상은 PLAY LIST 표시(회귀 0).
--
-- ⚠️ Supabase SQL 에디터에서 1회 수동 실행. **배포 전에 먼저 실행**(아래 컬럼이
--    music_uploads SELECT 에 포함되므로, 컬럼 없으면 검토대기 큐 조회가 일시적으로 빔).
--    GRANT 재부여 포함(불변원칙).

ALTER TABLE music_uploads
  ADD COLUMN IF NOT EXISTS show_playlist boolean NOT NULL DEFAULT true;

GRANT SELECT, INSERT, UPDATE ON music_uploads TO anon, authenticated, service_role;
