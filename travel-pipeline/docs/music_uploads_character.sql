-- music_uploads #50 — 인물(투명 PNG) 레이어 합성용 컬럼.
-- music_uploads_v2.sql 실행 후 Supabase SQL 에디터에서 1회 실행한다.
-- 빈 문자열 = 인물 없음(기존 동작). 값 있음 = R2(music-characters/{slug}/{mix_id}.png)에 투명 PNG 저장됨.

alter table music_uploads
  add column if not exists character_r2_key text not null default '';

-- 🚨 GRANT 재확인(컬럼 추가 후) — 기존 패턴과 동일.
grant select, insert, update on music_uploads to anon, authenticated, service_role;
