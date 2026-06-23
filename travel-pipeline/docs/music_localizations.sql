-- #32 다국어 시스템 — music_uploads 에 localizations(jsonb) 컬럼 추가.
-- 구조: { source_lang, meta:{lang:{title,description}}, lyrics:{lang:text}, hashtags:[...] }
-- 검수 UI 가 생성/수정하고, 공개 업로드 시 captions.insert + videos.update 에 사용한다.
-- Supabase SQL Editor 에서 실행. 즉시 반영(재배포 불필요).

alter table public.music_uploads
  add column if not exists localizations jsonb;

grant all on table public.music_uploads to service_role, anon, authenticated;
