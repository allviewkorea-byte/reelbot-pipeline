-- #20 음악 비주얼 시스템 — 곡 분석 결과(VizSpec) 캐싱 컬럼.
-- music_uploads 에 viz_spec(jsonb) 추가. 같은 mix 재렌더 시 GPT 재호출 없이 재사용.
-- Supabase SQL Editor 에서 실행 후, 변경 즉시 반영(재배포 불필요, 백엔드는 PostgREST 사용).

alter table public.music_uploads
  add column if not exists viz_spec jsonb;

-- GRANT 재확인(신규 컬럼은 테이블 권한을 상속하지만, 테이블 GRANT 누락 시 401 방지용으로 재적용).
grant all on table public.music_uploads to service_role, anon, authenticated;
