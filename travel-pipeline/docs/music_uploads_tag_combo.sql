-- music_uploads — tag_combo(8축 태그 조합) 컬럼 추가.
-- 카드에 한글 칩 나열(아기재울때 · 오르골 · 따뜻함)용.
-- Supabase SQL 에디터에서 실행한다.

alter table music_uploads add column if not exists tag_combo jsonb;

-- 🚨 GRANT 재확인(컬럼 추가 후).
grant all on table music_uploads to service_role, anon, authenticated;
